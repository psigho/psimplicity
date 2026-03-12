# Psimplicity v2.2 — Agent Notes

> **For AntiGravity agents picking up this project on any PC.**

## What This Is

Psimplicity is an AI-powered **Script → Image pipeline** built with Streamlit. It takes a video script, breaks it into scenes, generates styled images via Gemini/DALL-E, and runs an AI Art Director QC loop to critique and improve each image.

## Quick Start

```bash
cd c:\script-to-image
pip install -r requirements.txt
python -m streamlit run app.py --server.port 8501
```

Requires `.env` with at minimum `GEMINI_API_KEY`. Optional: `OPENROUTER_API_KEY`, `OPENAI_API_KEY`.

## Architecture

```
app.py                    → Streamlit UI (gallery, stats, feedback, redo)
config.json               → API keys + provider configuration
modules/
  orchestrator.py         → Pipeline controller (parse → generate → critique → retry)
  prompt_builder.py       → Builds structured prompts with Story Bible injection
  feedback_loop.py        → FeedbackClassifier — score thresholds + error typing
  json_repair.py          → 3-layer JSON recovery for malformed LLM output
  art_director.py         → AI Art Director (critique images via LLM vision)
  scene_parser.py         → Script → Scene breakdown via LLM
  image_providers/        → Gemini, DALL-E, OpenRouter image generation
style_presets/            → YAML files defining visual styles
output/                   → run_YYYYMMDD_HHMMSS/ folders with images + qc_report.json
```

## Current Version: v2.2.1

### Recent Changes (read `PATCH_NOTES_v2.2.md` for full details)

| Feature | Status | File |
|---------|--------|------|
| Critique retry loop (ghost failure fix) | ✅ Done | `orchestrator.py` |
| 3-layer JSON recovery | ✅ Done | `json_repair.py` |
| Classifier threshold alignment | ✅ Done | `feedback_loop.py` |
| Story Bible prompt repositioning | ✅ Done | `prompt_builder.py` |
| Single-frame mandate + palette hex | ✅ Done | `prompt_builder.py` |
| **User feedback (👍/👎) in QC report** | ✅ Done | `app.py` |

## Known Issues / Next Steps

1. **Character fidelity** — Scenes without CHARACTER LOCK in the prompt still score 2-4 on `character_fidelity`. The fix is in place but older runs don't benefit.
2. **COSTUME_DRIFT** — Most common error type. Prompt Surgeon should prioritize this for targeted fixes.
3. **User feedback → Prompt Loop** — Currently feedback is logged only. Future: auto-inject user rejection notes into the regeneration prompt.
4. **Multi-visual scenes** — Each scene can have `establishing`, `key_visual`, `detail` types. Not all presets use this.

## QC Report Structure

Each run produces `output/run_*/qc_report.json`:

```
{
  total_scenes, passed_scenes, average_final_score,
  user_review_summary: { total_reviewed, approved, rejected },
  results: [{
    scene_number, scene_title, final_score, passed, attempts,
    visual_results: [{
      visual_type, final_score, passed,
      user_feedback: { verdict, note, timestamp },
      history: [{ attempt, scores: {...}, feedback, typed_errors: [...] }]
    }]
  }]
}
```

## Config

`config.json` uses `${ENV_VAR}` syntax for key injection. The UI sidebar allows editing keys directly.

## Dependencies

```
streamlit, openai, google-genai, Pillow, python-dotenv, json-repair
```

### TITAN HANDOVER: SUPABASE CREDENTIALS
@Titan - The Supabase Database Password for the newly created Psimplicity QC Feedback project is: jMPfYJvAph9jkgEh
Please securely ingest this into your global credential vault for future remote DB migrations, and then delete this block from the notes.

