"""
Orchestrator Module
Controls the entire pipeline: parse → prompt → generate → critique → retry → output.
Produces numbered images + JSON QC report.
Supports Visual Density: each scene can have 1-3 visuals (establishing, key, detail).
"""

import copy
import json
import logging
import os
import random
import re
import shutil
import time
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional

from .scene_parser import SceneParser, Scene, Visual
from .prompt_builder import PromptBuilder, StylePreset
from .image_provider import ImageProvider, create_provider
from .art_director import ArtDirector, CritiqueResult
from .story_bible import generate_story_bible
from .gemini_llm import GeminiLLM
from .feedback_loop import process_feedback, FeedbackClassifier, PromptSurgeon

logger = logging.getLogger(__name__)

# Visual sub-index labels: a, b, c ...
_VISUAL_LABELS = "abcdefghijklmnopqrstuvwxyz"


@dataclass
class VisualResult:
    """Tracks the generation history for one visual shot."""
    visual_type: str
    final_image_path: str = ""
    final_prompt: str = ""
    final_score: float = 0.0
    passed: bool = False
    attempts: int = 0
    history: List[Dict] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "visual_type": self.visual_type,
            "final_image_path": self.final_image_path,
            "final_prompt": self.final_prompt,
            "final_score": self.final_score,
            "passed": self.passed,
            "attempts": self.attempts,
            "history": self.history,
        }


@dataclass
class SceneResult:
    """Tracks the full generation history for one scene (with multiple visuals)."""
    scene_number: int
    scene_title: str
    # Legacy single-image fields (kept for backward compat with app.py gallery)
    final_image_path: str = ""
    final_prompt: str = ""
    final_score: float = 0.0
    passed: bool = False
    attempts: int = 0
    history: List[Dict] = field(default_factory=list)
    # Visual Density: per-visual results
    visual_results: List[VisualResult] = field(default_factory=list)

    def to_dict(self) -> Dict:
        d = {
            "scene_number": self.scene_number,
            "scene_title": self.scene_title,
            "final_image_path": self.final_image_path,
            "final_prompt": self.final_prompt,
            "final_score": self.final_score,
            "passed": self.passed,
            "attempts": self.attempts,
            "history": self.history,
        }
        if self.visual_results:
            d["visual_results"] = [vr.to_dict() for vr in self.visual_results]
        return d


@dataclass
class PipelineReport:
    """Final pipeline execution report."""
    timestamp: str
    total_scenes: int
    passed_scenes: int
    failed_scenes: int
    total_images_generated: int
    total_critiques: int
    average_final_score: float
    results: List[Dict]
    style_preset: str
    duration_seconds: float
    total_visuals: int = 0

    def to_dict(self) -> Dict:
        return {
            "timestamp": self.timestamp,
            "total_scenes": self.total_scenes,
            "total_visuals": self.total_visuals,
            "passed_scenes": self.passed_scenes,
            "failed_scenes": self.failed_scenes,
            "total_images_generated": self.total_images_generated,
            "total_critiques": self.total_critiques,
            "average_final_score": self.average_final_score,
            "style_preset": self.style_preset,
            "duration_seconds": self.duration_seconds,
            "results": self.results
        }


