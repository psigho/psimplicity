"""
Scene Parser Module
Parses a text script into structured scenes using LLM.
Supports Visual Density: each scene can produce 1-3 visuals
(establishing shots, key visuals, detail/cutaway shots).
"""

import json
import logging
from dataclasses import dataclass, field
from typing import List, Optional
import openai

from .json_repair import extract_json

logger = logging.getLogger(__name__)


@dataclass
class Visual:
    """A single visual shot within a scene."""
    visual_type: str          # "establishing", "key_visual", or "detail"
    visual_description: str
    mood: str = ""
    key_elements: List[str] = field(default_factory=list)


@dataclass
class Scene:
    """Represents a single scene extracted from a script."""
    scene_number: int
    scene_title: str
    visual_description: str   # kept for backward compat (= first key_visual desc)
    mood: str = ""
    key_elements: List[str] = field(default_factory=list)
    duration_seconds: int = 0
    original_text: str = ""
    visuals: List[Visual] = field(default_factory=list)

    def get_visuals(self) -> List[Visual]:
        """Return visuals list, auto-wrapping legacy single-visual scenes."""
        if self.visuals:
            return self.visuals
        # Backward compat: wrap the single visual_description as a key_visual
        return [Visual(
            visual_type="key_visual",
            visual_description=self.visual_description,
            mood=self.mood,
            key_elements=self.key_elements,
        )]


