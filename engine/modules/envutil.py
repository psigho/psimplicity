"""
Single source of truth for ${ENV_VAR} substitution.

Before this module the same regex lived in four places (app.py:38, app.py
inline ×2, orchestrator.py:198, llm_gateway.py:43) with two different
unset-variable behaviours. Everything now routes through here.
"""

import os
import re

_PATTERN = re.compile(r'\$\{(\w+)\}')


def resolve_env_text(text: str, keep_unset: bool = False) -> str:
    """Expand ${VAR} in a string from os.environ.

    keep_unset=False -> unknown vars become '' (the orchestrator/gateway behaviour)
    keep_unset=True  -> unknown vars are left as-is, e.g. '${VAR}' (the app.py
                        config-loading behaviour, so a missing key is visible
                        rather than silently blanked before json.loads).
    """
    if not text:
        return text

    def _repl(m):
        name = m.group(1)
        if name in os.environ:
            return os.environ[name]
        return m.group(0) if keep_unset else ''

    return _PATTERN.sub(_repl, text)


def resolve_env_obj(obj):
    """Recursively resolve ${VAR} in every string inside a dict/list/str."""
    if isinstance(obj, str):
        return resolve_env_text(obj)
    if isinstance(obj, dict):
        return {k: resolve_env_obj(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [resolve_env_obj(v) for v in obj]
    return obj