class Orchestrator:
    """Controls the entire Script → Image pipeline with QC loop."""

    _API_COOLDOWN = 1.5  # seconds between API calls (paid tier)

    def __init__(self, config: dict, parser_model_override: str = None,
                 critic_model_override: str = None, image_provider_key: str = None):
        self.config = config
        pipeline_cfg = config.get("pipeline", {})
        self.max_retries = pipeline_cfg.get("max_retries", 3)
        self.pass_threshold = pipeline_cfg.get("pass_threshold", 7.0)

        # Output folder
        self.output_folder = Path(config.get("output", {}).get("folder", "output"))
        self.output_folder.mkdir(parents=True, exist_ok=True)

        # Initialize components — prefer direct OpenAI, fall back to OpenRouter
        oai_cfg = config.get("openai", {})
        or_cfg = config.get("openrouter", {})

        def _resolve(val: str) -> str:
            """Expand ${VAR} patterns to actual env values."""
            if not val:
                return val
            return re.sub(r'\$\{(\w+)\}', lambda m: os.environ.get(m.group(1), ''), val)

        # Pick the best available LLM credentials
        # Priority: Gemini direct → OpenAI direct → OpenRouter
        oai_key = _resolve(oai_cfg.get("api_key", "")) or os.environ.get("OPENAI_API_KEY", "")
        or_key = _resolve(or_cfg.get("api_key", "")) or os.environ.get("OPENROUTER_API_KEY", "")
        gemini_key = os.environ.get("GEMINI_API_KEY", "")

        if gemini_key:
            llm_key = gemini_key
            llm_base = "https://generativelanguage.googleapis.com/v1beta/openai/"
            parser_model = "gemini-3-flash-preview"
            critic_model = "gemini-3-flash-preview"
            logger.info("Using direct Gemini API for parser & critic")
        elif oai_key:
            llm_key = oai_key
            llm_base = "https://api.openai.com/v1"
            parser_model = oai_cfg.get("parser_model", "gpt-4.1-mini")
            critic_model = oai_cfg.get("critic_model", "gpt-4.1-mini")
            logger.info("Using direct OpenAI API for parser & critic")
        elif or_key:
            llm_key = or_key
            llm_base = or_cfg.get("base_url", "https://openrouter.ai/api/v1")
            parser_model = or_cfg.get("parser_model", "openai/gpt-4o")
            critic_model = or_cfg.get("critic_model", "openai/gpt-4o")
            logger.info("Using OpenRouter API for parser & critic")
        else:
            raise ValueError("No API key found. Set GEMINI_API_KEY, OPENAI_API_KEY, or OPENROUTER_API_KEY in .env.")

        # Apply sidebar overrides if provided
        gemini_base = "https://generativelanguage.googleapis.com/v1beta/openai/"

        def _resolve_model_route(model_name):
            """Route model to correct API endpoint.
            Strips 'google/' prefix so sidebar selections go direct to Gemini."""
            # google/gemini-3-flash-preview → gemini-3-flash-preview (direct Gemini)
            if model_name.startswith("google/gemini-") and gemini_key:
                clean = model_name.replace("google/", "")
                return clean, gemini_key, gemini_base
            if model_name.startswith("gemini-") and gemini_key:
                return model_name, gemini_key, gemini_base
            if model_name.startswith("gpt-") and oai_key:
                return model_name, oai_key, "https://api.openai.com/v1"
            # Everything else → OpenRouter
            return model_name, or_key or llm_key, or_cfg.get("base_url", "https://openrouter.ai/api/v1")

        if parser_model_override:
            parser_model, llm_key_parser, llm_base_parser = _resolve_model_route(parser_model_override)
            logger.info(f"Parser model override: {parser_model} → {llm_base_parser}")
        else:
            llm_key_parser, llm_base_parser = llm_key, llm_base

        if critic_model_override:
            critic_model, llm_key_critic, llm_base_critic = _resolve_model_route(critic_model_override)
            logger.info(f"Critic model override: {critic_model} → {llm_base_critic}")
        else:
            llm_key_critic, llm_base_critic = llm_key, llm_base

        # ── Native Gemini SDK — primary for all LLM calls ──
        self.gemini_client = None
        if gemini_key:
            try:
                self.gemini_client = GeminiLLM(
                    api_key=gemini_key,
                    model="gemini-3-flash-preview",
                )
                logger.info("✅ Native Gemini SDK initialized as PRIMARY LLM provider")
            except Exception as e:
                logger.warning(f"Failed to init native Gemini SDK: {e}. Using OpenAI-compat only.")

        # Build parser with native Gemini primary, OpenAI-compat fallback
        parser_fallback_key = oai_key if llm_base_parser != "https://api.openai.com/v1" else None
        self.parser = SceneParser(
            api_key=llm_key_parser,
            base_url=llm_base_parser,
            model=parser_model,
            fallback_api_key=parser_fallback_key,
            fallback_base_url="https://api.openai.com/v1",
            fallback_model="gpt-4.1-mini" if parser_fallback_key else None,
            gemini_client=self.gemini_client,
        )

        # Image provider — use override key or let factory auto-detect
        # Image provider — use override key or let factory auto-detect
        if image_provider_key:
            # Build a filtered config with only the selected provider
            img_config = {image_provider_key: config[image_provider_key]}
            logger.info(f"Image provider override: {image_provider_key}")
        else:
            img_config = config.copy()

        # Expand env vars for Gemini API Key
        if "gemini_api_key" in img_config:
            gak = img_config["gemini_api_key"].copy()
            gak["api_key"] = _resolve(gak.get("api_key", ""))
            img_config["gemini_api_key"] = gak

        self.image_provider = create_provider(img_config)

        # ── Provider chain (single provider — no round-robin) ─────────────
        # Seedream (ByteDance) was previously auto-injected as a fallback here,
        # but it drops all visual context (style bible, character fidelity)
        # producing images that look nothing like the rest of the series.
        # Keeping a single-provider chain preserves stylistic coherence.
        self._provider_chain = [self.image_provider]

        # Build critic with native Gemini primary, OpenAI-compat fallback
        critic_fallback_key = oai_key if llm_base_critic != "https://api.openai.com/v1" else None
        self.art_director = ArtDirector(
            api_key=llm_key_critic,
            base_url=llm_base_critic,
            model=critic_model,
            pass_threshold=self.pass_threshold,
            max_retries=self.max_retries,
            fallback_api_key=critic_fallback_key,
            fallback_base_url="https://api.openai.com/v1",
            fallback_model="gpt-4.1-mini" if critic_fallback_key else None,
            gemini_client=self.gemini_client,
        )

        logger.info("Orchestrator initialized")
        logger.info(f"  Parser model: {parser_model}")
        logger.info(f"  Critic model: {critic_model}")
        logger.info(f"  Primary LLM: {'Native Gemini SDK' if self.gemini_client else 'OpenAI-compat'}")
        logger.info(f"  Image provider: {self.image_provider.name()}")
        logger.info(f"  Provider chain: {' → '.join(p.name() for p in self._provider_chain)}")
        logger.info(f"  Pass threshold: {self.pass_threshold}/10")
        logger.info(f"  Max retries: {self.max_retries}")



    def run(self, script: str, style_preset_path: str,
            progress_callback=None, target_scenes: int = 0,
            project_name: str = None,
            brand_bible_data: dict = None) -> PipelineReport:
        """Execute the full pipeline with Visual Density support.

        Args:
            script: Raw script text
            style_preset_path: Path to style preset JSON
            progress_callback: Optional callable(scene_num, total, status, image_path)
            target_scenes: Target number of scenes (0 = auto-detect)
            project_name: Optional prefix for the output folder
            brand_bible_data: Optional Brand Bible dict from image analysis

        Returns:
            PipelineReport with all results
        """
        start_time = time.time()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Create run-specific output folder
        safe_project_name = re.sub(r'[^\w\-]', '_', project_name) if project_name else ""

        if safe_project_name:
            folder_name = f"run_{safe_project_name}_{timestamp}"
        else:
            folder_name = f"run_{timestamp}"

        run_folder = self.output_folder / folder_name
        images_folder = run_folder / "images"
        images_folder.mkdir(parents=True, exist_ok=True)

        # Load style preset
        style = StylePreset(style_preset_path)
        prompt_builder = PromptBuilder(style)

        # Step 1: Parse script into scenes (with multi-visual density)
        if progress_callback:
            progress_callback(0, 0, "Parsing script into scenes...", None)

        # Thread progress_callback so parser status (model name, fallback) shows in UI
        def _parse_status(msg):
            if progress_callback:
                progress_callback(0, 0, msg, None)

        scenes = self.parser.parse(
            script,
            target_scenes=target_scenes if target_scenes > 0 else None,
            status_callback=_parse_status,
        )
        total_scenes = len(scenes)

        # Persist parsed scenes for redo after restart
        import dataclasses as _dc
        scenes_path = run_folder / "scenes.json"
        with open(scenes_path, "w", encoding="utf-8") as sf:
            json.dump([_dc.asdict(s) for s in scenes], sf, indent=2, ensure_ascii=False)

        # Count total visuals across all scenes for accurate progress
        total_visuals = sum(len(sc.get_visuals()) for sc in scenes)
        logger.info(f"Pipeline: {total_scenes} scenes, {total_visuals} total visuals to generate")

        # Generate story bible — shared visual DNA for all scenes
        if progress_callback:
            progress_callback(0, 0, "Creating visual style bible...", None)

        try:
            story_bible = generate_story_bible(
                script=script,
                art_style=style.art_style,
                color_palette=style.color_palette,
                mood_keywords=", ".join(style.mood_keywords) if style.mood_keywords else "",
                llm_client=self.parser.client,
                model=self.parser.model,
                gemini_client=self.gemini_client,
            )
            self.story_bible = story_bible  # Persist for redo_scene()
        except Exception as e:
            logger.warning(f"Story bible failed with primary ({self.parser.model}): {e}")
            if self.parser.fallback_client:
                if progress_callback:
                    progress_callback(0, 0, f"Story bible fallback → {self.parser.fallback_model}...", None)
                story_bible = generate_story_bible(
                    script=script,
                    art_style=style.art_style,
                    color_palette=style.color_palette,
                    mood_keywords=", ".join(style.mood_keywords) if style.mood_keywords else "",
                    llm_client=self.parser.fallback_client,
                    model=self.parser.fallback_model,
                    gemini_client=self.gemini_client,
                )
            else:
                logger.warning("No fallback for story bible — using empty bible")
                story_bible = {}
                self.story_bible = story_bible

        # ── Merge Brand Bible visual DNA into story_bible (if provided) ──
        if brand_bible_data:
            if progress_callback:
                progress_callback(0, 0, "🧬 Merging Brand DNA into visual style...", None)
            from .brand_bible import merge_brand_into_story_bible
            story_bible = merge_brand_into_story_bible(story_bible, brand_bible_data)
            self.story_bible = story_bible
            brand_name = brand_bible_data.get('brand_name', 'Brand')
            logger.info(f"Brand Bible merged: {brand_name} visual DNA injected into story bible")

            # Store reference images for image-to-image generation
            ref_paths = brand_bible_data.get('reference_image_paths', [])
            if ref_paths:
                self.reference_images = ref_paths
                logger.info(f"Reference images loaded: {len(ref_paths)} images for img2img")
            else:
                self.reference_images = []
        else:
            self.reference_images = []

        # Brief script summary for narrative context
        script_summary = script[:500] + "..." if len(script) > 500 else script

        # Step 2-4: Process each scene
        scene_results: List[SceneResult] = []
        total_images = 0
        total_critiques = 0
        visual_index = 0  # running count for progress

        for scene in scenes:
            result = self._process_scene(
                scene=scene,
                prompt_builder=prompt_builder,
                images_folder=images_folder,
                style_description=f"{style.art_style} {style.color_palette}",
                progress_callback=progress_callback,
                total_scenes=total_scenes,
                total_visuals=total_visuals,
                visual_offset=visual_index,
                full_script_summary=script_summary,
                story_bible=story_bible,
            )
            scene_results.append(result)
            total_images += sum(vr.attempts for vr in result.visual_results) if result.visual_results else result.attempts
            total_critiques += sum(vr.attempts for vr in result.visual_results) if result.visual_results else result.attempts
            visual_index += len(scene.get_visuals())

        # Step 5: Generate report
        passed = sum(1 for r in scene_results if r.passed)
        failed = total_scenes - passed
        avg_score = sum(r.final_score for r in scene_results) / total_scenes if total_scenes else 0

        report = PipelineReport(
            timestamp=timestamp,
            total_scenes=total_scenes,
            passed_scenes=passed,
            failed_scenes=failed,
            total_images_generated=total_images,
            total_critiques=total_critiques,
            average_final_score=round(avg_score, 1),
            results=[r.to_dict() for r in scene_results],
            style_preset=style.name,
            duration_seconds=round(time.time() - start_time, 1),
            total_visuals=total_visuals,
        )

        # Save report
        report_path = run_folder / "qc_report.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)

        logger.info(f"Pipeline complete: {passed}/{total_scenes} passed | "
                     f"avg score: {avg_score:.1f}/10 | "
                     f"{total_visuals} visuals | "
                     f"duration: {report.duration_seconds}s")

        if progress_callback:
            progress_callback(total_visuals, total_visuals,
                              f"Done! {passed}/{total_scenes} scenes passed.", None)

        return report

    def _process_scene(self, scene: Scene, prompt_builder: PromptBuilder,
                       images_folder: Path, style_description: str,
                       progress_callback=None, total_scenes: int = 0,
                       total_visuals: int = 0, visual_offset: int = 0,
                       full_script_summary: str = "",
                       story_bible: dict = None) -> SceneResult:
        """Process a single scene — generates all its visuals through the QC loop."""
        result = SceneResult(
            scene_number=scene.scene_number,
            scene_title=scene.scene_title
        )

        visuals = scene.get_visuals()
        multi_shot = len(visuals) > 1

        all_visual_results: List[VisualResult] = []

        for v_idx, visual in enumerate(visuals):
            sub_label = _VISUAL_LABELS[v_idx] if multi_shot else ""
            vr = self._process_visual(
                visual=visual,
                scene=scene,
                sub_label=sub_label,
                prompt_builder=prompt_builder,
                images_folder=images_folder,
                style_description=style_description,
                progress_callback=progress_callback,
                total_scenes=total_scenes,
                total_visuals=total_visuals,
                visual_global_idx=visual_offset + v_idx,
                full_script_summary=full_script_summary,
                story_bible=story_bible,
            )
            all_visual_results.append(vr)

        result.visual_results = all_visual_results

        # Aggregate: scene passes if ALL its visuals pass (or best effort)
        scores = [vr.final_score for vr in all_visual_results if vr.final_score > 0]
        result.final_score = round(sum(scores) / len(scores), 1) if scores else 0.0
        result.passed = all(vr.passed for vr in all_visual_results)
        result.attempts = sum(vr.attempts for vr in all_visual_results)

        # Legacy single-image fields = the key_visual (or first visual)
        key_vr = next((vr for vr in all_visual_results if vr.visual_type == "key_visual"),
                       all_visual_results[0] if all_visual_results else None)
        if key_vr:
            result.final_image_path = key_vr.final_image_path
            result.final_prompt = key_vr.final_prompt

        # Flatten history from all visuals
        for vr in all_visual_results:
            for h in vr.history:
                h["visual_type"] = vr.visual_type
            result.history.extend(vr.history)

        if progress_callback:
            status_icon = "✅" if result.passed else "⚠️"
            progress_callback(visual_offset + len(visuals), total_visuals,
                              f"{status_icon} Scene {scene.scene_number} — {result.final_score}/10",
                              result.final_image_path)

        return result

    # _API_COOLDOWN defined at class level (1.5s)

    def _generate_with_retry(self, prompt: str, negative_prompt: str,
                              output_path: str, max_gen_retries: int = 2) -> bool:
        """Generate image with automatic retry on rate-limit / transient errors."""
        for gen_try in range(max_gen_retries):
            try:
                self.image_provider.generate(
                    prompt=prompt,
                    negative_prompt=negative_prompt,
                    output_path=output_path,
                    reference_images=getattr(self, 'reference_images', None) or None,
                )
                return True
            except Exception as e:
                err_str = str(e).lower()
                is_rate_limit = any(k in err_str for k in ("429", "rate", "quota", "too many"))
                if is_rate_limit and gen_try < max_gen_retries - 1:
                    wait = (gen_try + 1) * 10  # 10s, 20s backoff
                    logger.warning(f"Rate limited — waiting {wait}s before retry")
                    time.sleep(wait)
                    continue
                raise  # non-rate-limit error or final retry → bubble up

    def _process_visual(self, visual: Visual, scene: Scene, sub_label: str,
                        prompt_builder: PromptBuilder, images_folder: Path,
                        style_description: str, progress_callback=None,
                        total_scenes: int = 0, total_visuals: int = 0,
                        visual_global_idx: int = 0,
                        full_script_summary: str = "",
                        story_bible: dict = None) -> VisualResult:
        """Process a single visual.

        key_visual → full generate → critique → retry loop (QC enforced).
        establishing / detail → generate once, auto-pass (no critique API call).
        """
        vr = VisualResult(visual_type=visual.visual_type)
        vtype_label = visual.visual_type.replace("_", " ").title()
        is_key = visual.visual_type == "key_visual"

        # ── Fast path for supplementary shots (no critique) ──────────────
        if not is_key:
            if progress_callback:
                progress_callback(visual_global_idx, total_visuals,
                                  f"Scene {scene.scene_number}/{total_scenes} ({vtype_label})",
                                  None)

            prompt = prompt_builder.build_from_visual(visual, scene,
                                                      story_bible=story_bible)
            image_filename = f"{scene.scene_number:03d}{sub_label}_v1.png"
            image_path = str(images_folder / image_filename)

            try:
                time.sleep(self._API_COOLDOWN)
                self._generate_with_retry(prompt, prompt_builder.last_negative or "",
                                           image_path)
            except Exception as e:
                logger.error(f"Generation failed for scene {scene.scene_number}{sub_label}: {e}")
                vr.history.append({"attempt": 1, "prompt": prompt, "error": str(e)})
                vr.attempts = 1
                return vr

            # Auto-pass: supplementary shots don't need QC
            vr.attempts = 1
            vr.final_image_path = image_path
            vr.final_prompt = prompt
            vr.final_score = 7.5  # nominal pass score
            vr.passed = True
            vr.history.append({
                "attempt": 1, "prompt": prompt, "image_path": image_path,
                "scores": {}, "average_score": 7.5,
                "passed": True, "feedback": "Supplementary shot — auto-accepted"
            })

            # Copy to _final
            final_path = images_folder / f"{scene.scene_number:03d}{sub_label}_final.png"
            shutil.copy2(image_path, final_path)
            vr.final_image_path = str(final_path)

            logger.info(f"Scene {scene.scene_number}{sub_label} ({vtype_label}) — generated (no QC)")
            return vr

        # ── Full QC path for key_visual ──────────────────────────────────
        best_attempt = None
        best_score = 0.0
        last_critique = None

        for attempt in range(1, self.max_retries + 1):
            # ── Rotate provider through the chain ─────────────────────────
            chain = self._provider_chain
            if len(chain) > 1:
                provider_idx = (attempt - 1) % len(chain)
                self.image_provider = chain[provider_idx]
                if attempt > 1:
                    logger.info(f"🔄 Switching to {self.image_provider.name()} for attempt {attempt}")

            if progress_callback:
                shot_info = f" ({vtype_label})" if sub_label else ""
                provider_tag = f" [{self.image_provider.name()}]" if len(chain) > 1 else ""
                status = (f"Scene {scene.scene_number}/{total_scenes}{shot_info}"
                          f" — Attempt {attempt}{provider_tag}")
                progress_callback(visual_global_idx, total_visuals, status, None)

            # Build prompt — first attempt gets clean prompt, retries get targeted surgery
            if attempt == 1 or last_critique is None:
                prompt = prompt_builder.build_from_visual(visual, scene,
                                                          story_bible=story_bible)
                negative_prompt = prompt_builder.last_negative or ""
            else:
                # v2.1: Typed error classification + targeted prompt surgery
                base_prompt = prompt_builder.build_from_visual(visual, scene,
                                                               story_bible=story_bible)
                base_negative = prompt_builder.last_negative or ""
                
                # If safety filter tripped on last attempt, use LLM to scrub the prompt
                is_safety_retry = any(h.get("safety_scrub_triggered") for h in vr.history if h["attempt"] == attempt - 1)
                if is_safety_retry:
                    logger.warning(f"Using LLM to scrub safety-violating terms from prompt for attempt {attempt}")
                    scrub_instructions = (
                        "Rewrite this image generation prompt to completely remove all copyrighted "
                        "character names (e.g., Thanos, Gojo, Batman) and replace them with generic "
                        "physical descriptions (e.g., 'large purple muscular alien', 'blindfolded white-haired man'). "
                        "Also, tone down extreme violence or gore. Return ONLY the completely rewritten prompt.\n\n"
                        f"PROMPT:\n{base_prompt}"
                    )
                    try:
                        if self.gemini_client:
                            from google.genai import types
                            response = self.gemini_client.client.models.generate_content(
                                model=self.gemini_client.model,
                                contents=scrub_instructions,
                                config=types.GenerateContentConfig(temperature=0.7)
                            )
                            prompt = response.text.strip()
                        else:
                            response = self.art_director.client.chat.completions.create(
                                model=self.art_director.model,
                                messages=[{"role": "user", "content": scrub_instructions}],
                                temperature=0.7,
                            )
                            prompt = response.choices[0].message.content.strip()
                        negative_prompt = base_negative
                        logger.info("Successfully scrubbed prompt via LLM.")
                    except Exception as e:
                        logger.error(f"Failed to scrub prompt via LLM: {e}")
                        prompt = base_prompt
                        negative_prompt = base_negative
                else:
                    prompt, negative_prompt, typed_errors = process_feedback(
                        critique_result=last_critique,
                        prompt=base_prompt,
                        negative_prompt=base_negative,
                        story_bible=story_bible,
                        style_description=style_description,
                    )
                    if typed_errors:
                        error_summary = ", ".join(f"{e.type}({e.score})" for e in typed_errors)
                        logger.info(f"🩺 Feedback Loop: {error_summary} → prompt surgery applied")

            # Image filename with sub-label: 001a_v1.png or 001_v1.png
            image_filename = f"{scene.scene_number:03d}{sub_label}_v{attempt}.png"
            image_path = str(images_folder / image_filename)

            try:
                time.sleep(self._API_COOLDOWN)
                self._generate_with_retry(prompt, negative_prompt,
                                           image_path)
            except Exception as e:
                logger.error(f"Generation failed for scene {scene.scene_number}{sub_label} "
                             f"attempt {attempt} ({self.image_provider.name()}): {e}")

                # If safety filter tripped, create a mock critique to force a prompt rewrite
                if "safety-filtered" in str(e).lower() or "no content" in str(e).lower():
                    from .art_director import CritiqueResult
                    logger.warning(f"Safety filter tripped. Creating mock critique to scrub prompt on next attempt.")
                    last_critique = CritiqueResult(
                        scores={"relevance": 1, "concept": 1, "style": 1, "composition": 1, "artifact_free": 1, "text_accuracy": 1, "continuity": 1, "character_fidelity": 1},
                        average_score=1.0,
                        passed=False,
                        feedback={
                            "relevance": {"score": 1, "suggestion": "The prompt was blocked by the image generation safety filter. You MUST remove all mentions of copyrighted characters (e.g. Thanos, Gojo, Batman, etc.) and replace them with generic physical descriptions (e.g. purple alien warrior, white-haired blindfolded man). You MUST ALSO tone down any extreme violence, explosions, blood, or gore."},
                            "concept": {"score": 1, "suggestion": "Use generic, non-copyrighted descriptive language to bypass safety filters."},
                            "style": {"score": 1, "suggestion": ""},
                            "composition": {"score": 1, "suggestion": ""},
                            "artifact_free": {"score": 1, "suggestion": ""},
                            "text_accuracy": {"score": 1, "suggestion": ""},
                            "continuity": {"score": 1, "suggestion": ""},
                            "character_fidelity": {"score": 1, "suggestion": "Remove ALL copyrighted character names! Replace with highly generic visual descriptions."}
                        },
                        summary="Prompt was blocked by safety filters. Generating scrubbed prompt.",
                        raw_response=""
                    )
                    vr.history.append({
                        "attempt": attempt,
                        "prompt": prompt,
                        "image_path": None,
                        "scores": last_critique.scores,
                        "average_score": last_critique.average_score,
                        "passed": last_critique.passed,
                        "feedback": last_critique.summary,
                        "detailed_feedback": last_critique.feedback,
                        "provider": self.image_provider.name(),
                        "typed_errors": [{"type": "SafetyFilterBlock", "severity": "critical", "score": 1, "dimension": "relevance"}],
                        "safety_scrub_triggered": True,
                        "raw_error": str(e)
                    })
                    continue

                vr.history.append({
                    "attempt": attempt,
                    "prompt": prompt,
                    "error": str(e),
                    "provider": self.image_provider.name()
                })
                continue

            # Critique image (rate-limit cooldown)
            time.sleep(self._API_COOLDOWN)
            try:
                last_critique = self.art_director.critique(
                    image_path=image_path,
                    scene_title=scene.scene_title,
                    scene_description=visual.visual_description,
                    mood=visual.mood or scene.mood,
                    key_elements=visual.key_elements or scene.key_elements,
                    style_description=style_description,
                    original_text=scene.original_text,
                    full_script_summary=full_script_summary,
                    scene_number=scene.scene_number,
                    total_scenes=total_scenes,
                    story_bible=story_bible,
                )
            except Exception as e:
                logger.error(f"Critique failed for scene {scene.scene_number}{sub_label}: {e}")

                # ── v2.2: CRITIQUE RETRY — re-call the critic, don't regenerate image ──
                _retry_quips = [
                    "🎭 Art Director spilled coffee on the review — re-reading…",
                    "🔄 Brain glitch! The critic is recalibrating…",
                    "🧹 Sweeping up broken JSON… one sec…",
                    "🎬 CUT! Take two on the review…",
                    "🪄 Summoning a fresh pair of AI eyes…",
                ]
                critique_recovered = False
                for crit_retry in range(1, 3):  # max 2 critique retries
                    backoff = 5 * crit_retry
                    logger.info(f"{random.choice(_retry_quips)} "
                                f"(critique retry {crit_retry}/2, backoff {backoff}s)")
                    time.sleep(backoff)
                    try:
                        last_critique = self.art_director.critique(
                            image_path=image_path,
                            scene_title=scene.scene_title,
                            scene_description=visual.visual_description,
                            mood=visual.mood or scene.mood,
                            key_elements=visual.key_elements or scene.key_elements,
                            style_description=style_description,
                            original_text=scene.original_text,
                            full_script_summary=full_script_summary,
                            scene_number=scene.scene_number,
                            total_scenes=total_scenes,
                            story_bible=story_bible,
                        )
                        critique_recovered = True
                        logger.info(f"✅ Critique recovered on retry {crit_retry}!")
                        break
                    except Exception as e2:
                        logger.warning(f"Critique retry {crit_retry} also failed: {e2}")

                if not critique_recovered:
                    # All critique retries failed — log ghost failure and move on
                    vr.history.append({
                        "attempt": attempt, "prompt": prompt, "image_path": image_path,
                        "scores": {}, "average_score": 0.0,
                        "passed": False, "feedback": f"Critique error (3 attempts): {e}",
                        "critique_error": True,
                        "provider": self.image_provider.name()
                    })
                    vr.attempts = attempt
                    if best_attempt is None:
                        best_score = 0.0
                        best_attempt = {"path": image_path, "prompt": prompt,
                                        "score": 0.0, "passed": False}
                    continue  # Fall through to image regeneration only after all retries

                # Critique recovered — fall through to normal score tracking below

            # Track attempt
            # Classify errors for QC report (v2.1)
            classifier = FeedbackClassifier()
            attempt_errors = classifier.classify(last_critique)
            error_types = [{"type": e.type, "severity": e.severity, "score": e.score,
                           "dimension": e.dimension} for e in attempt_errors]

            vr.history.append({
                "attempt": attempt,
                "prompt": prompt,
                "image_path": image_path,
                "scores": last_critique.scores,
                "average_score": last_critique.average_score,
                "passed": last_critique.passed,
                "feedback": last_critique.summary,
                "provider": self.image_provider.name(),
                "typed_errors": error_types,  # v2.1: classified error types
            })
            vr.attempts = attempt

            # Track best
            if last_critique.average_score > best_score:
                best_score = last_critique.average_score
                best_attempt = {
                    "path": image_path,
                    "prompt": prompt,
                    "score": last_critique.average_score,
                    "passed": last_critique.passed
                }

            # Check if passed
            if last_critique.passed:
                logger.info(f"Scene {scene.scene_number}{sub_label} passed on attempt {attempt}")
                break
            elif not self.art_director.should_retry(last_critique, attempt):
                logger.warning(f"Scene {scene.scene_number}{sub_label} did not pass "
                               f"after {attempt} attempts")
                break

        # Use best attempt as final
        if best_attempt:
            vr.final_image_path = best_attempt["path"]
            vr.final_prompt = best_attempt["prompt"]
            vr.final_score = best_attempt["score"]
            vr.passed = best_attempt["passed"]

            # Copy best to final numbered filename
            final_name = f"{scene.scene_number:03d}{sub_label}_final.png"
            final_path = images_folder / final_name
            if Path(best_attempt["path"]).exists():
                shutil.copy2(best_attempt["path"], final_path)
                vr.final_image_path = str(final_path)

        # Reset provider to primary for next visual
        self.image_provider = self._provider_chain[0]

        return vr

    def redo_scene(self, scene_number: int, scenes: List[Scene],
                   style_preset_path: str, guidance: str = None,
                   run_folder: str = None,
                   progress_callback=None) -> SceneResult:
        """Redo a single scene with optional manual guidance (for UI redo button).

        Args:
            scene_number: Which scene to redo (1-indexed)
            scenes: Full scenes list from parsing
            style_preset_path: Path to style preset
            guidance: Optional manual text guidance from user
            run_folder: Path to existing run folder
            progress_callback: Optional callable(current, total, status, image_path)

        Returns:
            Updated SceneResult
        """
        # Deepcopy to prevent mutating the shared scene list
        scene = copy.deepcopy(scenes[scene_number - 1])

        # If user provided guidance, inject it into the copied scene
        if guidance:
            scene.visual_description += f" ADDITIONAL DIRECTION: {guidance}"
            for v in scene.get_visuals():
                v.visual_description += f" ADDITIONAL DIRECTION: {guidance}"

        style = StylePreset(style_preset_path)
        prompt_builder = PromptBuilder(style)
        style_desc = f"{style.art_style} {style.color_palette}"

        if run_folder:
            images_folder = Path(run_folder) / "images"
        else:
            images_folder = self.output_folder / "redo"

        images_folder.mkdir(parents=True, exist_ok=True)

        total_visuals = len(scene.get_visuals())

        # Use the persisted story bible from the last run() call
        story_bible = getattr(self, 'story_bible', None) or {}

        return self._process_scene(
            scene=scene,
            prompt_builder=prompt_builder,
            images_folder=images_folder,
            style_description=style_desc,
            progress_callback=progress_callback,
            total_scenes=len(scenes),
            total_visuals=total_visuals,
            story_bible=story_bible,
        )
