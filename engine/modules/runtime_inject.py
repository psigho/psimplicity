"""
Shared config loading + runtime image-provider injection.

The launch path and the redo path in app.py each had their own verbatim copy of
"open config → resolve ${ENV} → json.loads → inject the selected image engine's
runtime block". Two copies that had to stay in sync by hand (the audit flagged
this). Both now call through here.
"""

import json
import os

from .envutil import resolve_env_text


def load_config(config_path) -> dict:
    """Read config.json and expand ${ENV_VAR}. keep_unset=True leaves an unknown
    var literal (e.g. '${FOO}') so json stays valid and a missing key is visible
    rather than silently blanked."""
    with open(config_path, encoding="utf-8") as f:
        raw = f.read()
    return json.loads(resolve_env_text(raw, keep_unset=True))


def inject_image_provider_config(config: dict, image_config_key: str,
                                 image_model_id: str = "", env=None):
    """Build the runtime provider block for the selected engine, mutating config
    in place. Returns (effective_config_key, error_message_or_None).

    - gemini_image / imagen + GEMINI_API_KEY  -> injects 'gemini_api_key', remaps key
    - seedream + OPENROUTER_API_KEY           -> injects 'seedream'
    - gpt_image                               -> injects 'gpt_image' (errors if no key)
    """
    env = env if env is not None else os.environ
    key = image_config_key

    gemini = env.get("GEMINI_API_KEY", "")
    if gemini and key in ("gemini_image", "imagen"):
        engine_map = {"gemini_image": "gemini-image", "imagen": "imagen-3"}
        config["gemini_api_key"] = {"api_key": gemini, "engine": engine_map[key]}
        return "gemini_api_key", None

    openrouter = env.get("OPENROUTER_API_KEY", "")
    if openrouter and key == "seedream":
        config["seedream"] = {
            "api_key": openrouter,
            "base_url": "https://openrouter.ai/api/v1",
            "model": "bytedance-seed/seedream-4.5",
        }
        return key, None

    if key == "gpt_image":
        openai_key = env.get("OPENAI_API_KEY", "")
        if not openai_key:
            return key, ("GPT-Image selected but OPENAI_API_KEY is not set in .env. "
                         "Add it, or pick a different Image Engine in the sidebar.")
        config["gpt_image"] = {"api_key": openai_key, "model": image_model_id or "gpt-image-2"}
        return key, None

    return key, None
