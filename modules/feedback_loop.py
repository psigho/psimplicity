"""
Feedback Loop — Anti-Hallucination System
==========================================

Classifies Art Director critiques into typed errors and applies targeted
prompt surgery for retries instead of generic text appends.

Error Types:
  TEXT_HALLUCINATION   → inject negative prompt ("no text, no letters")
  ANATOMY_ERROR        → reinforce anatomy in positive prompt
  COSTUME_DRIFT        → re-inject full character description from bible
  CONSISTENCY_BREAK    → strengthen continuity anchoring
  GENERIC_STOCK        → strengthen concept + specificity
  STYLE_MISMATCH       → reinforce style directive
  COMPOSITION_ISSUE    → adjust framing language
  ARTIFACT_NOISE       → inject "clean, professional" + negative prompt
"""

import logging
import re
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# Error Taxonomy
# ──────────────────────────────────────────────────────────────

@dataclass
class TypedError:
    """A classified error from an Art Director critique."""
    type: str           # e.g. TEXT_HALLUCINATION, ANATOMY_ERROR
    severity: str       # hard_fail | soft_fail
    dimension: str      # which Art Director dimension flagged it
    score: int          # the actual score (1-10)
    detail: str         # Art Director's specific suggestion text
    fix_strategy: str   # negative_inject | positive_reinforce | character_reinject | bible_anchor


# Error type definitions with detection rules
ERROR_RULES = {
    "TEXT_HALLUCINATION": {
        "dimension": "text_accuracy",
        "threshold": 6,  # v2.2: raised from 5 to catch scores 1-5
        "severity": "hard_fail",
        "fix_strategy": "negative_inject",
        "keywords": ["text", "letters", "words", "writing", "garbled", "readable",
                     "watermark", "logo", "font", "label", "caption", "signage"],
        "negative_inject": "no text, no letters, no words, no writing, no watermark, no labels, no signage, no captions",
        "positive_inject": "",
    },
    "ANATOMY_ERROR": {
        "dimension": "artifact_free",
        "threshold": 6,  # v2.2: raised from 5
        "severity": "hard_fail",
        "fix_strategy": "positive_reinforce",
        "keywords": ["finger", "hand", "arm", "leg", "eye", "face", "body",
                     "limb", "anatomy", "proportion", "deformed", "extra",
                     "missing", "fused", "merged", "six", "seven"],
        "negative_inject": "deformed hands, extra fingers, fused limbs, bad anatomy, mutated",
        "positive_inject": "anatomically correct, natural human proportions, five fingers per hand",
    },
    "COSTUME_DRIFT": {
        "dimension": "character_fidelity",
        "threshold": 6,  # v2.2: raised from 5
        "severity": "hard_fail",
        "fix_strategy": "character_reinject",
        "keywords": ["character", "costume", "outfit", "clothing", "hair", "appearance",
                     "wearing", "dressed", "different", "inconsistent", "changed",
                     "wrong color", "skin", "ethnicity"],
        "negative_inject": "",
        "positive_inject": "",  # dynamically filled from story bible
    },
    "CONSISTENCY_BREAK": {
        "dimension": "continuity",
        "threshold": 7,  # v2.2: raised from 5 to match pass_threshold
        "severity": "soft_fail",
        "fix_strategy": "bible_anchor",
        "keywords": ["continuity", "consistent", "previous", "different from",
                     "doesn't match", "style shift", "mismatch", "palette"],
        "negative_inject": "",
        "positive_inject": "",  # dynamically filled from story bible
    },
    "GENERIC_STOCK": {
        "dimension": "concept",
        "threshold": 7,  # v2.2: raised from 5 to match pass_threshold
        "severity": "soft_fail",
        "fix_strategy": "positive_reinforce",
        "keywords": ["generic", "stock", "cliché", "bland", "template",
                     "unoriginal", "basic", "default", "clipart"],
        "negative_inject": "generic stock photo, cliché, clip art, template image",
        "positive_inject": "unique, specific, original composition, distinctive visual concept",
    },
    "STYLE_MISMATCH": {
        "dimension": "style",
        "threshold": 7,  # v2.2: raised from 5 to match pass_threshold
        "severity": "soft_fail",
        "fix_strategy": "positive_reinforce",
        "keywords": ["style", "aesthetic", "mood", "tone", "look", "feel",
                     "photorealistic", "cartoon", "doesn't match"],
        "negative_inject": "",
        "positive_inject": "",  # will be filled with the style preset
    },
    "COMPOSITION_ISSUE": {
        "dimension": "composition",
        "threshold": 7,  # v2.2: raised from 5 to match pass_threshold
        "severity": "soft_fail",
        "fix_strategy": "positive_reinforce",
        "keywords": ["composition", "framing", "cropped", "centered", "cluttered",
                     "empty", "balance", "focal", "spacing", "arrangement"],
        "negative_inject": "cluttered, poorly framed, off-center subject",
        "positive_inject": "well-composed, balanced framing, clear focal point",
    },
    "ARTIFACT_NOISE": {
        "dimension": "artifact_free",
        "threshold": 7,  # v2.2: raised from 5 to match pass_threshold
        "severity": "soft_fail",
        "fix_strategy": "negative_inject",
        "keywords": ["artifact", "noise", "blur", "distort", "glitch", "seam",
                     "border", "edge", "pixelat", "jpeg", "compression"],
        "negative_inject": "artifacts, noise, blur, distortion, glitch, pixelation, jpeg artifacts",
        "positive_inject": "clean, sharp, professional quality, high resolution",
    },
}


