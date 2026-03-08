"""
Image Provider Module
Abstract base + Imagen 3 implementation. Designed for swappable image generators.
"""

import io
import json
import logging
import base64
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional
from PIL import Image
from PIL import Image
import re
import os

def _resolve_env(val: str) -> str:
    """Expand ${VAR} patterns to actual env values."""
    if not val:
        return val
    return re.sub(r'\$\{(\w+)\}', lambda m: os.environ.get(m.group(1), ''), val)

logger = logging.getLogger(__name__)


class ImageProvider(ABC):
    """Abstract base class for image generation providers."""

    @abstractmethod
    def generate(self, prompt: str, negative_prompt: str = "", output_path: str = None,
                 reference_images: list = None) -> str:
        """Generate an image from a prompt. Returns path to saved image.

        Args:
            reference_images: Optional list of file paths to reference images.
                              When provided, the generator should use these as
                              visual input (image-to-image / multimodal).
        """
        pass

    @abstractmethod
    def name(self) -> str:
        pass


class Imagen3Provider(ImageProvider):
    """Google Imagen 3 via Vertex AI."""

    def __init__(self, service_account_path: str, project_id: str, region: str = "us-central1"):
        import vertexai
        from google.oauth2 import service_account
        from vertexai.preview.vision_models import ImageGenerationModel

        creds = service_account.Credentials.from_service_account_file(service_account_path)
        vertexai.init(project=project_id, location=region, credentials=creds)

        self.model = ImageGenerationModel.from_pretrained("imagen-3.0-generate-001")
        self._name = "Imagen 3"
        logger.info(f"Initialized {self._name}")

    def generate(self, prompt: str, negative_prompt: str = "", output_path: str = None) -> str:
        """Generate image using Imagen 3."""
        logger.info(f"Generating image with {self._name}...")

        kwargs = {"prompt": prompt, "number_of_images": 1}
        if negative_prompt:
            kwargs["negative_prompt"] = negative_prompt

        response = self.model.generate_images(**kwargs)

        if not response.images:
            raise RuntimeError("Imagen 3 returned no images")

        img = response.images[0]

        if output_path is None:
            output_path = "output.png"

        # Save the image
        img.save(output_path)
        logger.info(f"Image saved to {output_path}")
        return output_path

    def name(self) -> str:
        return self._name


class DallEProvider(ImageProvider):
    """OpenAI DALL-E 3 provider (alternative / future swap)."""

    def __init__(self, api_key: str):
        import openai
        self.client = openai.OpenAI(api_key=api_key)
        self._name = "DALL-E 3"
        logger.info(f"Initialized {self._name}")

    def generate(self, prompt: str, negative_prompt: str = "", output_path: str = None) -> str:
        """Generate image using DALL-E 3."""
        import requests

        logger.info(f"Generating image with {self._name}...")

        full_prompt = prompt
        if negative_prompt:
            full_prompt += f"\n\nAvoid: {negative_prompt}"

        response = self.client.images.generate(
            model="dall-e-3",
            prompt=full_prompt,
            size="1792x1024",
            quality="hd",
            n=1
        )

        image_url = response.data[0].url

        if output_path is None:
            output_path = "output.png"

        img_data = requests.get(image_url).content
        with open(output_path, "wb") as f:
            f.write(img_data)

        logger.info(f"Image saved to {output_path}")
        return output_path

    def name(self) -> str:
        return self._name


