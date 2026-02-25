"""
Prompt Builder Module
Constructs structured image generation prompts from scenes + style presets.
"""

import json
import logging
import re
from pathlib import Path
from typing import Dict, Optional, Tuple, List
from .scene_parser import Scene, Visual
from .story_bible import bible_to_prompt_prefix

logger = logging.getLogger(__name__)


class StylePreset:
    """Loads and applies a reusable style preset to prompts."""

    def __init__(self, preset_path: str):
        with open(preset_path, "r", encoding="utf-8") as f:
            self.data = json.load(f)

        self.name = self.data.get("name", "default")
        self.art_style = self.data.get("art_style", "")
        self.color_palette = self.data.get("color_palette", "")
        self.mood_keywords = self.data.get("mood_keywords", [])
        self.negative_prompt = self.data.get("negative_prompt", "")
        self.quality_tags = self.data.get("quality_tags", "")

        logger.info(f"Loaded style preset: {self.name}")

    def to_dict(self) -> Dict:
        return self.data


class PromptBuilder:
    """Builds image generation prompts from scenes + style presets."""

    # Shot-type prefixes that guide the image generator
    SHOT_PREFIX = {
        "establishing": "Wide cinematic establishing shot:",
        "key_visual": "",
        "detail": "Close-up detail shot, intimate and symbolic:",
    }

    def __init__(self, style_preset: StylePreset):
        self.style = style_preset

    def build(self, scene: Scene, revision_guidance: str = None) -> str:
        """Build a complete image prompt for a scene (legacy single-visual)."""
        parts = []

        # Style prefix
        if self.style.art_style:
            parts.append(self.style.art_style)

        # Core visual description
        parts.append(scene.visual_description)

        # Key elements emphasis
        if scene.key_elements:
            elements = ", ".join(scene.key_elements)
            parts.append(f"Key elements: {elements}.")

        # Mood
        if scene.mood:
            parts.append(f"Mood: {scene.mood}.")

        # Color palette
        if self.style.color_palette:
            parts.append(f"Color palette: {self.style.color_palette}.")

        # Quality tags
        if self.style.quality_tags:
            parts.append(self.style.quality_tags)

        # Revision guidance from art director (retry iterations)
        if revision_guidance:
            parts.append(f"IMPORTANT REVISION: {revision_guidance}")

        # Smart text guidance
        parts.append(
            'TEXT RULES: If this scene requires visible text (signs, headlines, labels), '
            'render ONLY short exact phrases (1-4 words max) and spell them perfectly. '
            'Prefer visual metaphors over text when possible. '
            'Never render long sentences, paragraphs, or body copy in the image.'
        )

        prompt = " ".join(parts)
        self.last_negative = self.style.negative_prompt

        logger.info(f"Built prompt for Scene {scene.scene_number} ({len(prompt)} chars)")
        return prompt

    def build_from_visual(self, visual: Visual, scene: Scene,
                          revision_guidance: str = None,
                          story_bible: dict = None) -> str:
        """Build a prompt from a specific Visual within a scene.

        Structure (priority order — v2.2 repositioned):
        1. SINGLE-FRAME MANDATE — prevent comic panel hallucination
        2. SCRIPT CONTEXT — the original script text (anchor)
        3. CHARACTER LOCK — exact character descriptions from bible (must be early)
        4. CONTINUITY ANCHOR — style/palette/lighting mandates from bible
        5. VISUAL — what to draw (literal description)
        6. STYLE — art style + color palette (brief)
        """
        parts = []

        # 1. SINGLE-FRAME MANDATE — v2.2: prevents multi-panel/comic layouts
        parts.append(
            "SINGLE IMAGE FRAME. No panels, no comic layout, no split screen, "
            "no multiple views. One continuous scene only."
        )

        # 2. SCRIPT CONTEXT — the image generator must know what it's illustrating
        if scene.original_text:
            script_excerpt = scene.original_text[:300]
            parts.append(f'This image illustrates this script line: "{script_excerpt}"')

        # 3. CHARACTER LOCK — v2.2: moved from position 5 to position 3
        #    Image generators weight early tokens more heavily
        if story_bible and story_bible.get("characters"):
            search_text = (visual.visual_description + " " + scene.original_text).lower()
            matched = []
            for char_id, char_data in story_bible["characters"].items():
                char_name = char_data.get("name", char_id).lower()
                name_match = re.search(r'\b' + re.escape(char_name) + r'\b', search_text)
                id_match = re.search(r'\b' + re.escape(char_id.lower()) + r'\b', search_text)
                if name_match or id_match:
                    appearance = char_data.get("appearance", "")
                    if appearance:
                        matched.append(f"{char_data.get('name', char_id)}: {appearance}")
            if matched:
                parts.append(f"CHARACTER LOCK (EXACT descriptions, do NOT deviate): {'; '.join(matched)}")

        # 4. CONTINUITY ANCHOR — v2.2: moved from position 6 to position 4
        if story_bible:
            # Color palette enforcement with hex codes if available
            palette = story_bible.get("color_palette")
            if palette:
                if isinstance(palette, list):
                    palette_str = ", ".join(palette[:6])
                else:
                    palette_str = str(palette)[:200]
                parts.append(f"MANDATORY COLOR PALETTE: {palette_str}")

            # Continuity rules
            rules = story_bible.get("continuity_rules")
            if rules:
                if isinstance(rules, list):
                    rules_str = "; ".join(rules[:3])
                else:
                    rules_str = str(rules)[:200]
                parts.append(f"CONTINUITY MANDATE: {rules_str}")

        # 5. VISUAL — the literal description from the parser
        parts.append(visual.visual_description)

        # Key elements (from the visual or scene)
        elements = visual.key_elements or scene.key_elements
        if elements:
            parts.append(f"Must include: {', '.join(elements)}.")

        # Mood
        mood = visual.mood or scene.mood
        if mood:
            parts.append(f"Mood: {mood}.")

        # 6. STYLE — condensed to essentials
        if self.style.art_style:
            parts.append(f"Style: {self.style.art_style}")

        if self.style.color_palette:
            parts.append(f"Palette: {self.style.color_palette}.")

        # Revision guidance from art director (retry iterations)
        if revision_guidance:
            parts.append(f"IMPORTANT REVISION: {revision_guidance}")

        prompt = " | ".join(parts)
        self.last_negative = self.style.negative_prompt

        vt = visual.visual_type
        logger.info(f"Built {vt} prompt for Scene {scene.scene_number} ({len(prompt)} chars)")
        return prompt

    def build_revision_prompt(self, scene: Scene, critique: Dict,
                              threshold: float = 7.0) -> str:
        """Build a revised prompt based on art director feedback."""
        guidance_parts = []

        for dimension, feedback in critique.get("feedback", {}).items():
            if feedback.get("score", 10) < threshold:
                guidance_parts.append(f"{dimension}: {feedback.get('suggestion', '')}")

        revision_str = "; ".join(guidance_parts) if guidance_parts else None
        return self.build(scene, revision_guidance=revision_str)

    def build_visual_revision_prompt(self, visual: Visual, scene: Scene,
                                     critique: Dict,
                                     story_bible: dict = None,
                                     threshold: float = 7.0) -> str:
        """Build a revised prompt for a specific visual based on art director feedback."""
        guidance_parts = []

        for dimension, feedback in critique.get("feedback", {}).items():
            if feedback.get("score", 10) < threshold:
                guidance_parts.append(f"{dimension}: {feedback.get('suggestion', '')}")

        revision_str = "; ".join(guidance_parts) if guidance_parts else None
        return self.build_from_visual(visual, scene, revision_guidance=revision_str,
                                     story_bible=story_bible)
