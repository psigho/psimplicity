# Psimplicity — AI Script → Image Pipeline

> Paste a video script. Get production-ready images with automated AI quality control.

Built for fast-turnaround commentary and philosophy videos. Paste your script, click Generate, and receive a folder of stylistically consistent, AI-critiqued images ready for your video editor.

---

## How It Works

```text
Script Text → Scene Segmentation → Prompt Generation → Image Generation
                                                              ↓
                                              AI Art Director Critique
                                                     ↓         ↓
                                                  PASS       FAIL → Revise prompt → Regenerate
                                                     ↓                    (up to 3 retries)
                                              Final Images + QC Report
```

### The AI Quality Control Loop (Heart of the System)

After every image is generated, an AI Art Director scores it across **8 dimensions**:

| Dimension | What It Measures |
| --- | --- |
| **Relevance** | Does the image match the actual script scene? |
| **Concept** | Is the visual metaphor clear and intentional? |
| **Style** | Does it match the chosen style preset? |
| **Composition** | Framing, layout, visual readability |
| **Artifact-Free** | No AI slop, bad hands, text glitches |
| **Text Accuracy** | Any text rendered must be correct |
| **Continuity** | Visual consistency across all scenes (Story Bible) |
| **Character Fidelity** | Do characters match their roster descriptions? |