class GeminiImageProvider(ImageProvider):
    """Google Gemini 3 Pro Image (Nano Banana Pro) via Vertex AI generateContent."""

    def __init__(self, service_account_path: str, project_id: str,
                 region: str = "us-central1", model: str = "gemini-3-pro-image-preview"):
        import vertexai
        from google.oauth2 import service_account
        from vertexai.generative_models import GenerativeModel

        creds = service_account.Credentials.from_service_account_file(service_account_path)
        vertexai.init(project=project_id, location=region, credentials=creds)

        self.model = GenerativeModel(model)
        self._model_name = model
        self._name = "Nano Banana Pro"
        logger.info(f"Initialized {self._name} ({model})")

    def generate(self, prompt: str, negative_prompt: str = "", output_path: str = None) -> str:
        """Generate image using Gemini 3 Pro Image (Nano Banana Pro)."""
        from vertexai.generative_models import GenerationConfig

        logger.info(f"Generating image with {self._name}...")

        full_prompt = f"Generate a high-quality image: {prompt}"
        if negative_prompt:
            full_prompt += f"\n\nAvoid: {negative_prompt}"

        generation_config = GenerationConfig(
            response_modalities=["IMAGE", "TEXT"],
            temperature=1.0,
        )

        response = self.model.generate_content(
            full_prompt,
            generation_config=generation_config,
        )

        # Extract image from multimodal response
        if not response.candidates:
            raise RuntimeError("Nano Banana Pro returned no candidates")

        candidate = response.candidates[0]

        # Safety filter or empty response — content/parts can be None
        if not getattr(candidate, "content", None) or not getattr(candidate.content, "parts", None):
            finish = getattr(candidate, "finish_reason", "UNKNOWN")
            safety = getattr(response, "prompt_feedback", None)
            logger.warning(f"Gemini returned empty content. finish_reason={finish}, safety={safety}")
            raise RuntimeError(
                f"Nano Banana Pro returned candidate with no content "
                f"(finish_reason={finish}). Prompt may have been safety-filtered."
            )

        img_data = None
        for part in candidate.content.parts:
            if hasattr(part, 'inline_data') and part.inline_data and \
               part.inline_data.mime_type.startswith("image/"):
                img_data = part.inline_data.data
                break

        if img_data is None:
            raise RuntimeError("Nano Banana Pro returned no image in response")

        if output_path is None:
            output_path = "output.png"

        img = Image.open(io.BytesIO(img_data))
        img.save(output_path)
        logger.info(f"Image saved to {output_path}")
        return output_path

    def name(self) -> str:
        return self._name


class GeminiAPIKeyProvider(ImageProvider):
    """Gemini image generation via google-genai SDK with a plain API key.

    No service account needed — just paste a key from aistudio.google.com.
    """

    def __init__(self, api_key: str, model: str = "gemini-3-pro-image-preview"):
        from google import genai

        self.client = genai.Client(api_key=api_key)
        self._model = model
        self._name = "Nano Banana Pro (API Key)"
        logger.info(f"Initialized {self._name} ({model})")

    _MAX_RETRIES = 4
    _BASE_DELAY = 5  # seconds — short for paid GCP tier

    def generate(self, prompt: str, negative_prompt: str = "", output_path: str = None,
                 reference_images: list = None) -> str:
        """Generate image using Gemini via API key with rate-limit retry."""
        import time as _time
        from google.genai import types

        logger.info(f"Generating image with {self._name}...")

        full_prompt = f"Generate a high-quality image: {prompt}"
        if negative_prompt:
            full_prompt += f"\n\nAvoid: {negative_prompt}"

        # Build multimodal contents: reference images + text prompt
        contents_parts = []
        if reference_images:
            for img_path in reference_images:
                try:
                    ref_img = Image.open(img_path)
                    contents_parts.append(ref_img)
                    logger.info(f"Added reference image: {img_path}")
                except Exception as e:
                    logger.warning(f"Could not load reference image {img_path}: {e}")
            # Prepend instruction about reference images
            full_prompt = ("Use the provided reference image(s) as visual guidance. "
                          "The product bottle shown MUST match the reference exactly — "
                          "same shape, label design, color, and proportions. "
                          "Generate the scene around this real product.\n\n" + full_prompt)
        contents_parts.append(full_prompt)
        contents = contents_parts if len(contents_parts) > 1 else full_prompt

        last_err = None
        for attempt in range(1, self._MAX_RETRIES + 1):
            try:
                response = self.client.models.generate_content(
                    model=self._model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        response_modalities=["IMAGE", "TEXT"],
                        temperature=1.0,
                    ),
                )
                break  # success
            except Exception as e:
                last_err = e
                err_str = str(e).lower()
                is_rate_limit = "429" in err_str or "rate" in err_str or "resource_exhausted" in err_str
                if is_rate_limit and attempt < self._MAX_RETRIES:
                    wait = self._BASE_DELAY * (2 ** (attempt - 1))  # 15, 30, 60
                    logger.warning(f"Rate limited — waiting {wait}s before retry {attempt+1}/{self._MAX_RETRIES}")
                    _time.sleep(wait)
                    continue
                raise  # non-rate-limit error or final attempt

        # Extract image from response parts
        if not response.candidates:
            raise RuntimeError("Gemini API returned no candidates")

        candidate = response.candidates[0]

        # Safety filter or empty response — content/parts can be None
        if not getattr(candidate, "content", None) or not getattr(candidate.content, "parts", None):
            finish = getattr(candidate, "finish_reason", "UNKNOWN")
            safety = getattr(response, "prompt_feedback", None)
            logger.warning(f"Gemini returned empty content. finish_reason={finish}, safety={safety}")
            raise RuntimeError(
                f"Gemini API returned candidate with no content "
                f"(finish_reason={finish}). Prompt may have been safety-filtered."
            )

        img_data = None
        for part in candidate.content.parts:
            if part.inline_data and part.inline_data.mime_type.startswith("image/"):
                img_data = part.inline_data.data
                break

        if img_data is None:
            raise RuntimeError("Gemini API returned no image in response")

        if output_path is None:
            output_path = "output.png"

        img = Image.open(io.BytesIO(img_data))
        img.save(output_path)
        logger.info(f"Image saved to {output_path}")
        return output_path

    def name(self) -> str:
        return self._name