class SceneParser:
    """Parses scripts into scenes using LLM. Native Gemini SDK primary, OpenAI-compat fallback."""

    SYSTEM_PROMPT = """You are a professional script-to-image parser for philosophy/commentary video production.

Parse the given script into individual scenes optimized for AI IMAGE generation (not video).

FOR EACH SCENE, provide:
1. scene_number: Sequential number starting from 1
2. scene_title: Brief descriptive title (max 50 chars)
3. original_text: The exact script text this scene corresponds to
4. visuals: An array with EXACTLY 1 visual for this scene:
   - visual_type: Always "key_visual"
   - visual_description: What the IMAGE should show. CRITICAL RULES:
     * Be LITERAL — describe exactly what should be drawn to illustrate this script moment
     * If the script mentions hands, show hands. If it mentions money, show money.
     * The viewer must read the script line and IMMEDIATELY recognize what the image depicts
     * Subject, pose, and composition should directly reflect the script's content
     * Lighting and environment should match the script's emotional tone
     * NO abstract metaphors unless the script itself uses metaphorical language
     * NO random animals, objects, or symbols that aren't mentioned or directly implied by the script
     * NO mentions of camera movement (these are still images)
   - mood: One or two words describing the emotional tone
   - key_elements: Array of 3-5 key visual elements that MUST appear (derived directly from the script text)

CRITICAL: Each scene gets EXACTLY 1 key_visual.
Every image must be a DIRECT ILLUSTRATION of the script text — not an artistic reinterpretation.
A viewer hearing the script should immediately understand why this image was chosen.

⚠️ SCRIPT COMPREHENSION — PRE-ANALYSIS (DO THIS FIRST):
Before parsing scenes, read the ENTIRE script and identify:
1. GENRE: Is this political commentary, philosophy, storytelling, education, etc.?
2. NAMED PEOPLE: List every real person mentioned by name and what role they play in the script
3. QUOTES: Which statements are direct quotes? Who said them?
4. FIGURATIVE vs LITERAL: Flag any phrases that are idioms, metaphors, or common expressions (these are NEVER to be depicted literally)
5. ANALOGIES: Are there hypothetical scenarios ("imagine a man who...", "say there was...") used to make a larger point?

⚠️ FIGURATIVE LANGUAGE RULES (MANDATORY):
- Political/commentary scripts are FULL of figurative language — assume colorful phrases are figurative unless proven literal
- ALWAYS illustrate the MEANING of an expression, never its literal words
- Common traps to avoid:
  * Body idioms ("spine", "backbone", "feet", "hands tied") → depict the QUALITY they represent (courage, independence, helplessness) NOT anatomy
  * Political idioms ("flip-flop", "roll over", "witch hunt", "mudslinging") → depict the POLITICAL ACTION, not the literal object
  * Violence idioms ("beat up on", "shoot down", "attack", "destroy") → depict CRITICISM or CONFLICT, not physical violence (unless script is literally about violence)
  * Size/scale idioms ("higher than ever", "through the roof", "rock bottom") → depict the CONTEXT (stock prices, emotions, status), not literal heights
- SELF-CHECK: Before finalizing each visual_description, re-read it and ask: "Would a human illustrator draw this the same way, or would they understand the figurative meaning?" If an illustrator would laugh at the literal interpretation, you have it wrong.

⚠️ NAMED PERSON & QUOTE ATTRIBUTION (MANDATORY):
- When the script NAMES a real person, that person MUST appear in the visual by name
- Write "Donald Trump" not "a man" — write "Pam Bondi" not "a woman at Congress"
- When the script contains a DIRECT QUOTE from a named person, the image must show THAT PERSON delivering or associated with that quote
- When the script describes a named person performing an action (even hypothetical), that named person is the subject of the image
- The viewer must be able to identify WHO the script is talking about from the image alone

⚠️ ANALOGIES & THOUGHT EXPERIMENTS (MANDATORY):
- Hypothetical scenarios ("Say there was a man...", "Imagine if...") are ANALOGIES — illustrate the scene as described
- When the script TRANSITIONS from analogy to real-world point ("That is the same as...", "This is what X is doing..."), the visual must shift to the REAL subject
- Each scene should be clearly EITHER the analogy OR the real point — never a confused mix of both
- The transition scene should depict the real-world political/social situation, not still show the analogy

Output as JSON: { "scenes": [...] }

RULES:
- Each visual = ONE powerful still image that LITERALLY depicts the script content
- Aim for 1 scene per 15-30 seconds of narration
- Visual descriptions should be 2-4 sentences, rich in CONCRETE detail
- key_elements must come FROM the script, not from imagination
- If the script is abstract/philosophical, illustrate the CONCRETE EXAMPLES it uses, not the abstract concepts"""

    def __init__(self, llm_gateway):
        self.llm = llm_gateway
        self.model = self.llm.parser_model

    def parse(self, script: str, target_scenes: int = None,
              status_callback=None) -> List[Scene]:
        """Parse a script into scenes with multi-visual density."""
        logger.info(f"Parsing script with {self.model}...")

        system = self.SYSTEM_PROMPT
        if target_scenes and target_scenes > 0:
            system += (
                f"\n\nCRITICAL REQUIREMENT: You MUST split this script into EXACTLY {target_scenes} scenes."
                f" Not {target_scenes - 1}, not {target_scenes + 1} — exactly {target_scenes}."
                f" Distribute the script content evenly across all {target_scenes} scenes."
                f" If the script is short, create finer-grained scene breakdowns"
                f" (e.g., split a single paragraph into multiple visual moments)."
                f" Your output JSON must contain exactly {target_scenes} objects in the 'scenes' array."
            )
            logger.info(f"Target scene count: {target_scenes}")

        # --- Chunking Logic ---
        # Split script into ~1000 word chunks to prevent Gemini output token truncation
        words = script.split()
        chunk_size = 1000
        chunks = [" ".join(words[i:i + chunk_size]) for i in range(0, len(words), chunk_size)]
        
        all_scenes = []
        scene_counter = 1
        
        # Determine target scenes per chunk if a total target was provided
        if target_scenes and target_scenes > 0:
            base_target = max(1, target_scenes // len(chunks))
            remainder = target_scenes % len(chunks)
        else:
            base_target = 0
            remainder = 0
        
        for idx, chunk_text in enumerate(chunks):
            chunk_target = base_target + (1 if idx < remainder else 0)
            
            # Build specific system prompt for this chunk
            chunk_system = self.SYSTEM_PROMPT
            if chunk_target > 0:
                chunk_system += (
                    f"\n\nCRITICAL REQUIREMENT: You MUST split this script chunk into EXACTLY {chunk_target} scenes."
                    f" Distribute the script content evenly across all {chunk_target} scenes."
                    f" Your output JSON must contain exactly {chunk_target} objects in the 'scenes' array."
                    f" START NUMBERING FROM {scene_counter}."
                )
            else:
                chunk_system += f"\n\nSTART NUMBERING FROM {scene_counter}."
                
            if status_callback:
                status_callback(f"Parsing script chunk {idx+1}/{len(chunks)} with {self.model}...")
                
            chunk_scenes = self._call_parser(chunk_system, chunk_text, status_callback=None)
            
            # Validation retry for this chunk
            if chunk_target > 0 and len(chunk_scenes) != chunk_target:
                logger.warning(f"Chunk {idx+1} parser returned {len(chunk_scenes)} scenes but target was {chunk_target}. Retrying...")
                retry_system = chunk_system + (
                    f"\n\nYOU PREVIOUSLY RETURNED {len(chunk_scenes)} SCENES. THIS IS WRONG."
                    f" I NEED EXACTLY {chunk_target} SCENES. START NUMBERING FROM {scene_counter}."
                )
                chunk_scenes = self._call_parser(retry_system, chunk_text, status_callback=None)
            
            # Fix scene numbers sequentially just in case the LLM ignored the instruction
            for scene in chunk_scenes:
                scene.scene_number = scene_counter
                scene_counter += 1
                
            all_scenes.extend(chunk_scenes)
            
        scenes = all_scenes

        # Validation: retry once if scene count doesn't match target
        if target_scenes and target_scenes > 0 and len(scenes) != target_scenes:
            logger.warning(f"Parser returned {len(scenes)} scenes but target was {target_scenes}. Retrying with stricter prompt...")
            if status_callback:
                status_callback(f"Got {len(scenes)} scenes, need {target_scenes} — retrying...")
            system += (
                f"\n\nYOU PREVIOUSLY RETURNED {len(scenes)} SCENES. THIS IS WRONG."
                f" I NEED EXACTLY {target_scenes} SCENES. Break longer scenes into"
                f" multiple visual moments. Every beat of the script deserves its own image."
            )
            scenes = self._call_parser(system, script, status_callback=status_callback)
            if len(scenes) != target_scenes:
                logger.warning(f"Retry still returned {len(scenes)} scenes (target: {target_scenes}). Using what we got.")

        return scenes

    def _call_parser(self, system: str, script: str,
                     status_callback=None) -> List[Scene]:
        """Call the LLM Gateway and parse the response into Scene objects."""
        if status_callback:
            status_callback(f"Parsing with {self.model}...")
            
        try:
            parsed = self.llm.generate_json(
                prompt=script,
                system_instruction=system,
                role="parser"
            )
        except Exception as e:
            logger.error(f"SceneParser parsing failed: {e}")
            raise RuntimeError(f"Scene extraction failed using {self.model}: {str(e)}") from e

        # parsed may be a dict {"scenes": [...]} or a bare list [...]
        if isinstance(parsed, list):
            scenes_data = parsed
        else:
            scenes_data = parsed.get("scenes", parsed)
            if not isinstance(scenes_data, list):
                scenes_data = [scenes_data]

        return self._build_scenes(scenes_data)

    def _build_scenes(self, scenes_data: list) -> List[Scene]:
        """Convert raw scene dicts into Scene objects."""
        scenes = []
        for i, s in enumerate(scenes_data):
            # Parse visuals array
            visuals = []
            raw_visuals = s.get("visuals", [])
            if isinstance(raw_visuals, list) and raw_visuals:
                for v in raw_visuals:
                    visuals.append(Visual(
                        visual_type=v.get("visual_type", "key_visual"),
                        visual_description=v.get("visual_description", ""),
                        mood=v.get("mood", ""),
                        key_elements=v.get("key_elements", []),
                    ))

            # Top-level visual_description = first key_visual (backward compat)
            top_desc = s.get("visual_description", "")
            if not top_desc and visuals:
                # Use the first key_visual's description as the top-level one
                kv = next((v for v in visuals if v.visual_type == "key_visual"), visuals[0])
                top_desc = kv.visual_description

            scene = Scene(
                scene_number=s.get("scene_number", i + 1),
                scene_title=s.get("scene_title", f"Scene {i + 1}"),
                visual_description=top_desc,
                mood=s.get("mood", visuals[0].mood if visuals else ""),
                key_elements=s.get("key_elements", visuals[0].key_elements if visuals else []),
                duration_seconds=s.get("duration_seconds", 0),
                original_text=s.get("original_text", ""),
                visuals=visuals,
            )
            scenes.append(scene)

        total_visuals = sum(len(sc.get_visuals()) for sc in scenes)
        logger.info(f"Parsed {len(scenes)} scenes with {total_visuals} total visuals")
        return scenes

