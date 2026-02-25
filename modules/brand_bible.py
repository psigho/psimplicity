"""
Brand Bible — Visual DNA Extractor
====================================
Analyze brand reference images (logos, products, campaigns) via Gemini 3 Pro
multimodal to extract a structured Brand Bible JSON that guides image generation.

Usage:
    from modules.brand_bible import analyze_brand_images
    brand_bible = analyze_brand_images(image_paths, api_key)
"""

import base64
import json
import logging
import os
import re
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


BRAND_BIBLE_PROMPT = """You are a senior Brand Strategist and Visual Director.

Analyze the provided brand image(s) — these may include logos, product packaging, 
campaign visuals, social media posts, or brand collateral.

Extract the brand's VISUAL DNA and return a structured JSON Brand Bible.

CRITICAL RULES:
- Analyze what you SEE, not what you assume
- Be specific about colors (hex values), typography feelings, composition patterns
- If you see a logo, describe its geometry, symbolism, and how it should be treated
- If you see a product, describe its key visual attributes (shape, label design, colors)
- Write rules that a generative AI can follow to produce on-brand content

Return ONLY a JSON object with these fields:

{
    "brand_name": "Detected or 'Unknown Brand'",
    "visual_identity": "2-3 sentences defining THE LOOK of this brand",
    "logo_treatment": {
        "description": "What the logo looks like — shape, colors, typography style",
        "symbolism": "What the logo communicates visually",
        "placement_rules": "Where and how the logo should appear in generated content",
        "colors": ["#hex1", "#hex2"]
    },
    "color_mandate": {
        "primary": ["#hex — name"],
        "secondary": ["#hex — name"],
        "accent": ["#hex — name"],
        "banned_colors": ["colors that clash with the brand"],
        "gradient_rules": "Any gradient usage patterns observed"
    },
    "product_visual": {
        "shape": "Product form factor description",
        "key_features": "What makes the product visually recognizable",
        "photography_angle": "How the product should be shot (front, 3/4, overhead, etc)",
        "context": "What environment/setting suits this product"
    },
    "typography_feel": "The typographic vibe — modern/classic/playful/luxury etc",
    "composition_rules": [
        "Rule 1 — specific composition guideline",
        "Rule 2 — layout pattern observed"
    ],
    "mood_signature": ["mood1", "mood2", "mood3"],
    "brand_personality": "In 2 sentences, what personality does this brand project?",
    "content_guidelines": {
        "do": ["Things to always include"],
        "dont": ["Things to never do in brand content"]
    }
}

Respond with ONLY the JSON object, no wrapping text or markdown."""


def _load_image_as_part(image_path: str) -> dict:
    """Load an image file and return a Gemini-compatible Part dict."""
    path = Path(image_path)
    suffix = path.suffix.lower()
    mime_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
    }
    mime = mime_map.get(suffix, "image/jpeg")
    
    with open(path, "rb") as f:
        data = f.read()
    
    return {
        "inline_data": {
            "mime_type": mime,
            "data": base64.b64encode(data).decode("utf-8"),
        }
    }


def _load_uploaded_image_as_part(uploaded_file) -> dict:
    """Load a Streamlit UploadedFile and return a Gemini-compatible Part dict."""
    mime = uploaded_file.type or "image/jpeg"
    data = uploaded_file.getvalue()
    return {
        "inline_data": {
            "mime_type": mime,
            "data": base64.b64encode(data).decode("utf-8"),
        }
    }


def analyze_brand_images(
    image_sources: list,
    api_key: str = None,
    model: str = "gemini-2.5-flash",
    custom_instructions: str = "",
) -> Dict:
    """Analyze brand images and extract a Brand Bible JSON.
    
    Args:
        image_sources: List of file paths (str) or Streamlit UploadedFile objects
        api_key: Gemini API key (falls back to GEMINI_API_KEY env var)
        model: Gemini model to use for analysis
        custom_instructions: Extra context about the brand
    
    Returns:
        Dict — Brand Bible JSON
    """
    api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise ValueError("No Gemini API key available. Set GEMINI_API_KEY in .env")
    
    # Build multimodal content parts
    parts = []
    
    for src in image_sources:
        if isinstance(src, (str, Path)):
            parts.append(_load_image_as_part(str(src)))
        else:
            # Streamlit UploadedFile
            parts.append(_load_uploaded_image_as_part(src))
    
    # Add text prompt
    prompt_text = BRAND_BIBLE_PROMPT
    if custom_instructions:
        prompt_text += f"\n\nADDITIONAL CONTEXT FROM USER:\n{custom_instructions}"
    
    parts.append(prompt_text)
    
    # Call Gemini multimodal
    from google import genai
    from google.genai import types
    
    client = genai.Client(api_key=api_key)
    
    logger.info(f"Brand Bible: Analyzing {len(image_sources)} image(s) with {model}")
    
    response = client.models.generate_content(
        model=model,
        contents=parts,
        config=types.GenerateContentConfig(
            temperature=0.3,  # Low temp for consistent structured output
            max_output_tokens=4096,
        ),
    )
    
    # Extract JSON from response
    raw_text = response.text if hasattr(response, 'text') else ""
    if not raw_text:
        for candidate in (response.candidates or []):
            for part in candidate.content.parts:
                if hasattr(part, 'text') and part.text:
                    raw_text = part.text
                    break
    
    # Clean and parse JSON
    brand_bible = _extract_json(raw_text)
    logger.info(f"Brand Bible extracted: {brand_bible.get('brand_name', 'Unknown')}")
    
    return brand_bible