# ──────────────────────────────────────────────────────────────
# Error Classifier
# ──────────────────────────────────────────────────────────────

class FeedbackClassifier:
    """Maps Art Director critique scores + suggestions to typed errors."""

    def classify(self, critique_result) -> List[TypedError]:
        """
        Analyze a CritiqueResult and return a list of TypedErrors.

        Args:
            critique_result: CritiqueResult from art_director.py

        Returns:
            List of TypedError, sorted by severity (hard_fail first)
        """
        errors = []
        scores = critique_result.scores or {}
        feedback = critique_result.feedback or {}

        for error_type, rule in ERROR_RULES.items():
            dimension = rule["dimension"]
            score = scores.get(dimension, 10)  # default 10 = no issue

            # Skip if score is above threshold
            if score >= rule["threshold"]:
                continue

            # Get the Art Director's suggestion for this dimension
            dim_feedback = feedback.get(dimension, {})
            suggestion = dim_feedback.get("suggestion", "") if isinstance(dim_feedback, dict) else str(dim_feedback)

            # Check if the suggestion text contains keywords for this error type
            suggestion_lower = suggestion.lower()
            keyword_match = any(kw in suggestion_lower for kw in rule["keywords"])

            # Also check if text_detected flag is set (special case for text hallucination)
            if error_type == "TEXT_HALLUCINATION":
                text_detected = getattr(critique_result, 'text_detected', None)
                if text_detected is None and hasattr(critique_result, 'raw_response'):
                    # Try to extract from raw response
                    raw = critique_result.raw_response or ""
                    if '"text_detected": true' in raw.lower() or '"text_detected":true' in raw.lower():
                        text_detected = True
                if text_detected:
                    keyword_match = True

            # For anatomy errors within artifact_free, we need keyword evidence
            # (artifact_free covers many things, not just anatomy)
            if error_type == "ANATOMY_ERROR" and not keyword_match:
                continue

            # For the primary dimension error type, always include if score is low enough
            # For secondary types that share a dimension, require keyword evidence
            primary_for_dimension = error_type == self._primary_type_for(dimension)
            if not primary_for_dimension and not keyword_match:
                continue

            errors.append(TypedError(
                type=error_type,
                severity=rule["severity"],
                dimension=dimension,
                score=score,
                detail=suggestion,
                fix_strategy=rule["fix_strategy"],
            ))

        # Sort: hard_fail first, then by score ascending (worst first)
        errors.sort(key=lambda e: (0 if e.severity == "hard_fail" else 1, e.score))

        if errors:
            logger.info(f"🔍 Classified {len(errors)} error(s): "
                       f"{', '.join(e.type + f'({e.score})' for e in errors)}")
        else:
            logger.info("✅ No typed errors found in critique")

        return errors

    def _primary_type_for(self, dimension: str) -> str:
        """Return the primary error type for a given Art Director dimension."""
        primary_map = {
            "text_accuracy": "TEXT_HALLUCINATION",
            "artifact_free": "ARTIFACT_NOISE",
            "character_fidelity": "COSTUME_DRIFT",
            "continuity": "CONSISTENCY_BREAK",
            "concept": "GENERIC_STOCK",
            "style": "STYLE_MISMATCH",
            "composition": "COMPOSITION_ISSUE",
            "relevance": "GENERIC_STOCK",
        }
        return primary_map.get(dimension, "")


# ──────────────────────────────────────────────────────────────
# Prompt Surgeon
# ──────────────────────────────────────────────────────────────

