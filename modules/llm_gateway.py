"""
LLM Gateway Module
==================

Centralizes all LLM API client instantiations, fallback logic, and prompt execution.
Replaces fragmented Gemini/OpenRouter logic previously scattered across:
- Orchestrator
- SceneParser
- ArtDirector
- StoryBible
"""

import logging
import os
import re
from typing import Dict, Optional, Tuple, Any
from pathlib import Path

import openai
from google import genai
from google.genai import types

from .json_repair import extract_json

logger = logging.getLogger(__name__)


def _resolve_env(val: str) -> str:
    """Expand ${VAR} patterns to actual env values."""
    if not val:
        return val
    return re.sub(r'\$\{(\w+)\}', lambda m: os.environ.get(m.group(1), ''), val)


class LLMGateway:
    """
    Unified manager for all text generation, JSON parsing, and vision critique operations.
    Handles automatic fallback from native Gemini SDK to OpenAI-compatible endpoints.
    """

    def __init__(self, config: dict, parser_override: str = None, critic_override: str = None):
        self.config = config
        
        # 1. Resolve Credentials
        oai_cfg = config.get("openai", {})
        or_cfg = config.get("openrouter", {})
        
        oai_key = _resolve_env(oai_cfg.get("api_key", "")) or os.environ.get("OPENAI_API_KEY", "")
        or_key = _resolve_env(or_cfg.get("api_key", "")) or os.environ.get("OPENROUTER_API_KEY", "")
        gemini_key = os.environ.get("GEMINI_API_KEY", "")
        
        # 2. Determine Primary Framework
        if gemini_key:
            self.primary_key = gemini_key
            self.primary_base = "https://generativelanguage.googleapis.com/v1beta/openai/"
            default_parser = "gemini-3.1-pro-preview"
            default_critic = "gemini-2.5-flash"
            logger.info("Gateway: Using direct Gemini API")
        elif oai_key:
            self.primary_key = oai_key
            self.primary_base = "https://api.openai.com/v1"
            default_parser = oai_cfg.get("parser_model", "gpt-4.1-mini")
            default_critic = oai_cfg.get("critic_model", "gpt-4.1-mini")
            logger.info("Gateway: Using direct OpenAI API")
        elif or_key:
            self.primary_key = or_key
            self.primary_base = or_cfg.get("base_url", "https://openrouter.ai/api/v1")
            default_parser = or_cfg.get("parser_model", "openai/gpt-4o")
            default_critic = or_cfg.get("critic_model", "openai/gpt-4o")
            logger.info("Gateway: Using OpenRouter API")
        else:
            raise ValueError("No API key found. Set GEMINI_API_KEY, OPENAI_API_KEY, or OPENROUTER_API_KEY in .env.")

        # 3. Resolve Models (with sidebar overrides)
        self.parser_model, self._parser_key, self._parser_base = self._resolve_model_route(
            parser_override or default_parser, gemini_key, oai_key, or_key, or_cfg
        )
        self.critic_model, self._critic_key, self._critic_base = self._resolve_model_route(
            critic_override or default_critic, gemini_key, oai_key, or_key, or_cfg
        )

        # 4. Initialize Core Clients
        self.gemini_client = None
        if gemini_key:
            try:
                self.gemini_client = genai.Client(api_key=gemini_key)
                logger.info("✅ Native Gemini SDK initialized in Gateway")
            except Exception as e:
                logger.warning(f"Failed to init native Gemini SDK: {e}")

        # OpenAI compatible clients (lazy loaded if needed)
        self._oai_clients = {}

    def _resolve_model_route(self, model_name: str, gemini_key: str, oai_key: str, or_key: str, or_cfg: dict) -> Tuple[str, str, str]:
        """Route model to correct API endpoint."""
        gemini_base = "https://generativelanguage.googleapis.com/v1beta/openai/"
        if model_name.startswith("google/gemini-") and gemini_key:
            return model_name.replace("google/", ""), gemini_key, gemini_base
        if model_name.startswith("gemini-") and gemini_key:
            return model_name, gemini_key, gemini_base
        if model_name.startswith("gpt-") and oai_key:
            return model_name, oai_key, "https://api.openai.com/v1"
        return model_name, or_key or self.primary_key, or_cfg.get("base_url", "https://openrouter.ai/api/v1")

    def _get_oai_client(self, api_key: str, base_url: str) -> openai.OpenAI:
        """Get or create an OpenAI client for a specific endpoint."""
        cache_key = f"{base_url}_{api_key[:5]}"
        if cache_key not in self._oai_clients:
            self._oai_clients[cache_key] = openai.OpenAI(
                api_key=api_key,
                base_url=base_url,
                timeout=60.0,
                max_retries=1,
            )
        return self._oai_clients[cache_key]

    # -------------------------------------------------------------------------
    # Unified Generation Methods
    # -------------------------------------------------------------------------

    def generate_json(self, prompt: str, system_instruction: str = "", role: str = "parser") -> Dict[str, Any]:
        """Generate structured JSON. Uses Native Gemini SDK if available, falls back to OpenAI-compat."""
        model = self.parser_model if role == "parser" else self.critic_model
        
        # Path A: Native Gemini
        if self.gemini_client and model.startswith("gemini-"):
            logger.debug(f"[Gateway] JSON Request to Native Gemini ({model})")
            contents = []
            if system_instruction:
                contents.append(types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=system_instruction + "\n\n" + prompt)]
                ))
            else:
                contents.append(prompt)
                
            response = self.gemini_client.models.generate_content(
                model=model,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    max_output_tokens=12000,
                    temperature=0.7,
                ),
            )
            return extract_json(response.text)

        # Path B: OpenAI Compatible Endpoint
        logger.debug(f"[Gateway] JSON Request to OpenAI-Compat ({model})")
        api_key = self._parser_key if role == "parser" else self._critic_key
        base_url = self._parser_base if role == "parser" else self._critic_base
        client = self._get_oai_client(api_key, base_url)
        
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.7,
            max_tokens=12000
        )
        return extract_json(response.choices[0].message.content)

    def generate_text(self, prompt: str, system_instruction: str = "", role: str = "critic", temp: float = 0.7) -> str:
        """Generate raw text. Used for prompt rewriting and story generation."""
        model = self.critic_model if role == "critic" else self.parser_model
        
        # Path A: Native Gemini
        if self.gemini_client and model.startswith("gemini-"):
            logger.debug(f"[Gateway] Text Request to Native Gemini ({model})")
            contents = []
            if system_instruction:
                contents.append(types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=system_instruction + "\n\n" + prompt)]
                ))
            else:
                contents.append(prompt)
                
            response = self.gemini_client.models.generate_content(
                model=model,
                contents=contents,
                config=types.GenerateContentConfig(
                    temperature=temp,
                ),
            )
            return response.text.strip()

        # Path B: OpenAI Compatible Endpoint
        logger.debug(f"[Gateway] Text Request to OpenAI-Compat ({model})")
        api_key = self._critic_key if role == "critic" else self._parser_key
        base_url = self._critic_base if role == "critic" else self._parser_base
        client = self._get_oai_client(api_key, base_url)
        
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})
        
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temp,
        )
        return response.choices[0].message.content.strip()

    def critique_image(self, prompt: str, image_path: str, system_instruction: str = "") -> Dict[str, Any]:
        """Send an image and a prompt for JSON critique."""
        model = self.critic_model
        
        # Path A: Native Gemini (Required for vision + JSON)
        if self.gemini_client and model.startswith("gemini-"):
            logger.debug(f"[Gateway] Vision Critique Request to Native Gemini ({model})")
            img_path = Path(image_path)
            mime_type = "image/png" if img_path.suffix.lower() == ".png" else "image/jpeg"
            
            with open(img_path, "rb") as f:
                image_bytes = f.read()
                
            contents = [
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                 system_instruction + "\n\n" + prompt if system_instruction else prompt,
            ]
            
            response = self.gemini_client.models.generate_content(
                model=model,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    max_output_tokens=1500,
                    temperature=0.3, # Low temp for analytical grading
                ),
            )
            return extract_json(response.text)
            
        # Path B: OpenAI Compatible (Warning: OpenRouter vision support varies wildly)
        logger.warning("[Gateway] Falling back to OpenAI-Compat for Vision Critique. This may be unstable depending on the model.")
        api_key = self._critic_key
        base_url = self._critic_base
        client = self._get_oai_client(api_key, base_url)
        
        import base64
        with open(image_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
            
        mime_type = "image/png" if str(image_path).lower().endswith('.png') else "image/jpeg"
        data_uri = f"data:{mime_type};base64,{encoded_string}"
        
        sys_msg = system_instruction + "\n\n" if system_instruction else ""
        
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": sys_msg + prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": data_uri,
                                    "detail": "high"
                                }
                            }
                        ]
                    }
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
            )
            return extract_json(response.choices[0].message.content)
            
        except openai.BadRequestError as e:
            if "response_format" in str(e).lower() or "json" in str(e).lower():
                logger.error(f"[Gateway] Model {model} on {base_url} rejected JSON mode for vision. Try using native Gemini.")
                raise RuntimeError("Vision model does not support enforced JSON output. Switch to Gemini.") from e
            raise
