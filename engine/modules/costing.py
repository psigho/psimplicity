"""
Cost control for the pipeline.

Three concerns the engine had no answer for before (see PSIMPLICITY_AUDIT
2026-06-10, the P0 gap):

  1. image_unit_cost / estimate_run_cost — a *pre-run* estimate so the operator
     sees "~$X, confirm?" before spending. The config already carries every
     price; nothing used them ahead of a run.
  2. BudgetTracker / BudgetExceeded — a hard USD ceiling that aborts mid-run.
     usd was accumulated but never compared to a cap.
  3. RateLimiter — a shared min-interval gate to replace the blanket
     `time.sleep(1.5)` calls, so scenes can run in parallel without exceeding
     provider rate limits.

All pure / dependency-free so they unit-test offline with no API spend.
"""

import threading
import time
from typing import Dict, Optional


class BudgetExceeded(Exception):
    """Raised inside a run when the accumulated USD crosses the budget ceiling."""


# ── pricing lookups ──────────────────────────────────────────────────────────
def image_unit_cost(config: dict, image_id: str = "", config_key: str = "") -> float:
    """USD per generated image for the selected engine.

    Prefers an exact `id` match (e.g. 'gpt-image-2'); falls back to the first
    generator whose `config_key` matches (e.g. 'gemini_image' is shared by
    'gemini-image' and 'nano-banana-pro'); else 0.0.
    """
    gens = config.get("available_models", {}).get("image_generators", [])
    if image_id:
        for g in gens:
            if g.get("id") == image_id:
                return float(g.get("usd_per_image", 0.0) or 0.0)
    if config_key:
        # 'gemini_api_key' is the runtime-injected alias for the 'gemini_image' /
        # 'imagen' config keys; normalise so the lookup still resolves a price.
        norm = {"gemini_api_key": "gemini_image"}.get(config_key, config_key)
        for g in gens:
            if g.get("config_key") in (config_key, norm):
                return float(g.get("usd_per_image", 0.0) or 0.0)
    return 0.0


def model_price(config: dict, model_id: str) -> Dict[str, float]:
    """{'in': usd/1M, 'out': usd/1M} for a parser/critic model id (prefix-tolerant)."""
    parsers = config.get("available_models", {}).get("parsers", [])
    bare = model_id.split("/", 1)[-1] if "/" in model_id else model_id
    for m in parsers:
        mid = m.get("id", "")
        if mid == model_id or mid == bare or mid.split("/", 1)[-1] == bare:
            return {
                "in": float(m.get("usd_per_million_input_tokens", 0.0) or 0.0),
                "out": float(m.get("usd_per_million_output_tokens", 0.0) or 0.0),
            }
    return {"in": 0.0, "out": 0.0}


# Heuristic token sizes per LLM call kind (only used for the *estimate*; the
# live run records exact usage from the provider).
_LLM_ASSUMED = {
    "parse":   {"in": 2500, "out": 1800},
    "bible":   {"in": 1800, "out": 1200},
    "critique": {"in": 1900, "out": 700},
    "surgery": {"in": 1300, "out": 500},
}


def estimate_run_cost(config: dict, num_scenes: int, images_per_scene: int,
                      max_retries: int, image_id: str = "", config_key: str = "",
                      parser_model: str = "", critic_model: str = "") -> dict:
    """Rough pre-run cost. Returns a breakdown dict; total is image-dominated and
    clearly an estimate (LLM token counts are assumed, image counts are bounded).

    typical: key visual settles in ~2 attempts. max: every key visual burns all
    `max_retries`. Supplementary visuals (images_per_scene-1) generate once each.
    """
    num_scenes = max(0, int(num_scenes))
    images_per_scene = max(1, int(images_per_scene))
    max_retries = max(1, int(max_retries))
    typical_attempts = min(2, max_retries)
    supp = images_per_scene - 1

    unit = image_unit_cost(config, image_id, config_key)
    images_typical = num_scenes * (supp + typical_attempts)
    images_max = num_scenes * (supp + max_retries)
    img_cost_typical = images_typical * unit
    img_cost_max = images_max * unit

    # LLM side (small relative to images for image-heavy runs)
    p = model_price(config, parser_model) if parser_model else {"in": 0.0, "out": 0.0}
    c = model_price(config, critic_model or parser_model)

    def _call(kind, price):
        a = _LLM_ASSUMED[kind]
        return (a["in"] / 1e6) * price["in"] + (a["out"] / 1e6) * price["out"]

    llm_typical = (
        _call("parse", p) + _call("bible", p)
        + num_scenes * typical_attempts * _call("critique", c)
        + num_scenes * max(0, typical_attempts - 1) * _call("surgery", c)
    )
    llm_max = (
        _call("parse", p) + _call("bible", p)
        + num_scenes * max_retries * _call("critique", c)
        + num_scenes * max(0, max_retries - 1) * _call("surgery", c)
    )

    return {
        "image_unit_usd": round(unit, 4),
        "images_typical": images_typical,
        "images_max": images_max,
        "image_cost_typical": round(img_cost_typical, 4),
        "image_cost_max": round(img_cost_max, 4),
        "llm_cost_typical": round(llm_typical, 4),
        "llm_cost_max": round(llm_max, 4),
        "total_typical": round(img_cost_typical + llm_typical, 4),
        "total_max": round(img_cost_max + llm_max, 4),
    }


# ── budget enforcement ───────────────────────────────────────────────────────
class BudgetTracker:
    """Thread-safe USD accumulator with an optional hard ceiling."""

    def __init__(self, ceiling_usd: float = 0.0):
        self.ceiling = float(ceiling_usd or 0.0)
        self._spent = 0.0
        self._lock = threading.Lock()

    @property
    def spent(self) -> float:
        with self._lock:
            return self._spent

    def add(self, usd: float) -> float:
        with self._lock:
            self._spent += float(usd or 0.0)
            return self._spent

    def check(self):
        """Raise BudgetExceeded if a ceiling is set and already crossed."""
        if self.ceiling and self.spent >= self.ceiling:
            raise BudgetExceeded(
                f"spent ${self.spent:.2f} >= budget ceiling ${self.ceiling:.2f}"
            )

    def would_exceed(self, next_usd: float) -> bool:
        if not self.ceiling:
            return False
        return (self.spent + float(next_usd or 0.0)) > self.ceiling


# ── shared rate limiter ──────────────────────────────────────────────────────
class RateLimiter:
    """Global min-interval gate. Serializes spacing across threads so parallel
    scenes can't burst past the provider's rate limit. min_interval<=0 disables.
    """

    def __init__(self, min_interval: float = 0.0,
                 _clock=time.monotonic, _sleep=time.sleep):
        self.min_interval = float(min_interval or 0.0)
        self._last = None  # None = never called (clock-origin independent)
        self._lock = threading.Lock()
        self._clock = _clock
        self._sleep = _sleep

    def wait(self):
        if self.min_interval <= 0:
            return
        with self._lock:
            now = self._clock()
            if self._last is not None:
                remaining = self.min_interval - (now - self._last)
                if remaining > 0:
                    self._sleep(remaining)
                    now = self._clock()
            self._last = now
