"""
Story Bible Generator
One LLM call to create a shared visual identity for the entire script.
Ensures all scenes look like they belong in the same project.
"""

import json
import logging
from typing import Dict, Optional

from .llm_gateway import LLMGateway

logger = logging.getLogger(__name__)

STORY_BIBLE_PROMPT = """You are a Visual Director creating a cohesive style bible for an illustrated narrative.

Given this script and style preset, produce a STRICT visual identity document that every image in the series MUST follow. Think of this as the "look dev" pass for an animated short film — every frame must feel like the same project.

SCRIPT:
{script}

STYLE PRESET:
Art Style: {art_style}
Color Palette: {color_palette}
Mood: {mood_keywords}

Generate a JSON object with these fields:

1. "visual_identity" — 2-3 sentences defining THE LOOK. Be hyper-specific: lighting direction, texture style, level of realism, rendering technique. NOT generic art direction — describe it as if briefing an artist who will paint every frame.

2. "recurring_elements" — Specific visual motifs, characters, or objects that should appear across multiple scenes to create visual continuity. Describe them concretely (e.g., "a weathered leather journal with frayed edges" not "a book").

3. "color_mandate" — Exact color rules: dominant hues, accent colors, what colors are BANNED. Be specific with descriptors (e.g., "burnt sienna" not "orange").

4. "atmosphere" — The consistent environmental feeling across all scenes: weather, time of day, air quality, ambient lighting. This anchors the whole series in one world.

5. "continuity_rules" — 3-5 bullet-point rules that EVERY image must obey to maintain visual coherence. These are non-negotiable constraints (e.g., "All scenes use top-left key lighting at 45 degrees", "Human figures are always shown in silhouette or from behind — never direct face close-ups").

6. "characters" — A JSON object mapping character identifiers to their visual description. For EACH named or recurring character/figure in the script, provide:
   - "name": How they're referred to (e.g., "The Professor", "Sarah", "The Narrator")
   - "appearance": 3-4 key visual traits that MUST stay consistent across ALL scenes: hair (color, length, style), build/silhouette, distinguishing clothing or accessories, approximate age range.
   Be CONCRETE and specific: "auburn shoulder-length wavy hair, athletic build, late 20s, olive military jacket" NOT "red hair, average build".
   If the script has NO specific characters (pure abstraction), return an empty object {{}}.

Keep each field concise (1-3 sentences max per field, except continuity_rules and characters). Total output should be under 350 words.

Respond with ONLY the JSON object, no wrapping."""


def generate_story_bible(
    script: str,
    llm_gateway: LLMGateway,
    art_style: str = "",
    color_palette: str = "",
    mood_keywords: str = "",
) -> Dict:
    """
    Parses the script to identify main characters, key themes, and visual rules.
    Used by the Art Director to verify consistency across scenes.
    """
    logger.info("Generating Story Bible...")

    system_prompt = STORY_BIBLE_PROMPT.format(
        script=script[:3000],  # Cap to avoid token overflow
        art_style=art_style or "not specified",
        color_palette=color_palette or "not specified",
        mood_keywords=mood_keywords or "not specified",
    )

    try:
        bible = llm_gateway.generate_json(
            prompt=script,
            system_instruction=system_prompt,
            role="parser"
        )
    except Exception as e:
        logger.error(f"Story bible generation failed: {e}")
        return _empty_bible()

    # Validate required fields
    required = ["visual_identity", "recurring_elements", "color_mandate",
                 "atmosphere", "continuity_rules", "characters"]
    for field in required:
        if field not in bible:
            bible[field] = {} if field == "characters" else ""

    if bible.get("characters"):
        char_count = len(bible["characters"])
        logger.info(f"  Character roster: {char_count} character(s) identified")
        for cid, cdata in bible["characters"].items():
            logger.info(f"    → {cdata.get('name', cid)}: {cdata.get('appearance', 'N/A')[:60]}...")

    logger.info("Story bible generated successfully")
    logger.info(f"  Visual identity: {bible['visual_identity'][:80]}...")
    return bible


def bible_to_prompt_prefix(bible: Dict) -> str:
    """Convert story bible to a prompt prefix string for image generation."""
    if not bible or not bible.get("visual_identity"):
        return ""

    parts = []

    parts.append(f"VISUAL IDENTITY: {bible['visual_identity']}")

    if bible.get("recurring_elements"):
        parts.append(f"RECURRING ELEMENTS: {bible['recurring_elements']}")

    if bible.get("color_mandate"):
        parts.append(f"COLOR RULES: {bible['color_mandate']}")

    if bible.get("atmosphere"):
        parts.append(f"ATMOSPHERE: {bible['atmosphere']}")

    if bible.get("continuity_rules"):
        rules = bible["continuity_rules"]
        if isinstance(rules, list):
            rules_str = "; ".join(rules)
        else:
            rules_str = str(rules)
        parts.append(f"CONTINUITY: {rules_str}")

    if bible.get("characters"):
        char_descs = []
        for cid, cdata in bible["characters"].items():
            name = cdata.get("name", cid)
            appearance = cdata.get("appearance", "")
            if appearance:
                char_descs.append(f"{name}: {appearance}")
        if char_descs:
            parts.append(f"CHARACTERS: {'; '.join(char_descs)}")

    return " | ".join(parts)


def bible_to_critique_context(bible: Dict) -> str:
    """Convert story bible to critique context for art director."""
    if not bible or not bible.get("visual_identity"):
        return ""

    parts = [
        f"Visual Identity: {bible.get('visual_identity', '')}",
        f"Color Rules: {bible.get('color_mandate', '')}",
        f"Atmosphere: {bible.get('atmosphere', '')}",
    ]

    rules = bible.get("continuity_rules", "")
    if isinstance(rules, list):
        parts.append(f"Continuity Rules: {'; '.join(rules)}")
    elif rules:
        parts.append(f"Continuity Rules: {rules}")

    # Character roster for fidelity checking
    characters = bible.get("characters", {})
    if characters:
        char_lines = []
        for cid, cdata in characters.items():
            name = cdata.get("name", cid)
            appearance = cdata.get("appearance", "")
            if appearance:
                char_lines.append(f"  - {name}: {appearance}")
        if char_lines:
            parts.append(f"Character Roster:\n" + "\n".join(char_lines))

    return "\n".join(parts)


def _empty_bible() -> Dict:
    """Return an empty story bible (fallback when generation fails)."""
    return {
        "visual_identity": "",
        "recurring_elements": "",
        "color_mandate": "",
        "atmosphere": "",
        "continuity_rules": "",
        "characters": {},
    }
