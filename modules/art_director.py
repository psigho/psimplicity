"""
Art Director Module — THE HEART OF THE PROJECT
AI-powered image critique, scoring, and revision loop using GPT-4o Vision.

Scoring Rubric (8 dimensions, each 1-10):
  1. relevance         — How well does image match the script scene?
  2. concept           — Is the visual metaphor clear and intentional?
  3. style             — Does it match the preset style/mood?
  4. composition       — Is framing, layout, readability good?
  5. artifact_free     — Free of AI slop, bad hands, text glitches?
  6. text_accuracy     — Is text rendered correctly (or absent as expected)?
  7. continuity        — Does it maintain visual continuity across scenes?
  8. character_fidelity — Do characters match the Story Bible roster?

Pass threshold: average >= 7.0 (configurable) AND relevance >= 7.0 (hard gate)
Max retries: 3 (configurable, hard cap to prevent infinite loops)
"""

import json
import base64
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple
import openai
from .story_bible import bible_to_critique_context
from .json_repair import extract_json as _extract_json

logger = logging.getLogger(__name__)


@dataclass
class CritiqueResult:
    """Result of an art director critique."""
    scores: Dict[str, int]
    average_score: float
    passed: bool
    feedback: Dict[str, Dict]  # dimension -> {score, suggestion}
    summary: str
    raw_response: str = ""

    def to_dict(self) -> Dict:
        return {
            "scores": self.scores,
            "average_score": self.average_score,
            "passed": self.passed,
            "feedback": self.feedback,
            "summary": self.summary
        }


