"""
Gemini LLM Module — Native Google GenAI SDK wrapper.

Primary LLM provider for all pipeline calls (parser, story bible, art director).
Uses the native google-genai SDK instead of OpenAI-compat shim — fixes JSON
corruption issues with vision+structured output.

Fallback: OpenAI-compatible clients (OpenRouter, OpenAI direct) handled by callers.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Optional

from google import genai
from google.genai import types

from .json_repair import extract_json as _extract_json

logger = logging.getLogger(__name__)


class GeminiLLM:
    """Native Gemini SDK wrapper for reliable JSON generation."""

    def __init__(self, api_key: str, model: str = "gemini-3-flash-preview"):
        self.client = genai.Client(api_key=api_key)
        self.model = model
        logger.info(f"GeminiLLM initialized: model={model}")

    def generate_json(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int = 1500,
        temperature: float = 0.4,
    ) -> Dict:
        """Generate structured JSON from a text prompt.

        Used by: scene_parser, story_bible
        """
        contents = []
        if system:
            contents.append(types.Content(
                role="user",
                parts=[types.Part.from_text(text=system + "\n\n" + prompt)]
            ))
        else:
            contents.append(prompt)

        response = self.client.models.generate_content(
            model=self.model,
            contents=contents,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                max_output_tokens=max_tokens,
                temperature=temperature,
            ),
        )

        return _extract_json(response.text)

    def critique_image(
        self,
        prompt: str,
        image_path: str,
        max_tokens: int = 1500,
        temperature: float = 0.3,
    ) -> Dict:
        """Critique an image with vision + JSON structured output.

        Used by: art_director (the critical path that was breaking)
        """
        img_path = Path(image_path)
        suffix = img_path.suffix.lower()
        mime_type = "image/png" if suffix == ".png" else "image/jpeg"

        with open(img_path, "rb") as f:
            image_bytes = f.read()

        contents = [
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            prompt,
        ]

        response = self.client.models.generate_content(
            model=self.model,
            contents=contents,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                max_output_tokens=max_tokens,
                temperature=temperature,
            ),
        )

        return _extract_json(response.text)