class SeedreamProvider(ImageProvider):
    """ByteDance Seedream 4.5 via OpenRouter (chat.completions + modalities).

    OpenRouter image-gen models use chat.completions.create() with
    modalities=["image"].  The generated image comes back as a base64
    data-URL inside the assistant message content.

    More lenient safety filters than Gemini for illustrated/stylized content.
    Pricing: ~$0.04 per image via OpenRouter.
    """

    _MAX_RETRIES = 3
    _BASE_DELAY = 4  # seconds

    def __init__(self, api_key: str, base_url: str = "https://openrouter.ai/api/v1",
                 model: str = "bytedance-seed/seedream-4.5"):
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._name = "Seedream 4.5"
        logger.info(f"Initialized {self._name} ({model}) via {base_url}")

    def generate(self, prompt: str, negative_prompt: str = "", output_path: str = None) -> str:
        """Generate image using Seedream 4.5 via OpenRouter chat.completions."""
        import time as _time
        import requests

        logger.info(f"Generating image with {self._name}...")

        full_prompt = prompt
        if negative_prompt:
            full_prompt += f"\n\nNegative: {negative_prompt}"

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": full_prompt}],
            "modalities": ["image"],
            "max_tokens": 4096,
        }

        last_err = None
        resp_json = None
        for attempt in range(1, self._MAX_RETRIES + 1):
            try:
                resp = requests.post(
                    f"{self._base_url}/chat/completions",
                    headers=headers, json=payload, timeout=120,
                )
                resp.raise_for_status()
                resp_json = resp.json()
                break
            except Exception as e:
                last_err = e
                err_str = str(e).lower()
                is_rate_limit = "429" in err_str or "rate" in err_str
                if is_rate_limit and attempt < self._MAX_RETRIES:
                    wait = self._BASE_DELAY * (2 ** (attempt - 1))
                    logger.warning(f"Rate limited — waiting {wait}s before retry {attempt+1}/{self._MAX_RETRIES}")
                    _time.sleep(wait)
                    continue
                logger.error(f"Seedream generation failed: {e}")
                raise

        if resp_json is None:
            raise RuntimeError(f"Seedream failed after {self._MAX_RETRIES} attempts: {last_err}")

        # Extract base64 image from response
        # OpenRouter returns images in: choices[0].message.images[]
        # Each item: {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}
        img_data = None
        choices = resp_json.get("choices", [])
        if choices:
            msg = choices[0].get("message", {})

            # Primary: check message.images[] (OpenRouter documented format)
            images = msg.get("images", [])
            for img_item in images:
                url = ""
                if isinstance(img_item, dict):
                    url = img_item.get("image_url", {}).get("url", "") or img_item.get("url", "")
                if url and "base64" in url:
                    b64_str = url.split(",", 1)[1] if "," in url else url
                    img_data = base64.b64decode(b64_str)
                    break

            # Fallback: check message.content (some providers put it here)
            if img_data is None:
                content = msg.get("content", "")
                if isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict):
                            url = (part.get("image_url", {}).get("url", "")
                                   if part.get("type") == "image_url"
                                   else part.get("url", ""))
                            if url and "base64" in url:
                                b64_str = url.split(",", 1)[1] if "," in url else url
                                img_data = base64.b64decode(b64_str)
                                break
                elif isinstance(content, str) and content.startswith("data:image"):
                    b64_str = content.split(",", 1)[1] if "," in content else content
                    img_data = base64.b64decode(b64_str)

        if img_data is None:
            logger.error(f"Seedream response keys: {list(resp_json.get('choices', [{}])[0].get('message', {}).keys())}")
            logger.error(f"Seedream response (500 chars): {json.dumps(resp_json)[:500]}")
            raise RuntimeError("Seedream returned no image data in response")

        if output_path is None:
            output_path = "output.png"

        img = Image.open(io.BytesIO(img_data))
        img.save(output_path)
        logger.info(f"Image saved to {output_path}")
        return output_path

    def name(self) -> str:
        return self._name