def _extract_json(text: str) -> Dict:
    """Extract JSON from LLM response text."""
    # Try direct parse first
    text = text.strip()
    if text.startswith("{"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
    
    # Extract from markdown code block
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    
    # Last resort: find the outermost { ... }
    brace_start = text.find("{")
    brace_end = text.rfind("}")
    if brace_start != -1 and brace_end != -1:
        try:
            return json.loads(text[brace_start:brace_end + 1])
        except json.JSONDecodeError:
            pass
    
    logger.warning("Could not parse Brand Bible JSON — returning empty")
    return {}


def merge_brand_into_story_bible(story_bible: Dict, brand_bible: Dict) -> Dict:
    """Merge Brand Bible visual DNA into the pipeline's story_bible.
    
    Brand Bible entries take PRIORITY over story_bible defaults.
    This ensures generated images match the brand's visual identity.
    """
    if not brand_bible:
        return story_bible
    
    merged = dict(story_bible) if story_bible else {}
    
    # Inject brand visual identity (overrides generic story style)
    if brand_bible.get("visual_identity"):
        merged["visual_identity"] = (
            f"BRAND VISUAL DNA: {brand_bible['visual_identity']} "
            f"{merged.get('visual_identity', '')}"
        )
    
    # Inject brand color mandate
    brand_colors = brand_bible.get("color_mandate", {})
    if brand_colors:
        color_parts = []
        for key in ("primary", "secondary", "accent"):
            vals = brand_colors.get(key, [])
            if vals:
                color_parts.append(f"{key}: {', '.join(vals)}")
        banned = brand_colors.get("banned_colors", [])
        if banned:
            color_parts.append(f"BANNED: {', '.join(banned)}")
        if color_parts:
            merged["color_mandate"] = " | ".join(color_parts)
    
    # Inject logo treatment rules
    logo = brand_bible.get("logo_treatment", {})
    if logo:
        logo_rules = []
        if logo.get("description"):
            logo_rules.append(f"LOGO: {logo['description']}")
        if logo.get("placement_rules"):
            logo_rules.append(logo["placement_rules"])
        if logo_rules:
            existing_rules = merged.get("continuity_rules", "")
            merged["continuity_rules"] = (
                " | ".join(logo_rules) + " | " + existing_rules
            )
    
    # Inject product visual rules
    product = brand_bible.get("product_visual", {})
    if product and product.get("key_features"):
        elements = merged.get("recurring_elements", "")
        product_desc = (
            f"HERO PRODUCT: {product.get('key_features', '')}. "
            f"Shot angle: {product.get('photography_angle', 'hero')}. "
            f"Context: {product.get('context', 'clean studio')}"
        )
        merged["recurring_elements"] = f"{product_desc} | {elements}"
    
    # Inject mood signature
    moods = brand_bible.get("mood_signature", [])
    if moods:
        existing_atmo = merged.get("atmosphere", "")
        merged["atmosphere"] = f"BRAND MOOD: {', '.join(moods)}. {existing_atmo}"
    
    # Store full brand bible for reference
    merged["_brand_bible"] = brand_bible
    
    return merged


def save_brand_bible(brand_bible: Dict, output_path: str) -> str:
    """Save Brand Bible JSON to disk."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(brand_bible, f, indent=2, ensure_ascii=False)
    logger.info(f"Brand Bible saved to {path}")
    return str(path)


def load_brand_bible(path: str) -> Dict:
    """Load a previously saved Brand Bible JSON."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
