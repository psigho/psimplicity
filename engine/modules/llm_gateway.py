"""
LLM Gateway Module — v2.3 (post-grill 2026-05-27)
==================================================

Centralizes all LLM API client instantiations, fallback logic, and prompt execution.

Improvements over v2.2:
- **system_instruction is honored properly** on both Gemini SDK (via GenerateContentConfig.system_instruction)
  and OpenAI-compat (via system message). Enables prompt caching for the static rubric.
- **`surgeon` role added** — Prompt Surgeon now routes to cheap Flash by default instead of premium Pro.
- **Per-role max_output_tokens** — parser=12K (scripts can be long), critic=2048, surgeon=2048.
- **Critic default upgraded** from `gemini-2.5-flash` to `gemini-2.5-pro`. The QC gate now uses the
  smarter model. Asymmetry corrected.
- **Exponential backoff** on 429/5xx. Replaces the prior `max_retries=1` cliff.
- **Token usage extracted** from every call and exposed via `last_usage` + optional event_callback.
- **Vision support validation** — `supports_vision(model)` for guardrails at init.

NOTE: callers should pass `role` as one of {"parser", "critic", "surgeon"}. Legacy "parser" continues
to work but Prompt Surgeon should now pass role="surgeon".
"""

import logging
import os
import re
import time
import random
from typing import Dict, Optional, Tuple, Any, Callable, List
from pathlib import Path

import openai
from google import genai
from google.genai import types

from .json_repair import extract_json

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _resolve_env(val: str) -> str:
    """Expand ${VAR} patterns to actual env values."""
    if not val:
        return val
    return re.sub(r'\$\{(\w+)\}', lambda m: os.environ.get(m.group(1), ''), val)


# Known vision-capable model prefixes / substrings. Used by supports_vision().
_VISION_MODEL_HINTS = (
    "gemini-2.5-pro", "gemini-2.5-flash", "gemini-3", "gemini-1.5-pro", "gemini-1.5-flash",
    "gpt-4o", "gpt-4-turbo", "gpt-4-vision", "gpt-4.1", "o4", "o3",
    "claude-3", "claude-sonnet", "claude-opus", "claude-haiku",
    "llama-3.2", "llava", "qwen2-vl", "pixtral",
)

_TEXT_ONLY_BLOCKLIST = (
    "deepseek-r1", "qwen3-235b-a22b", "qwen2.5-coder",
)


def supports_vision(model: str) -> bool:
    """Best-effort guess at whether a model supports image-input."""
    if not model:
        return False
    m = model.lower()
    if any(b in m for b in _TEXT_ONLY_BLOCKLIST):
        return False
    return any(h in m for h in _VISION_MODEL_HINTS)


# Per-role defaults (max_output_tokens). Parser writes JSON for scripts (can be large).
# Critic + surgeon produce focused JSON / single-paragraph rewrites.
_ROLE_MAX_TOKENS = {
    "parser":  12000,
    "critic":  2048,
    "surgeon": 2048,
}

_ROLE_DEFAULT_TEMPS = {
    "parser":  0.7,
    "critic":  0.3,
    "surgeon": 0.7,
}


# ──────────────────────────────────────────────────────────────────────────────
# Retry / backoff
# ──────────────────────────────────────────────────────────────────────────────

def _is_retryable(err: Exception) -> bool:
    """Detect rate-limit and transient-server errors across SDKs."""
    s = str(err).lower()
    return (
        "429" in s or "rate" in s or "resource_exhausted" in s or
        "503" in s or "502" in s or "504" in s or "500" in s or
        "timeout" in s or "temporar" in s or "overloaded" in s
    )


def _retry(fn: Callable, *, max_attempts: int = 5, base_delay: float = 2.0, op: str = "llm_call"):
    """Run `fn()` with exponential backoff on 429/5xx. Raises non-retryable errors immediately."""
    last_err: Optional[Exception] = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except Exception as e:
            last_err = e
            if not _is_retryable(e) or attempt == max_attempts:
                raise
            wait = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
            logger.warning(
                f"[Gateway] retryable error on {op} (attempt {attempt}/{max_attempts}): "
                f"{type(e).__name__}: {str(e)[:200]} — sleeping {wait:.1f}s"
            )
            time.sleep(wait)
    raise last_err  # unreachable; here for type-checker


# ──────────────────────────────────────────────────────────────────────────────
# Gateway
# ──────────────────────────────────────────────────────────────────────────────

