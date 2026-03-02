# Psimplicity v2.2 — QC-Driven Patch

**Release Date:** 2026-02-18

> Data-driven fixes from aggregated analysis of 13 QC reports (80 scenes, 109 critiques).

---

## 🔴 P0: Eliminate Ghost Failures (59% of all failures)

### Critique Retry Loop (`orchestrator.py`)

**Before:** When Gemini returned broken JSON, the system logged a fake 0.0 score and regenerated the image with the identical prompt — wasting all 3 retry attempts.

**After:** The orchestrator retries the *critique call* (up to 2 times with increasing backoff) before falling back to image regeneration. Only when all 3 critique attempts fail does it continue to the next image generation attempt.

### Enhanced JSON Recovery (`json_repair.py`)

**Before:** Two-layer recovery: strip fences → regex brace extraction. Failed on truncated output, unquoted properties, and mismatched brackets.

**After:** Three-layer recovery: strip fences → regex extraction → `json_repair` library (pip). The library handles Gemini's most common failure modes and gracefully skips if not installed.

---

## 🟡 P1: Fix Real Quality Failures

### Classifier Threshold Alignment (`feedback_loop.py`)

**Before:** All error rules had `threshold: 5`. Scores 5-6 (which ARE failures below the Art Director's 7.0 pass threshold) were never classified or surgically fixed.

**After:**

- `hard_fail` types (TEXT_HALLUCINATION, ANATOMY_ERROR, COSTUME_DRIFT): threshold → 6
- `soft_fail` types (CONSISTENCY_BREAK, STYLE_MISMATCH, etc.): threshold → 7

### Story Bible Prompt Repositioning (`prompt_builder.py`)

**Before:** Character fidelity = position 5 of 6. Continuity = position 6 of 6. Image generators "forget" late-prompt constraints.

**After (new priority order):**

1. `SINGLE IMAGE FRAME` mandate (prevents comic panels)
2. Script context
3. `CHARACTER LOCK` (exact descriptions from bible)
4. `CONTINUITY MANDATE` + `MANDATORY COLOR PALETTE` (hex codes)
5. Visual description
6. Style

---

## 🟢 P2: Prevent Specific Hallucinations

### Single-Frame Mandate (`prompt_builder.py`)

Every prompt now starts with: *"SINGLE IMAGE FRAME. No panels, no comic layout, no split screen, no multiple views. One continuous scene only."*

### Palette Hex Injection (`prompt_builder.py`)

Extracts `color_palette` from story bible (supports list of hex codes or string) and injects as `MANDATORY COLOR PALETTE` in position 4.

---

## Files Changed

| File | Change |
|------|--------|
| `modules/orchestrator.py` | Critique retry loop (lines 653-710) |
| `modules/json_repair.py` | Layer 3: `json_repair` library fallback |
| `modules/feedback_loop.py` | All 8 thresholds raised |
| `modules/prompt_builder.py` | Prompt structure reordered + single-frame + palette |

## 🆕 User Feedback System (v2.2.1)

### In-App Review (`app.py`)

Each generated image now shows 👍 **Approve** / 👎 **Reject** buttons directly on the card. After clicking, a badge shows ✅ Approved or ❌ Rejected. Users can:

- Add optional free-text notes per image
- Change verdicts anytime via ✏️ Change feedback expander  
- See a live **👤 User Reviewed** counter in the stats panel

### QC Report Persistence

All feedback writes to `qc_report.json`:

```json
{
  "user_feedback": { "verdict": "approved", "note": "...", "timestamp": "..." }
}
```

Top-level `user_review_summary` auto-computes: `{ total_reviewed, approved, rejected }`

### Purpose

Captures **human ground truth** alongside AI Art Director scores. Enables:

- AI vs. Human score calibration
- Prompt surgery effectiveness tracking
- Cross-run user satisfaction comparison

---

## New Dependency

```
pip install json-repair
```

---

## 🚨 Hotfix: API Key Loading Safety (v2.2.2)

### `.env` File Creation (`START.bat`)

**Before:** The setup script forcefully overwrote the `.env` template using `> ".env"`. If a user pressed Enter without pasting a key, the file was wiped empty, losing all template structure.
**After:** Safely appends (`>>`) the API key strings to `.env` using delayed expansion-safe syntax, preserving existing template comments and placeholders.

### Orchestrator Initialization (`app.py`)

**Before:** The backend `Orchestrator` initialized outside the main Streamlit interface `try..except` block. A missing `.env` key raised a ValueError that instantly crashed the app, preventing users from accessing the UI to input their keys.
**After:** `Orchestrator` instantiation moved safely inside the `try..except` pipeline block. Missing keys now gracefully surface as UI errors, allowing the app to stay alive and the user to enter their credentials.
