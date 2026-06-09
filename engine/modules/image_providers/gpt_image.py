"""
GPT-Image provider (OpenAI) — supports gpt-image-1 / gpt-image-1.5 / gpt-image-2.

Created 2026-05-27 as part of the Psimplicity /goal Phase 4.

API surface (per OpenAI docs as of 2026-04):
  - Endpoint: client.images.generate()
  - Models: gpt-image-1, gpt-image-1-mini, gpt-image-1.5, gpt-image-2, gpt-image-2-2026-04-21
  - size: "WIDTHxHEIGHT", both divisible by 16, aspect ratio 1:3..3:1, up to 3840x2160
  - quality: low | medium | high | auto
  - output_format: png | jpeg | webp
  - moderation: low | auto
  - n: 1-10
  - background: transparent | opaque | auto  (gpt-image-* only, requires PNG/WebP)
  - Response: b64_json (always for GPT image models — no `url` option)

Pricing (as of 2026-05, may drift — check current rates):
  gpt-image-2 high:   ~$0.17/image
  gpt-image-2 medium: ~$0.04/image
  gpt-image-2 low:    ~$0.01/image
"""

import io
import base64
import logging
import time as _time
from pathlib import Path
from PIL import Image

from ..image_provider import ImageProvider  # base class

logger = logging.getLogger(__name__)


class GPTImageProvider(ImageProvider):
    """OpenAI GPT-Image family (gpt-image-1, gpt-image-1.5, gpt-image-2, ...)."""

    _MAX_RETRIES = 3
    _BASE_DELAY = 4  # seconds

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-image-2",
        size: str = "1536x1024",
        quality: str = "high",
        output_format: str = "png",
        background: str = "auto",
        moderation: str = "auto",
    ):
        import openai
        self.client = openai.OpenAI(api_key=api_key, max_retries=0)
        self._model = model
        self._size = size
        self._quality = quality
        self._output_format = output_format
        self._background = background
        self._moderation = moderation
        self._name = f"GPT-Image ({model})"
        logger.info(
            f"Initialized {self._name} — size={size} quality={quality} "
            f"format={output_format} bg={background}"
        )

    def name(self) -> str:
        return self._name

    def generate(
        self,
        prompt: str,
        negative_prompt: str = "",
        output_path: str = None,
        reference_images: list = None,
    ) -> str:
        """Generate image via OpenAI Images API. Reference images use the edit endpoint."""
        full_prompt = prompt
        if negative_prompt:
            # gpt-image doesn't have a negative_prompt field — fold into the prompt
            full_prompt += f"\n\nAvoid: {negative_prompt}"

        if output_path is None:
            output_path = "output.png"

        # ── Build the kwargs payload ─────────────────────────────────────
        kwargs = dict(
            model=self._model,
            prompt=full_prompt,
            n=1,
            size=self._size,
            quality=self._quality,
            output_format=self._output_format,
            moderation=self._moderation,
        )
        if self._background and self._background != "auto":
            kwargs["background"] = self._background

        # ── Retry loop for 429 / 5xx ─────────────────────────────────────
        last_err = None
        for attempt in range(1, self._MAX_RETRIES + 1):
            try:
                if reference_images:
                    # Use edit endpoint for image-to-image / refs
                    file_handles = [open(p, "rb") for p in reference_images if Path(p).exists()]
                    try:
                        resp = self.client.images.edit(
                            model=self._model,
                            prompt=full_prompt,
                            image=file_handles if len(file_handles) > 1 else file_handles[0],
                            n=1,
                            size=self._size,
                            quality=self._quality,
                        )
                    finally:
                        for fh in file_handles:
                            try:
                                fh.close()
                            except Exception:
                                pass
                else:
                    resp = self.client.images.generate(**kwargs)
                break
            except Exception as e:
                last_err = e
                msg = str(e).lower()
                is_retryable = (
                    "429" in msg or "rate" in msg or "timeout" in msg or
                    "503" in msg or "502" in msg or "overload" in msg or "temporar" in msg
                )
                if is_retryable and attempt < self._MAX_RETRIES:
                    wait = self._BASE_DELAY * (2 ** (attempt - 1))
                    logger.warning(
                        f"{self._name} retryable error (attempt {attempt}/{self._MAX_RETRIES}) — "
                        f"sleeping {wait}s: {e}"
                    )
                    _time.sleep(wait)
                    continue
                raise
        else:
            raise RuntimeError(f"{self._name} failed after {self._MAX_RETRIES} attempts: {last_err}")

        # ── Decode base64 → PNG file ─────────────────────────────────────
        if not resp.data:
            raise RuntimeError(f"{self._name} returned no data")
        b64 = getattr(resp.data[0], "b64_json", None)
        if not b64:
            raise RuntimeError(f"{self._name} returned a record with no b64_json field")

        img_bytes = base64.b64decode(b64)
        img = Image.open(io.BytesIO(img_bytes))
        img.save(output_path)
        logger.info(f"Image saved to {output_path}")
        return output_path