class LLMGateway:
    """Unified manager for text generation, JSON parsing, and vision critique.

    Auto-routes Gemini models through the native SDK (preferred) and everything
    else through OpenAI-compatible endpoints (OpenRouter).
    """

    def __init__(
        self,
        config: dict,
        parser_override: Optional[str] = None,
        critic_override: Optional[str] = None,
        surgeon_override: Optional[str] = None,
        event_callback: Optional[Callable[[dict], None]] = None,
        run_id: Optional[str] = None,
    ):
        self.config = config
        self.event_callback = event_callback  # called per-LLM-call with structured event dict
        self.run_id = run_id or "no_run_id"
        self.last_usage: Dict[str, Any] = {}  # populated after each call

        # 1. Resolve credentials
        or_cfg = config.get("openrouter", {})
        or_key = _resolve_env(or_cfg.get("api_key", "")) or os.environ.get("OPENROUTER_API_KEY", "")
        gemini_key = os.environ.get("GEMINI_API_KEY", "")
        self._or_key = or_key
        self._or_cfg = or_cfg

        # 2. Choose primary framework
        if gemini_key:
            self.primary_key = gemini_key
            self.primary_base = "https://generativelanguage.googleapis.com/v1beta/openai/"
            default_parser = "gemini-3.1-pro-preview"
            default_critic = "gemini-2.5-pro"       # ← upgraded from flash per grill F1.7
            default_surgeon = "gemini-2.5-flash"    # ← cheap Flash for prompt rewrites per grill F1.3
            logger.info("Gateway: Using direct Gemini API")
        elif or_key:
            self.primary_key = or_key
            self.primary_base = or_cfg.get("base_url", "https://openrouter.ai/api/v1")
            default_parser = or_cfg.get("parser_model", "google/gemini-3.1-pro-preview")
            default_critic = or_cfg.get("critic_model", "google/gemini-2.5-pro")
            default_surgeon = or_cfg.get("surgeon_model", "google/gemini-2.5-flash")
            logger.info("Gateway: Using OpenRouter API")
        else:
            raise ValueError("No API key found. Set GEMINI_API_KEY or OPENROUTER_API_KEY in .env.")

        # 3. Resolve models with overrides
        self.parser_model,  self._parser_key,  self._parser_base  = self._resolve_model_route(
            parser_override or default_parser, gemini_key, or_key, or_cfg)
        self.critic_model,  self._critic_key,  self._critic_base  = self._resolve_model_route(
            critic_override or default_critic, gemini_key, or_key, or_cfg)
        self.surgeon_model, self._surgeon_key, self._surgeon_base = self._resolve_model_route(
            surgeon_override or default_surgeon, gemini_key, or_key, or_cfg)

        # 4. Validate critic supports vision — fail fast at init, not at first critique
        if not supports_vision(self.critic_model):
            raise ValueError(
                f"Critic model '{self.critic_model}' is not known to support vision input. "
                f"Critique calls require a vision-capable model. "
                f"Pick one of: gemini-2.5-pro, gemini-2.5-flash, claude-sonnet-4, gpt-4o."
            )

        # 5. Initialize native Gemini client (if usable)
        self.gemini_client: Optional[genai.Client] = None
        if gemini_key:
            try:
                self.gemini_client = genai.Client(api_key=gemini_key)
                logger.info("✅ Native Gemini SDK initialized in Gateway")
            except Exception as e:
                logger.warning(f"Failed to init native Gemini SDK: {e}")

        # 6. OpenAI-compat clients (lazy)
        self._oai_clients: Dict[str, openai.OpenAI] = {}

    # -------------------------------------------------------------------------
    # Routing
    # -------------------------------------------------------------------------

    def _resolve_model_route(self, model_name: str, gemini_key: str, or_key: str,
                              or_cfg: dict) -> Tuple[str, str, str]:
        """Pick (model, key, base_url) for a given logical model name."""
        gemini_base = "https://generativelanguage.googleapis.com/v1beta/openai/"
        or_base = or_cfg.get("base_url", "https://openrouter.ai/api/v1")

        is_gemini_model = model_name.startswith("gemini-") or model_name.startswith("google/gemini-")
        bare_gemini = model_name.replace("google/", "") if model_name.startswith("google/") else model_name

        if is_gemini_model and gemini_key:
            return bare_gemini, gemini_key, gemini_base

        if is_gemini_model:
            or_model = f"google/{bare_gemini}"
            logger.info(f"Routing {model_name} → OpenRouter as {or_model}")
            return or_model, or_key or self.primary_key, or_base

        return model_name, or_key or self.primary_key, or_base

    def _get_oai_client(self, api_key: str, base_url: str) -> openai.OpenAI:
        cache_key = f"{base_url}_{api_key[:5]}"
        if cache_key not in self._oai_clients:
            self._oai_clients[cache_key] = openai.OpenAI(
                api_key=api_key, base_url=base_url, timeout=120.0, max_retries=0
            )
        return self._oai_clients[cache_key]

    def _role_to_target(self, role: str) -> Tuple[str, str, str]:
        if role == "parser":
            return self.parser_model, self._parser_key, self._parser_base
        if role == "surgeon":
            return self.surgeon_model, self._surgeon_key, self._surgeon_base
        return self.critic_model, self._critic_key, self._critic_base  # critic default

    # -------------------------------------------------------------------------
    # Telemetry
    # -------------------------------------------------------------------------

    def _emit(self, event: dict) -> None:
        event["ts"] = time.time()
        event["run_id"] = self.run_id
        if self.event_callback:
            try:
                self.event_callback(event)
            except Exception as e:
                logger.debug(f"event_callback raised: {e}")

    @staticmethod
    def _extract_usage_openai(resp) -> dict:
        u = getattr(resp, "usage", None)
        if not u:
            return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        return {
            "prompt_tokens":     getattr(u, "prompt_tokens", 0),
            "completion_tokens": getattr(u, "completion_tokens", 0),
            "total_tokens":      getattr(u, "total_tokens", 0),
        }

    @staticmethod
    def _extract_usage_gemini(resp) -> dict:
        meta = getattr(resp, "usage_metadata", None)
        if not meta:
            return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        return {
            "prompt_tokens":     getattr(meta, "prompt_token_count", 0),
            "completion_tokens": getattr(meta, "candidates_token_count", 0),
            "total_tokens":      getattr(meta, "total_token_count", 0),
        }

    # -------------------------------------------------------------------------
    # Public API: generate_json
    # -------------------------------------------------------------------------

    def generate_json(self, prompt: str, system_instruction: str = "",
                       role: str = "parser", scene_num: Optional[int] = None) -> Dict[str, Any]:
        """Generate structured JSON. Uses Native Gemini SDK when possible, otherwise OpenAI-compat."""
        model, api_key, base_url = self._role_to_target(role)
        max_toks = _ROLE_MAX_TOKENS.get(role, 4096)
        temp = _ROLE_DEFAULT_TEMPS.get(role, 0.7)

        t0 = time.time()

        # Path A: Native Gemini SDK — system_instruction goes through SDK config field (cacheable)
        if self.gemini_client and model.startswith("gemini-"):
            logger.debug(f"[Gateway:{role}] JSON → Native Gemini ({model})")

            def _call():
                cfg_kwargs = dict(
                    response_mime_type="application/json",
                    max_output_tokens=max_toks,
                    temperature=temp,
                )
                if system_instruction:
                    cfg_kwargs["system_instruction"] = system_instruction
                return self.gemini_client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(**cfg_kwargs),
                )

            resp = _retry(_call, op=f"gemini.generate_json[{role}]")
            usage = self._extract_usage_gemini(resp)
            self.last_usage = usage
            self._emit({
                "event": "llm_call", "role": role, "model": model, "kind": "json",
                "scene_num": scene_num, "duration_s": round(time.time() - t0, 3),
                "usage": usage, "provider": "gemini-native",
            })
            return extract_json(resp.text)

        # Path B: OpenAI-compatible — system goes as system role message
        logger.debug(f"[Gateway:{role}] JSON → OpenAI-Compat ({model})")
        client = self._get_oai_client(api_key, base_url)
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        def _call():
            return client.chat.completions.create(
                model=model, messages=messages,
                response_format={"type": "json_object"},
                temperature=temp, max_tokens=max_toks,
            )

        resp = _retry(_call, op=f"oai.generate_json[{role}]")
        usage = self._extract_usage_openai(resp)
        self.last_usage = usage
        self._emit({
            "event": "llm_call", "role": role, "model": model, "kind": "json",
            "scene_num": scene_num, "duration_s": round(time.time() - t0, 3),
            "usage": usage, "provider": "openai-compat",
        })
        return extract_json(resp.choices[0].message.content)

    # -------------------------------------------------------------------------
    # Public API: generate_text
    # -------------------------------------------------------------------------

    def generate_text(self, prompt: str, system_instruction: str = "",
                       role: str = "critic", temp: Optional[float] = None,
                       scene_num: Optional[int] = None) -> str:
        """Generate raw text. Used for prompt surgery and story generation."""
        model, api_key, base_url = self._role_to_target(role)
        max_toks = _ROLE_MAX_TOKENS.get(role, 4096)
        effective_temp = temp if temp is not None else _ROLE_DEFAULT_TEMPS.get(role, 0.7)

        t0 = time.time()

        if self.gemini_client and model.startswith("gemini-"):
            logger.debug(f"[Gateway:{role}] TEXT → Native Gemini ({model})")

            def _call():
                cfg_kwargs = dict(
                    temperature=effective_temp,
                    max_output_tokens=max_toks,
                )
                if system_instruction:
                    cfg_kwargs["system_instruction"] = system_instruction
                return self.gemini_client.models.generate_content(
                    model=model, contents=prompt,
                    config=types.GenerateContentConfig(**cfg_kwargs),
                )

            resp = _retry(_call, op=f"gemini.generate_text[{role}]")
            usage = self._extract_usage_gemini(resp)
            self.last_usage = usage
            self._emit({
                "event": "llm_call", "role": role, "model": model, "kind": "text",
                "scene_num": scene_num, "duration_s": round(time.time() - t0, 3),
                "usage": usage, "provider": "gemini-native",
            })
            return (resp.text or "").strip()

        logger.debug(f"[Gateway:{role}] TEXT → OpenAI-Compat ({model})")
        client = self._get_oai_client(api_key, base_url)
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        def _call():
            return client.chat.completions.create(
                model=model, messages=messages,
                temperature=effective_temp, max_tokens=max_toks,
            )

        resp = _retry(_call, op=f"oai.generate_text[{role}]")
        usage = self._extract_usage_openai(resp)
        self.last_usage = usage
        self._emit({
            "event": "llm_call", "role": role, "model": model, "kind": "text",
            "scene_num": scene_num, "duration_s": round(time.time() - t0, 3),
            "usage": usage, "provider": "openai-compat",
        })
        return (resp.choices[0].message.content or "").strip()

    # -------------------------------------------------------------------------
    # Public API: critique_image
    # -------------------------------------------------------------------------

    def critique_image(self, prompt: str, image_path: str,
                        system_instruction: str = "",
                        scene_num: Optional[int] = None) -> Dict[str, Any]:
        """Send an image + prompt for JSON critique. Critic role only."""
        model = self.critic_model
        max_toks = _ROLE_MAX_TOKENS.get("critic", 2048)
        t0 = time.time()

        # Path A: Native Gemini — pass system_instruction via config, image as Part.from_bytes
        if self.gemini_client and model.startswith("gemini-"):
            logger.debug(f"[Gateway:critic] VISION → Native Gemini ({model})")
            img_path = Path(image_path)
            mime_type = "image/png" if img_path.suffix.lower() == ".png" else "image/jpeg"
            with open(img_path, "rb") as f:
                image_bytes = f.read()

            contents = [
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                prompt,
            ]

            def _call():
                cfg_kwargs = dict(
                    response_mime_type="application/json",
                    max_output_tokens=max_toks,
                    temperature=0.3,  # analytical
                )
                if system_instruction:
                    cfg_kwargs["system_instruction"] = system_instruction
                return self.gemini_client.models.generate_content(
                    model=model, contents=contents,
                    config=types.GenerateContentConfig(**cfg_kwargs),
                )

            resp = _retry(_call, op=f"gemini.critique_image")
            usage = self._extract_usage_gemini(resp)
            self.last_usage = usage
            self._emit({
                "event": "llm_call", "role": "critic", "model": model, "kind": "vision",
                "scene_num": scene_num, "duration_s": round(time.time() - t0, 3),
                "usage": usage, "provider": "gemini-native",
            })
            return extract_json(resp.text)

        # Path B: OpenAI-compat vision
        logger.warning("[Gateway:critic] VISION → OpenAI-Compat fallback (variable support)")
        client = self._get_oai_client(self._critic_key, self._critic_base)
        import base64
        with open(image_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
        mime_type = "image/png" if str(image_path).lower().endswith('.png') else "image/jpeg"
        data_uri = f"data:{mime_type};base64,{encoded_string}"

        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": data_uri, "detail": "high"}},
            ],
        })

        def _call():
            try:
                return client.chat.completions.create(
                    model=model, messages=messages,
                    response_format={"type": "json_object"},
                    temperature=0.3,
                    max_tokens=max_toks,
                )
            except openai.BadRequestError as e:
                if "response_format" in str(e).lower() or "json" in str(e).lower():
                    logger.error(
                        f"[Gateway:critic] Model {model} on {self._critic_base} "
                        f"rejected JSON mode for vision. Use Gemini or Claude Sonnet 4."
                    )
                    raise RuntimeError("Vision model does not support enforced JSON output.") from e
                raise

        resp = _retry(_call, op="oai.critique_image")
        usage = self._extract_usage_openai(resp)
        self.last_usage = usage
        self._emit({
            "event": "llm_call", "role": "critic", "model": model, "kind": "vision",
            "scene_num": scene_num, "duration_s": round(time.time() - t0, 3),
            "usage": usage, "provider": "openai-compat",
        })
        return extract_json(resp.choices[0].message.content)