class Imagen3APIKeyProvider(ImageProvider):
    """Google Imagen 3 via google-genai SDK with a plain API key.

    No service account needed — just paste a key from aistudio.google.com.
    """

    def __init__(self, api_key: str, model: str = "imagen-3.0-generate-001"):
        from google import genai

        self.client = genai.Client(api_key=api_key)
        self._model = model
        self._name = "Imagen 3 (API Key)"
        logger.info(f"Initialized {self._name} ({model})")

    def generate(self, prompt: str, negative_prompt: str = "", output_path: str = None) -> str:
        """Generate image using Imagen 3 via API key."""
        from google.genai import types

        logger.info(f"Generating image with {self._name}...")

        config = types.GenerateImagesConfig(
            number_of_images=1,
            negative_prompt=negative_prompt if negative_prompt else None,
        )

        response = self.client.models.generate_images(
            model=self._model,
            prompt=prompt,
            config=config,
        )

        if not response.generated_images:
            raise RuntimeError("Imagen 3 API returned no images")

        img_bytes = response.generated_images[0].image.image_bytes

        if output_path is None:
            output_path = "output.png"

        img = Image.open(io.BytesIO(img_bytes))
        img.save(output_path)
        logger.info(f"Image saved to {output_path}")
        return output_path

    def name(self) -> str:
        return self._name


def create_provider(config: dict) -> ImageProvider:
    """Factory function to create the right provider from config.

    Priority: Seedream > API key mode > Service Account mode.
    """
    # ── Seedream via OpenRouter ────────────────────────────────────────
    if "seedream" in config:
        cfg = config["seedream"]
        return SeedreamProvider(
            api_key=_resolve_env(cfg.get("api_key", "")),
            base_url=_resolve_env(cfg.get("base_url", "https://openrouter.ai/api/v1")),
            model=cfg.get("model", "bytedance-seed/seedream-4.5"),
        )

    # ── API Key mode (simple — no service account needed) ─────────────
    if "gemini_api_key" in config:
        cfg = config["gemini_api_key"]
        api_key = _resolve_env(cfg.get("api_key", ""))
        engine = cfg.get("engine", "gemini-image")  # "gemini-image" or "imagen-3"

        if not api_key:
            raise ValueError("GEMINI_API_KEY is set in config but empty. "
                             "Get one at https://aistudio.google.com")

        if engine == "imagen-3":
            return Imagen3APIKeyProvider(
                api_key=api_key,
                model=cfg.get("model", "imagen-3.0-generate-001"),
            )
        else:
            return GeminiAPIKeyProvider(
                api_key=api_key,
                model=cfg.get("model", "gemini-3-pro-image-preview"),
            )

    # ── Service Account mode (existing behavior) ──────────────────────
    if "gemini_image" in config:
        cfg = config["gemini_image"]
        return GeminiImageProvider(
            service_account_path=cfg["service_account_path"],
            project_id=cfg["project_id"],
            region=cfg.get("region", "us-central1"),
            model=cfg.get("model", "gemini-3-pro-image-preview")
        )
    elif "imagen" in config:
        cfg = config["imagen"]
        return Imagen3Provider(
            service_account_path=cfg["service_account_path"],
            project_id=cfg["project_id"],
            region=cfg.get("region", "us-central1")
        )
    elif "dalle" in config:
        return DallEProvider(api_key=_resolve_env(config["dalle"].get("api_key", "")))
    else:
        raise ValueError("No valid image provider found in config. "
                         "Set a GEMINI_API_KEY or configure a provider in the sidebar.")