class PromptSurgeon:
    """Applies targeted fixes to prompts based on typed errors."""

    def apply_fixes(
        self,
        prompt: str,
        negative_prompt: str,
        errors: List[TypedError],
        story_bible: Optional[Dict] = None,
        style_description: str = "",
    ) -> Tuple[str, str]:
        """
        Apply targeted prompt surgery based on classified errors.

        Args:
            prompt: Current positive prompt
            negative_prompt: Current negative prompt
            errors: List of TypedError from the classifier
            story_bible: The story bible dict (for character/continuity injection)
            style_description: The style preset description

        Returns:
            Tuple of (enhanced_prompt, enhanced_negative_prompt)
        """
        if not errors:
            return prompt, negative_prompt

        positive_additions = []
        negative_additions = []
        revision_notes = []

        for error in errors:
            rule = ERROR_RULES.get(error.type, {})

            # 1. Apply negative prompt injections
            neg = rule.get("negative_inject", "")
            if neg:
                negative_additions.append(neg)

            # 2. Apply positive prompt reinforcements
            pos = rule.get("positive_inject", "")
            if pos:
                positive_additions.append(pos)

            # 3. Strategy-specific handling
            if error.fix_strategy == "character_reinject" and story_bible:
                char_block = self._build_character_block(story_bible)
                if char_block:
                    positive_additions.append(f"CRITICAL CHARACTER ACCURACY: {char_block}")

            elif error.fix_strategy == "bible_anchor" and story_bible:
                continuity_block = self._build_continuity_block(story_bible)
                if continuity_block:
                    positive_additions.append(f"CONTINUITY MANDATE: {continuity_block}")

            elif error.fix_strategy == "positive_reinforce" and error.type == "STYLE_MISMATCH":
                if style_description:
                    positive_additions.append(f"MANDATORY STYLE: {style_description}")

            # 4. Always include the Art Director's specific suggestion
            if error.detail:
                revision_notes.append(f"[{error.type}] {error.detail}")

        # Dedupe
        negative_additions = list(dict.fromkeys(negative_additions))
        positive_additions = list(dict.fromkeys(positive_additions))

        # Build enhanced prompts
        enhanced_prompt = prompt
        if positive_additions:
            enhanced_prompt += "\n\n" + ". ".join(positive_additions) + "."
        if revision_notes:
            enhanced_prompt += "\n\nART DIRECTOR REVISION:\n" + "\n".join(revision_notes)

        enhanced_negative = negative_prompt
        if negative_additions:
            neg_str = ", ".join(negative_additions)
            if enhanced_negative:
                enhanced_negative += ", " + neg_str
            else:
                enhanced_negative = neg_str

        logger.info(f"🔧 Prompt Surgeon applied {len(errors)} fix(es): "
                   f"[+{len(positive_additions)} positive, -{len(negative_additions)} negative]")

        return enhanced_prompt, enhanced_negative

    def _build_character_block(self, story_bible: Dict) -> str:
        """Extract all character descriptions from the story bible."""
        characters = story_bible.get("characters", {})
        if not characters:
            return ""

        parts = []
        for char_id, char_data in characters.items():
            name = char_data.get("name", char_id)
            appearance = char_data.get("appearance", "")
            if appearance:
                parts.append(f"{name}: {appearance}")

        return "; ".join(parts)

    def _build_continuity_block(self, story_bible: Dict) -> str:
        """Extract continuity rules from the story bible."""
        rules = story_bible.get("continuity_rules", [])
        if isinstance(rules, list):
            return "; ".join(rules[:4])  # max 4 rules
        return str(rules)[:300]


# ──────────────────────────────────────────────────────────────
# Convenience function for the orchestrator
# ──────────────────────────────────────────────────────────────

def process_feedback(
    critique_result,
    prompt: str,
    negative_prompt: str,
    story_bible: Optional[Dict] = None,
    style_description: str = "",
) -> Tuple[str, str, List[TypedError]]:
    """
    One-call convenience: classify errors and apply prompt surgery.

    Args:
        critique_result: CritiqueResult from art_director.py
        prompt: Current positive prompt
        negative_prompt: Current negative prompt
        story_bible: Story bible dict
        style_description: Style preset description

    Returns:
        Tuple of (enhanced_prompt, enhanced_negative, errors_found)
    """
    classifier = FeedbackClassifier()
    errors = classifier.classify(critique_result)

    if not errors:
        return prompt, negative_prompt, errors

    surgeon = PromptSurgeon()
    enhanced_prompt, enhanced_negative = surgeon.apply_fixes(
        prompt=prompt,
        negative_prompt=negative_prompt,
        errors=errors,
        story_bible=story_bible,
        style_description=style_description,
    )

    return enhanced_prompt, enhanced_negative, errors