- **Pass threshold**: Average ≥ 7.0/10
- **Relevance hard gate**: Relevance score alone must be ≥ 7 (a pretty image that doesn't match the script auto-fails)
- **Max retries**: 3 per image (prevents infinite loops)
- Failed images get revised prompts based on the Art Director's specific feedback

---

## Quick Start (1 minute)

### ⚡ 1-Click Windows Installer (Recommended)

Run the following command in PowerShell:

```powershell
irm https://raw.githubusercontent.com/psigho/psimplicity/main/install.ps1 | iex
```

*This will automatically install Python/Git (if missing), download the app, and launch it!*

---

### Manual Installation (Advanced)

#### 1. Prerequisites

- **Python 3.10+** — [Download Python](https://www.python.org/downloads/)
- **Git** — [Download Git](https://git-scm.com/downloads)

#### 2. Clone & Install

```bash
git clone https://github.com/psigho/psimplicity.git
cd psimplicity
pip install -r requirements.txt
```

### 3. Get Your API Keys

You need **one LLM key** (for parsing & critique) and **one image generation key**.

#### Option A: Gemini Only (Recommended — one key does everything)

Get a free Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey):

1. Go to <https://aistudio.google.com/apikey>
2. Click **"Create API Key"**
3. Copy the key

This single key powers:

- ✅ Script parsing (Gemini 2.5 Flash)
- ✅ AI Art Director critique (Gemini 2.5 Flash)
- ✅ Image generation (Gemini 3 Pro Image — "Nano Banana Pro")

#### Option B: OpenAI + Separate Image Generator

- Get an OpenAI key from [platform.openai.com/api-keys](https://platform.openai.com/api-keys)
- For image generation, you'll also need a Gemini key (see Option A) or configure DALL-E 3

#### Option C: OpenRouter (Access to 100+ models)

- Get a key from [openrouter.ai/keys](https://openrouter.ai/keys)
- Routes through OpenRouter to access Gemini, Claude, DeepSeek, Qwen, etc.

### 4. Configure API Keys

Copy the example environment file and add your keys:

```bash
cp .env.example .env
```

Edit `.env` with your keys:

```config
# Required — at least one LLM key
GEMINI_API_KEY=your_gemini_key_here

# Optional — additional providers
OPENAI_API_KEY=your_openai_key_here
OPENROUTER_API_KEY=your_openrouter_key_here
```

### 5. Run

```bash
streamlit run app.py
```

Open <http://localhost:8501> in your browser.

---

## Usage

### Basic Workflow

1. **Paste your script** in the main text area
2. **Choose a style preset** from the sidebar (8 built-in styles)
3. **Set scene count** — how many images you want (or leave auto)
4. **Click "Generate"** — the pipeline runs automatically
5. **Review results** — images appear in a grid with QC scores
6. **Redo any image** — click the redo button, optionally add guidance text

### Sidebar Controls

| Control | What It Does |
| --- | --- |
| **Style Preset** | Visual style for all images (Watercolor, Noir, Anime, etc.) |
| **Scene Count** | Target number of images (auto if left at 0) |
| **Parser Model** | Which AI parses your script into scenes |
| **Image Generator** | Which engine generates images |
| **Project Name** | Labels your output folder |

### Redo an Image

Click the **Redo** button on any image. You can optionally type guidance like:

- "Make this more symbolic"
- "Show the character from a different angle"
- "More dramatic lighting"

The system sends it back through the full AI QC loop.

---

## Style Presets

8 built-in presets, each with art direction, color palette, mood, and negative prompt:

| Preset | Best For |
| --- | --- |
| 🎨 **Watercolor Storybook** | Soft, emotional philosophy videos |
| 🖤 **Noir Thriller** | Dark, moody commentary |
| 🎬 **Cinematic Documentary** | Serious, professional content |
| ✏️ **B&W Pencil Sketch** | Minimalist, intellectual feel |
| 🌊 **Retro Synthwave** | Nostalgia, pop culture commentary |
| ⚔️ **Anime Epic** | High-energy, dramatic content |
| 🧠 **Philosophy Dark** | Abstract, thought-provoking visuals |
| 🎪 **Pixar/Dreamworks** | Fun, accessible explainers |

You can also create custom presets — just add a new `.json` file in `style_presets/`.

---

## Project Structure

```text
script-to-image/
├── app.py                    # Streamlit UI (main entry point)
├── config.json               # Model & pipeline configuration
├── requirements.txt          # Python dependencies
├── .env                      # Your API keys (never committed)
├── .env.example              # Template for .env
│
├── modules/
│   ├── scene_parser.py       # Script → structured scenes (LLM)
│   ├── prompt_builder.py     # Scene → image generation prompt
│   ├── image_provider.py     # Image generation (Gemini/DALL-E/Imagen)
│   ├── art_director.py       # AI critique + scoring (8 dimensions)
│   ├── story_bible.py        # Visual DNA consistency across scenes
│   └── orchestrator.py       # Pipeline controller (ties everything together)
│
├── style_presets/             # 8 built-in visual style configs
│   ├── watercolor_storybook.json
│   ├── noir_thriller.json
│   └── ... (6 more)
│
└── output/                   # Generated images + reports (per run)
    └── run_ProjectName_YYYYMMDD_HHMMSS/
        ├── images/           # Final numbered images
        ├── scenes.json       # Parsed scene data
        └── report.json       # Full QC report with scores
```

---

## Output Structure

Each run creates a folder in `output/` containing:

| File | Contents |
| --- | --- |
| `images/scene_01_v1.png` | Final images, numbered by scene |
| `scenes.json` | Parsed scenes with titles, descriptions, key elements |
| `report.json` | Full pipeline report: prompts used, all critique scores, retry history |

The **report.json** includes for every image:

- The prompt that generated it
- All Art Director scores (relevance, concept, style, composition, artifact-free, text, continuity, character fidelity)
- Average score and pass/fail status
- Revision history if the image was regenerated

---

## Supported Image Generators

| Generator | Key Needed | Notes |
| --- | --- | --- |
| **Nano Banana Pro** (Gemini 3 Pro Image) | `GEMINI_API_KEY` | Recommended — best quality/speed |
| **Imagen 3.0** | Google Cloud credentials | Enterprise-grade |
| **DALL-E 3** | `OPENAI_API_KEY` | OpenAI's generator |

The system is **modular** — swap generators from the sidebar without changing code.

---

## Supported LLM Models (Parser & Critic)

| Model | Provider | Best For |
| --- | --- | --- |
| **Gemini 2.5 Flash** ⚡ | Direct Gemini | Fast, free tier available |
| **GPT-4.1 Mini** | Direct OpenAI | Reliable, good JSON output |
| **Gemini 2.5 Pro** 👑 | OpenRouter | Premium quality |
| **Claude 4 Sonnet** 💎 | OpenRouter | Nuanced understanding |
| **DeepSeek R1** 🧠 | OpenRouter | Deep reasoning |

Select from the sidebar dropdown. The system auto-routes to the correct API.

---

## Troubleshooting

| Issue | Solution |
| --- | --- |
| **"No API key found"** | Add at least one key to `.env` (see Step 4) |
| **Images don't match script** | The AI Art Director auto-rejects irrelevant images. Try increasing max retries in config. |
| **Stuck on "Parsing..."** | Your LLM provider may be down. Switch parser model in sidebar. |
| **502 Bad Gateway** | OpenRouter is down. Switch to Gemini Flash (direct) in sidebar — it bypasses OpenRouter. |
| **Slow generation** | Image generation takes 10-30s per image. 7 scenes × 3 retries = a few minutes. |

---

## Configuration

Edit `config.json` to change defaults:

```json
{
  "pipeline": {
    "max_retries": 3,         // Max regeneration attempts per image
    "pass_threshold": 7.0,    // Minimum average score to pass (1-10)
    "images_per_scene": 1     // Images per scene
  }
}
```

---

## License

Private project. All rights reserved.