class ArtDirector:
    """AI Art Director — critiques images and provides revision guidance."""

    CRITIQUE_PROMPT = """You are a professional Art Director reviewing AI-generated images for a video production pipeline.

NARRATIVE CONTEXT:
Full Script Summary: {full_script_summary}
This is Scene {scene_number} of {total_scenes} in the sequence.

STORY BIBLE (the visual identity ALL images in this series MUST follow):
{story_bible_context}

CURRENT SCENE:
Scene Title: {scene_title}
Scene Description: {scene_description}
Original Script Text: {original_text}
Mood: {mood}
Key Elements Expected: {key_elements}
Style Preset: {style_description}

SCORE THIS IMAGE on these 8 dimensions (each 1-10):

1. **relevance** — Does this image match what the script scene describes? Does it visually represent the ideas in the original script text? Consider the scene's position in the overall narrative.
2. **concept** — Is the visual metaphor/concept clear? Does it communicate the intended idea? Is it a creative interpretation of the script, not generic stock imagery?
3. **style** — Is the visual style consistent with the preset (color palette, mood, art direction)? Does it feel cohesive with the overall video's tone?
4. **composition** — Is the framing good? Is the layout readable? Is the focal point clear? Would this work as a frame in a video?
5. **artifact_free** — Is it free from AI artifacts? No extra fingers, weird faces, blurry patches, impossible anatomy, or "AI slop"?
6. **text_accuracy** — If ANY text/letters/words appear in the image: Are they perfectly spelled, legible, and intentional? Score 1-3 if text is garbled/hallucinated. Score 10 if no text appears (no text = perfect score). Score 8-10 if text is short, accurate, and well-placed.
7. **continuity** — Does this image look like it belongs in the SAME visual series as the other scenes? Does it follow the Story Bible's visual identity, color mandate, atmosphere, and continuity rules? Score low if this image could be from a completely different project.
8. **character_fidelity** — Do the recurring characters in this image match their descriptions from the Story Bible's character roster? Check: hair color/length, build, clothing, age, distinguishing features. Score 10 if no characters appear in the scene. Score 1-4 if a character's appearance contradicts their established description (e.g., blonde hair when it should be dark, wrong clothing). Score 7+ if characters visually match their roster descriptions.

For each dimension:
- Give a score (1-10)
- If score < 7, give a SPECIFIC, ACTIONABLE suggestion for the prompt revision
- If score >= 7, suggestion can be empty

Also provide:
- **summary**: 1-2 sentence overall assessment considering the scene's role in the narrative
- **revision_priority**: Which dimension needs the MOST improvement (or "none" if all pass)
- **text_detected**: true/false — did you see any text/letters rendered in the image?

Respond in JSON:
{{
  "scores": {{"relevance": X, "concept": X, "style": X, "composition": X, "artifact_free": X, "text_accuracy": X, "continuity": X, "character_fidelity": X}},
  "feedback": {{
    "relevance": {{"score": X, "suggestion": "..."}},
    "concept": {{"score": X, "suggestion": "..."}},
    "style": {{"score": X, "suggestion": "..."}},
    "composition": {{"score": X, "suggestion": "..."}},
    "artifact_free": {{"score": X, "suggestion": "..."}},
    "text_accuracy": {{"score": X, "suggestion": "..."}},
    "continuity": {{"score": X, "suggestion": "..."}},
    "character_fidelity": {{"score": X, "suggestion": "..."}}
  }},
  "summary": "...",
  "revision_priority": "...",
  "text_detected": false
}}

Be HONEST and SPECIFIC. Do not inflate scores. A score of 5 means "mediocre". 7 means "good enough". 9-10 means "excellent". Garbled or hallucinated text should ALWAYS score below 4 on text_accuracy. Character appearance contradicting the Story Bible roster should ALWAYS score below 4 on character_fidelity."""

    def __init__(self, llm_gateway, pass_threshold: float = 7.0, max_retries: int = 3):
        self.llm = llm_gateway
        self.model = self.llm.critic_model
        self.pass_threshold = pass_threshold
        self.max_retries = max_retries

    def critique(self, image_path: str, scene_title: str, scene_description: str,
                 mood: str = "", key_elements: list = None,
                 style_description: str = "", original_text: str = "",
                 full_script_summary: str = "", scene_number: int = 0,
                 total_scenes: int = 0,
                 story_bible: dict = None) -> CritiqueResult:
        """Critique an image against the scene requirements.
        
        Args:
            image_path: Path to the generated image
            scene_title: Title of the scene
            scene_description: Visual description from script parsing
            mood: Mood keywords
            key_elements: List of expected visual elements
            style_description: Description of the style preset
            original_text: Original script text for narrative context
            full_script_summary: Brief summary of the entire script
            scene_number: Current scene number in sequence
            total_scenes: Total number of scenes
            story_bible: Story bible dict for continuity scoring
            
        Returns:
            CritiqueResult with scores, feedback, and pass/fail status
        """
        # Build story bible context for continuity scoring
        bible_ctx = bible_to_critique_context(story_bible) if story_bible else "Not available"

        # Build the critique prompt
        prompt = self.CRITIQUE_PROMPT.format(
            scene_title=scene_title,
            scene_description=scene_description,
            original_text=original_text or "not provided",
            full_script_summary=full_script_summary or "not provided",
            story_bible_context=bible_ctx,
            scene_number=scene_number or "?",
            total_scenes=total_scenes or "?",
            mood=mood or "not specified",
            key_elements=", ".join(key_elements) if key_elements else "not specified",
            style_description=style_description or "not specified"
        )

        logger.info(f"Art Director reviewing: {Path(image_path).name}")

        # ── Strategy: Native Gemini SDK (primary) → OpenAI-compat (fallback) ──
        logger.info(f"Critiquing image with {self.model}...")

        try:
            parsed = self.llm.critique_image(
                prompt=prompt,
                image_path=image_path,
                system_instruction="" # System context is woven into the main prompt for ArtDirector
            )
        except Exception as e:
            logger.error(f"Image critique failed: {e}")
            raise RuntimeError(f"Art Director critique failed: {str(e)}") from e

        # Extract scores map
        scores = parsed.get("scores", {})
        avg = sum(scores.values()) / len(scores) if scores else 0

        # Hard gate: relevance must pass independently — a pretty image
        # that doesn't match the script is worthless (Dan's feedback)
        relevance_score = scores.get("relevance", 0)
        relevance_passed = relevance_score >= self.pass_threshold
        avg_passed = avg >= self.pass_threshold
        passed = relevance_passed and avg_passed

        if not relevance_passed and avg_passed:
            logger.warning(f"Image FAILED relevance hard gate ({relevance_score}/10) "
                          f"despite avg {avg:.1f}/10 — image doesn't match script")

        critique = CritiqueResult(
            scores=scores,
            average_score=round(avg, 1),
            passed=passed,
            feedback=parsed.get("feedback", {}),
            summary=parsed.get("summary", ""),
            raw_response=json.dumps(parsed)
        )

        status = "✅ PASS" if passed else "❌ FAIL"
        logger.info(f"Art Director verdict: {status} (avg: {critique.average_score}/10)")
        for dim, score in scores.items():
            logger.info(f"  {dim}: {score}/10")

        return critique

    def should_retry(self, critique: CritiqueResult, attempt: int) -> bool:
        """Determine if we should retry based on critique and attempt count."""
        if critique.passed:
            return False
        if attempt >= self.max_retries:
            logger.warning(f"Max retries ({self.max_retries}) reached. Using best attempt.")
            return False
        return True
