"""
Robust JSON extraction for LLM responses.

Every module that parses JSON from any LLM (Gemini, OpenAI, Claude, etc.)
MUST use `extract_json()` instead of bare `json.loads()`.

This handles the common garbage that LLMs wrap around valid JSON:
  - Markdown code fences (```json ... ```)
  - Trailing commas before } or ]
  - Literal newlines/tabs inside string values
  - BOM and zero-width characters
  - Stray text wrapping the JSON object
"""

import json
import re
import logging
from typing import Dict

logger = logging.getLogger(__name__)


def _fix_unescaped_newlines(text: str) -> str:
    """Escape literal newlines/tabs inside JSON string values.

    Walks char-by-char tracking quote state. Any raw newline, carriage
    return, or tab inside a quoted string is replaced with its escaped
    form so json.loads won't choke on 'Unterminated string'.
    """
    out = []
    in_string = False
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == '"' and (i == 0 or text[i - 1] != '\\'):
            in_string = not in_string
            out.append(ch)
        elif in_string and ch == '\n':
            out.append('\\n')
        elif in_string and ch == '\r':
            out.append('\\r')
        elif in_string and ch == '\t':
            out.append('\\t')
        else:
            out.append(ch)
        i += 1
    return ''.join(out)


def extract_json(text: str) -> Dict:
    """Robustly extract a JSON object from an LLM response string.

    Use this EVERYWHERE instead of json.loads() when parsing LLM output.

    Handles:
    - Markdown code fences (```json ... ```)
    - Leading/trailing whitespace and BOM
    - Trailing commas before closing braces/brackets
    - Literal newlines inside string values (Gemini's favorite quirk)
    - Stray wrapper text around the JSON
    """
    if not text or not text.strip():
        raise ValueError("Empty response text — LLM returned nothing")

    cleaned = text.strip()

    # Strip markdown code fences
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", cleaned, re.DOTALL)
    if fence_match:
        cleaned = fence_match.group(1).strip()

    # Strip BOM and zero-width chars
    cleaned = cleaned.lstrip("\ufeff\u200b")

    # Remove trailing commas before } or ]
    cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)

    # Fix literal newlines inside JSON string values
    cleaned = _fix_unescaped_newlines(cleaned)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as first_err:
        # Layer 2: find the outermost { ... }
        brace_match = re.search(r"(\{.*\})", cleaned, re.DOTALL)
        if brace_match:
            inner = _fix_unescaped_newlines(brace_match.group(1))
            inner = re.sub(r",\s*([}\]])", r"\1", inner)
            try:
                return json.loads(inner)
            except json.JSONDecodeError:
                pass

        # Layer 3: json_repair library (handles truncated JSON, missing quotes, etc.)
        try:
            import json_repair as jr
            repaired = jr.loads(cleaned)
            if isinstance(repaired, dict):
                logger.info("✅ json_repair library salvaged the response")
                return repaired
        except ImportError:
            logger.debug("json_repair library not installed — skipping Layer 3")
        except Exception as repair_err:
            logger.debug(f"json_repair library failed: {repair_err}")

        # Log the problematic response for debugging
        logger.error(f"JSON extraction failed. First 500 chars of response:\n{text[:500]}")
        raise first_err
