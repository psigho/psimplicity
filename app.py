"""
Script-to-Image Pipeline — Streamlit UI
=========================================
Paste a script → Generate styled images → View in grid → Click to redo.

Run: streamlit run app.py
"""

import json
import logging
import os
import random
import re
import shutil
import time
import zipfile
import io
import streamlit as st
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
load_dotenv()
from modules.orchestrator import Orchestrator

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def _resolve_env(val: str) -> str:
    """Expand ${VAR} patterns to actual env values."""
    if not val:
        return val
    return re.sub(r'\$\{(\w+)\}', lambda m: os.environ.get(m.group(1), ''), val)

def _get_llm_credentials(config: dict):
    """Return (api_key, base_url, model) from config with env var resolution."""
    oai = config.get("openai", {})
    orc = config.get("openrouter", {})
    oai_key = _resolve_env(oai.get("api_key", "")) or os.environ.get("OPENAI_API_KEY", "")
    or_key = _resolve_env(orc.get("api_key", "")) or os.environ.get("OPENROUTER_API_KEY", "")
    if oai_key:
        return oai_key, "https://api.openai.com/v1", oai.get("parser_model", "gpt-4.1-mini")
    elif or_key:
        return or_key, orc.get("base_url", "https://openrouter.ai/api/v1"), orc.get("parser_model", "openai/gpt-4o")
    return "", "", ""

# ── Page Config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Psimplicity | Psio.io",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── Custom CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&family=Inter:wght@300;400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
    /* ──── PSIO.IO Aesthetic ── */
    :root {
        --bg-color: #050508;
        --surface-color: #0a0a10;
        --accent-color: #00d4aa;
        --accent-gradient: linear-gradient(135deg, #00d4aa 0%, #00b4dc 100%);
        --text-color: #e8e8ec;
        --text-dim: #8b949e;
        --border-color: #1a1e28;
    }

    /* ──── Global Font ── */
    body, .stApp, .stMarkdown, p, span, div, label, h1, h2, h3, h4, h5, h6,
    button, input, textarea, select, option, li, td, th {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
        color: var(--text-color) !important;
    }
    .stApp {
        background-color: var(--bg-color) !important;
    }
    h1, h2, h3, .main-title, .ancap-logo {
        font-family: 'Space Grotesk', sans-serif !important;
    }
    code, pre, .stCode, [data-testid="stCode"] { font-family: 'JetBrains Mono', monospace !important; }

    /* ──── Selectbox: pointer cursor ── */
    [data-testid="stSelectbox"], [data-testid="stSelectbox"] * { cursor: pointer !important; }
    /* ──── NUKE ALL Material Symbols / Ghost Text ── */
    .material-symbols-rounded,
    [class*="material-symbols"],
    span.material-symbols-rounded,
    .stApp span[class*="material"] {
        font-size: 0 !important;
        width: 0 !important;
        height: 0 !important;
        overflow: hidden !important;
        display: inline-block !important;
        line-height: 0 !important;
        visibility: hidden !important;
        position: absolute !important;
    }

    /* ──── Hide ALL Streamlit chrome ── */
    [data-testid="collapsedControl"],
    [data-testid="stSidebarCollapseButton"],
    button[kind="headerNoPadding"],
    #MainMenu, .stDeployButton, 
    header .stToolbar,
    [data-testid="stStatusWidget"],
    [data-testid="InputInstructions"],
    footer,
    header[data-testid="stHeader"] .stToolbar,
    header[data-testid="stHeader"] [data-testid="stToolbar"] {
        display: none !important;
        visibility: hidden !important;
        height: 0 !important;
        width: 0 !important;
        overflow: hidden !important;
        position: absolute !important;
    }

    /* ──── Selectbox: pointer cursor + kill "open" tooltip ── */
    [data-baseweb="select"] {
        cursor: pointer !important;
    }
    [data-baseweb="select"] input {
        cursor: pointer !important;
        caret-color: transparent !important;
    }
    /* Kill the "open"/"close" tooltip on the dropdown arrow */
    [data-baseweb="select"] [role="presentation"] svg {
        pointer-events: none !important;
    }

    /* ──── Hide Streamlit header bar ── */
    header[data-testid="stHeader"] {
        background: transparent !important;
        backdrop-filter: none !important;
        height: 0 !important;
        min-height: 0 !important;
        padding: 0 !important;
        overflow: hidden !important;
    }

    /* ──── NUCLEAR: Kill ALL ghost text in expander summaries ── */
    /* Step 1: Zero out everything in summary */
    [data-testid="stExpander"] summary,
    [data-testid="stExpander"] summary * {
        font-size: 0 !important;
        color: transparent !important;
        cursor: pointer !important;
    }
    /* Step 2: Restore ONLY the label text */
    [data-testid="stExpander"] summary [data-testid="stMarkdownContainer"],
    [data-testid="stExpander"] summary [data-testid="stMarkdownContainer"] * {
        font-size: 0.95rem !important;
        color: #c9d1d9 !important;
    }
    /* Step 3: Native toggle icon is already invisible from font-size:0 above */
    /* Step 4: Inject a CSS-only chevron via ::before */
    [data-testid="stExpander"] summary::before {
        content: "▸" !important;
        font-size: 14px !important;
        color: #8b949e !important;
        margin-right: 6px !important;
        display: inline-block !important;
        transition: transform 0.2s ease !important;
        flex-shrink: 0 !important;
    }
    [data-testid="stExpander"][open] summary::before {
        content: "▾" !important;
    }

    /* ──── Background ── */
    .stApp {
        background: var(--bg-color) !important;
        max-width: 100vw !important;
        overflow-x: hidden !important;
    }
    
    /* ──── Kill horizontal overflow & scrollbar ── */
    .stMain, [data-testid="stAppViewContainer"], 
    [data-testid="stAppViewBlockContainer"],
    .stApp > div {
        overflow-x: hidden !important;
        max-width: 100vw !important;
    }
    .stMain {
        overflow-y: auto !important;
    }
    html, body {
        overflow-x: hidden !important;
        max-width: 100vw !important;
    }
    
    /* ──── Main content card ── */
    .stMainBlockContainer {
        background: var(--surface-color) !important;
        border-radius: 16px;
        padding: 28px 40px !important;
        margin: 8px 16px 16px 16px;
        border: 1px solid var(--border-color);
        box-shadow: 0 4px 24px rgba(0, 0, 0, 0.3);
    }
    

    
    /* ──── Sidebar ── */
    section[data-testid="stSidebar"] {
        background: var(--surface-color) !important;
        border-right: 1px solid var(--border-color) !important;
    }
    section[data-testid="stSidebar"] .stMarkdown { color: #c9d1d9 !important; }

    /* ──── Sidebar spacing ── */
    section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
        gap: 0.6rem !important;
    }
    section[data-testid="stSidebar"] .stMarkdown p { 
        margin-bottom: 0.3rem !important;
        overflow: visible !important;
        text-overflow: unset !important;
        white-space: normal !important;
    }
    /* Sidebar labels */
    section[data-testid="stSidebar"] label,
    section[data-testid="stSidebar"] .stSlider label,
    section[data-testid="stSidebar"] .stTextInput label,
    section[data-testid="stSidebar"] .stSelectbox label {
        color: #8b949e !important;
        font-size: 13px !important;
        font-weight: 500 !important;
    }
    /* Fix icon text rendering in expanders */
    [data-testid="stExpander"] summary span[data-testid="stMarkdownContainer"] {
        overflow: hidden !important;
    }

    /* ──── Headers ── */
    .ancap-logo {
        font-family: 'Space Grotesk', sans-serif !important;
        font-size: 2.6rem;
        font-weight: 700;
        letter-spacing: -0.04em;
        background: var(--accent-gradient);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        margin-bottom: 4px !important;
        padding-bottom: 0;
        line-height: 1.2;
    }
    .ancap-sub {
        font-size: 0.82rem;
        font-weight: 500;
        color: #8b949e;
        letter-spacing: 0.05em;
        text-transform: uppercase;
        margin-top: 0;
        margin-bottom: 8px !important;
    }
    .main-title {
        font-family: 'Space Grotesk', sans-serif !important;
        font-size: 2.4rem;
        font-weight: 700;
        color: #f0f6fc;
        letter-spacing: -0.03em;
        margin-bottom: 6px;
    }
    .main-subtitle {
        font-size: 1.1rem;
        color: #a0aab4;
        font-weight: 400;
        margin-top: 0;
        margin-bottom: 28px;
    }

    /* ──── Score Badges ── */
    .score-pass {
        background: linear-gradient(135deg, #238636, #2ea043);
        color: #ffffff; padding: 5px 14px;
        border-radius: 20px; font-weight: 600; font-size: 13px;
        display: inline-block; letter-spacing: 0.02em;
        box-shadow: 0 0 12px rgba(46, 160, 67, 0.3);
    }
    .score-fail {
        background: linear-gradient(135deg, #da3633, #f85149);
        color: #ffffff; padding: 5px 14px;
        border-radius: 20px; font-weight: 600; font-size: 13px;
        display: inline-block;
        box-shadow: 0 0 12px rgba(248, 81, 73, 0.3);
    }
    .score-warn {
        background: linear-gradient(135deg, #9e6a03, #d29922);
        color: #ffffff; padding: 5px 14px;
        border-radius: 20px; font-weight: 600; font-size: 13px;
        display: inline-block;
        box-shadow: 0 0 12px rgba(210, 153, 34, 0.3);
    }

    /* ──── Script Input Section ── */
    .script-input-section {
        margin-top: 24px;
        padding-top: 24px;
        border-top: 1px solid var(--border-color);
    }
    .script-input-label {
        font-family: 'Space Grotesk', sans-serif !important;
        font-weight: 600;
        color: var(--text-color);
        font-size: 1rem;
        margin-bottom: 4px;
    }
    .script-input-hint {
        color: var(--text-dim);
        font-size: 0.85rem;
        margin-bottom: 12px;
    }

    /* ──── Glassmorphism Image Cards ── */
    .image-card {
        background: rgba(22, 27, 34, 0.8);
        backdrop-filter: blur(12px);
        border: 1px solid var(--border-color);
        border-radius: 12px;
        padding: 16px;
        margin-bottom: 8px;
        transition: all 0.2s ease;
    }
    
    .image-card:hover {
        border-color: rgba(0, 212, 170, 0.5);
        box-shadow: 0 8px 32px rgba(0, 212, 170, 0.1);
    }
    
    .image-card-title {
        font-family: 'Space Grotesk', sans-serif !important;
        font-size: 0.95rem;
        font-weight: 600;
        color: var(--text-color);
        margin-bottom: 8px;
    }
    
    .image-card-meta {
        display: flex;
        align-items: center;
        gap: 12px;
        margin-bottom: 0;
    }

    /* ──── Prompt Display Card ── */
    /* ──── Prompt Display Card ── */
    .prompt-card {
        background: rgba(13, 17, 23, 0.9);
        border: 1px solid var(--border-color);
        border-left: 3px solid var(--accent-color);
        border-radius: 8px;
        padding: 12px 14px;
        margin: 8px 0 12px 0;
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 0.78rem;
        color: var(--text-dim);
        line-height: 1.5;
        max-height: 120px;
        overflow-y: auto;
        word-wrap: break-word;
    }
    .prompt-card-label {
        font-family: 'Inter', sans-serif !important;
        font-size: 0.75rem;
        font-weight: 600;
        color: var(--accent-color);
        text-transform: uppercase;
        letter-spacing: 0.06em;
        margin-bottom: 6px;
    }

    /* ──── Empty State ── */
    .empty-state {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        min-height: 400px;
        background: rgba(22, 27, 34, 0.4);
        border: 2px dashed var(--border-color);
        border-radius: 16px;
        color: var(--text-dim);
        text-align: center;
        padding: 40px;
    }
    
    .empty-state-icon {
        font-size: 4rem;
        margin-bottom: 16px;
        opacity: 0.5;
        color: var(--text-dim);
    }
    
    .empty-state-text {
        font-size: 1.1rem;
        font-weight: 500;
        color: var(--text-color);
    }
    
    .empty-state-sub {
        font-size: 0.9rem;
        color: var(--text-dim);
        margin-top: 8px;
    }

    /* ──── Widgets ── */
    .stTextArea textarea {
        background: var(--surface-color) !important;
        border: 1px solid var(--border-color) !important;
        border-radius: 10px !important;
        color: var(--text-color) !important;
        font-size: 15px !important;
        padding: 18px !important;
        transition: border-color 0.2s ease;
        min-height: 80px !important;
    }
    .stTextArea textarea:focus {
        border-color: var(--accent-color) !important;
        box-shadow: 0 0 0 3px rgba(0, 212, 170, 0.15) !important;
    }
    .stTextArea textarea::placeholder { color: var(--text-dim) !important; }

    /* ──── Bright Labels ── */
    .stTextArea label, .stTextInput label, .stSelectbox label,
    .stSlider label, .stCheckbox label {
        color: var(--text-color) !important;
        font-size: 15px !important;
        font-weight: 500 !important;
        font-family: 'Inter', sans-serif !important;
    }
    
    .stTextInput input {
        background: var(--surface-color) !important;
        border: 1px solid var(--border-color) !important;
        border-radius: 6px !important;
        color: var(--text-color) !important;
    }
    .stTextInput input:focus {
        border-color: var(--accent-color) !important;
        box-shadow: 0 0 0 3px rgba(0, 212, 170, 0.15) !important;
    }
    .stSelectbox > div > div {
        background: var(--surface-color) !important;
        border: 1px solid var(--border-color) !important;
        border-radius: 6px !important;
        color: var(--text-color) !important;
    }
    /* Selectbox selected value text */
    .stSelectbox [data-baseweb="select"] span,
    .stSelectbox [data-baseweb="select"] div {
        color: var(--text-color) !important;
    }
    /* Dropdown option list */
    [data-baseweb="popover"] ul {
        background: var(--surface-color) !important;
        border: 1px solid var(--border-color) !important;
    }
    [data-baseweb="popover"] li {
        color: var(--text-color) !important;
        background: transparent !important;
    }
    [data-baseweb="popover"] li:hover {
        background: var(--bg-color) !important;
        color: var(--accent-color) !important;
    }
    /* ──── Hide Streamlit ghost text / keyboard hints ── */
    [data-testid="InputInstructions"],
    .stDeployButton,
    div[data-testid="stStatusWidget"] {
        display: none !important;
        visibility: hidden !important;
    }

    /* ──── Buttons ── */
    .stButton > button[kind="primary"] {
        background: var(--accent-gradient) !important;
        color: #000000 !important;
        font-weight: 700 !important;
        border: none !important;
        border-radius: 8px !important;
        padding: 10px 24px !important;
        transition: all 0.2s ease !important;
        letter-spacing: 0.01em;
        font-family: 'Space Grotesk', sans-serif !important;
    }
    .stButton > button[kind="primary"]:hover {
        box-shadow: 0 4px 16px rgba(0, 212, 170, 0.4) !important;
        transform: translateY(-1px) !important;
        filter: brightness(1.1);
    }
    .stButton > button[kind="secondary"] {
        background: rgba(255, 255, 255, 0.05) !important;
        color: var(--text-color) !important;
        border: 1px solid var(--border-color) !important;
        border-radius: 8px !important;
        transition: all 0.2s ease !important;
        font-family: 'Inter', sans-serif !important;
    }
    .stButton > button[kind="secondary"]:hover {
        background: rgba(255, 255, 255, 0.1) !important;
        border-color: var(--accent-color) !important;
        color: var(--accent-color) !important;
    }

    /* ──── Metrics ── */
    [data-testid="stMetric"] {
        background: rgba(22, 27, 34, 0.6);
        backdrop-filter: blur(12px);
        border: 1px solid var(--border-color);
        border-radius: 10px;
        padding: 16px 20px;
    }
    [data-testid="stMetricLabel"] { color: var(--text-dim) !important; font-size: 13px !important; font-family: 'Inter', sans-serif !important; }
    [data-testid="stMetricValue"] { color: var(--text-color) !important; font-weight: 700 !important; font-family: 'Space Grotesk', sans-serif !important; }

    /* ──── Expander ── */
    .streamlit-expanderHeader,
    [data-testid="stExpander"] summary {
        background: var(--surface-color) !important;
        border-radius: 8px !important;
        color: var(--text-color) !important;
        font-weight: 500 !important;
        overflow: visible !important;
        white-space: normal !important;
        border: 1px solid var(--border-color) !important;
        font-family: 'Inter', sans-serif !important;
    }
    [data-testid="stExpander"] {
        border: none !important;
        border-radius: 8px !important;
        overflow: visible !important;
    }
    [data-testid="stExpander"] summary:hover {
        border-color: var(--accent-color) !important;
        color: var(--accent-color) !important;
    }

    /* ──── Dividers ── */
    hr { border-color: var(--border-color) !important; opacity: 0.6; }

    /* ──── Scrollbar ── */
    ::-webkit-scrollbar { width: 8px; }
    ::-webkit-scrollbar-track { background: var(--bg-color); }
    ::-webkit-scrollbar-thumb { background: var(--border-color); border-radius: 4px; }
    ::-webkit-scrollbar-thumb:hover { background: var(--text-dim); }

    /* ──── Progress Bar ── */
    .stProgress > div > div {
        background: var(--accent-gradient) !important;
        border-radius: 4px;
    }
    
    /* ──── Download Button ── */
    .stDownloadButton > button {
        background: var(--surface-color) !important;
        color: var(--accent-color) !important;
        border: 1px solid var(--border-color) !important;
        border-radius: 8px !important;
        font-weight: 500 !important;
        font-family: 'Space Grotesk', sans-serif !important;
    }
    .stDownloadButton > button:hover {
        background: var(--bg-color) !important;
        border-color: var(--accent-color) !important;
    }
    
    /* ──── Stats Panel ── */
    .stats-panel {
        background: rgba(22, 27, 34, 0.6);
        border: 1px solid var(--border-color);
        border-radius: 12px;
        padding: 24px;
        height: fit-content;
    }
    
    .stats-panel h3 {
        font-family: 'Space Grotesk', sans-serif !important;
        font-size: 1.1rem;
        font-weight: 600;
        color: var(--text-color);
        margin-bottom: 16px;
        display: flex;
        align-items: center;
        gap: 8px;
    }
    
    .stat-row {
        display: flex;
        justify-content: space-between;
        padding: 12px 0;
        border-bottom: 1px solid var(--border-color);
    }
    
    .stat-row:last-child {
        border-bottom: none;
    }
    
    .stat-label {
        color: var(--text-dim);
        font-size: 0.9rem;
        font-family: 'Inter', sans-serif !important;
    }
    
    .stat-value {
        color: var(--text-color);
        font-weight: 600;
        font-size: 0.95rem;
        font-family: 'Space Grotesk', sans-serif !important;
    }

    /* ──── Progress bar: gold/amber on dark ── */
    /* ──── Progress bar: teal on dark ── */
    .stProgress > div > div > div > div {
        background: var(--accent-gradient) !important;
        border-radius: 4px !important;
    }
    .stProgress > div > div {
        background-color: var(--surface-color) !important;
        border-radius: 4px !important;
    }
    .stProgress p {
        color: var(--text-color) !important;
        font-size: 0.85rem !important;
        font-weight: 600 !important;
        text-shadow: 0 1px 2px rgba(0,0,0,0.5) !important;
        font-family: 'Inter', sans-serif !important;
    }

    /* ──── Disabled buttons: no stop cursor ── */
    button[disabled] {
        cursor: default !important;
        opacity: 0.45 !important;
    }

    /* ──── Pipeline status banner ── */
    .pipeline-status {
        background: linear-gradient(135deg, rgba(26, 30, 40, 0.8) 0%, rgba(22, 27, 34, 0.8) 100%);
        border: 1px solid var(--border-color);
        border-radius: 10px;
        padding: 20px;
        text-align: center;
        margin: 8px 0;
    }
    .pipeline-status .status-emoji {
        font-size: 2rem;
        margin-bottom: 8px;
        animation: pulse 1.5s ease-in-out infinite;
    }
    .pipeline-status .status-text {
        color: #d4af37;
        font-size: 1rem;
        font-weight: 500;
    }
    .pipeline-status .status-sub {
        color: #8b949e;
        font-size: 0.8rem;
        margin-top: 4px;
    }
    @keyframes pulse {
        0%, 100% { transform: scale(1); }
        50% { transform: scale(1.15); }
    }

    /* ──── User Feedback ── */
    .feedback-row {
        display: flex;
        gap: 8px;
        align-items: center;
        margin: 8px 0 4px;
    }
    .feedback-badge {
        display: inline-flex;
        align-items: center;
        gap: 4px;
        padding: 4px 12px;
        border-radius: 6px;
        font-size: 0.8rem;
        font-weight: 600;
        font-family: 'Space Grotesk', sans-serif;
    }
    .feedback-badge.approved {
        background: rgba(63, 185, 80, 0.15);
        color: #3fb950;
        border: 1px solid rgba(63, 185, 80, 0.3);
    }
    .feedback-badge.rejected {
        background: rgba(248, 81, 73, 0.15);
        color: #f85149;
        border: 1px solid rgba(248, 81, 73, 0.3);
    }
    .feedback-badge.pending {
        background: rgba(139, 148, 158, 0.1);
        color: #8b949e;
        border: 1px solid rgba(139, 148, 158, 0.2);
    }
</style>
""", unsafe_allow_html=True)

# Kill "open"/"close" tooltips on selectbox arrows (CSS can't remove title elements)
import streamlit.components.v1 as components
components.html("""
<script>
(function(){
    var root = window.parent.document;
    function stripTitles(){
        root.querySelectorAll('[data-baseweb="select"] svg title').forEach(function(t){
            t.textContent = '';
        });
    }
    stripTitles();
    new MutationObserver(stripTitles).observe(root.body, {childList:true, subtree:true, characterData:true});
})();
</script>
""", height=0)


# ── Auto-load latest run ─────────────────────────────────────────────────────
def _load_latest_report():
    """Find the most recent qc_report.json in output/ and return (report_dict, run_folder) or (None, None)."""
    output_dir = Path("output")
    if not output_dir.exists():
        return None, None
    # Sorted descending by folder name (timestamp-based)
    run_dirs = sorted(
        [d for d in output_dir.iterdir() if d.is_dir() and d.name.startswith("run_")],
        key=lambda d: d.name,
        reverse=True,
    )
    for run_dir in run_dirs:
        report_file = run_dir / "qc_report.json"
        if report_file.exists():
            try:
                with open(report_file, "r", encoding="utf-8") as f:
                    report = json.load(f)
                return report, str(run_dir)
            except Exception:
                continue
    return None, None


def _save_user_feedback(run_folder: str, scene_number: int, visual_type: str, verdict: str, note: str):
    """Persist user feedback into qc_report.json for a specific scene/visual."""
    from datetime import datetime, timezone, timedelta
    report_path = Path(run_folder) / "qc_report.json"
    if not report_path.exists():
        return
    with open(report_path, "r", encoding="utf-8") as f:
        report = json.load(f)

    feedback_obj = {
        "verdict": verdict,
        "note": note,
        "timestamp": datetime.now(timezone(timedelta(hours=5))).isoformat()
    }

    # Find matching result and inject feedback
    for result in report.get("results", []):
        if result["scene_number"] != scene_number:
            continue
        vr_list = result.get("visual_results", [])
        if vr_list:
            for vr in vr_list:
                if vr.get("visual_type", "key_visual") == visual_type:
                    vr["user_feedback"] = feedback_obj
                    break
        else:
            result["user_feedback"] = feedback_obj
        break

    # Recompute summary
    reviewed = 0
    approved = 0
    rejected = 0
    for result in report.get("results", []):
        vr_list = result.get("visual_results", [])
        if vr_list:
            for vr in vr_list:
                uf = vr.get("user_feedback")
                if uf:
                    reviewed += 1
                    if uf["verdict"] == "approved":
                        approved += 1
                    else:
                        rejected += 1
        else:
            uf = result.get("user_feedback")
            if uf:
                reviewed += 1
                if uf["verdict"] == "approved":
                    approved += 1
                else:
                    rejected += 1
    report["user_review_summary"] = {
        "total_reviewed": reviewed,
        "approved": approved,
        "rejected": rejected
    }

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    # Update in-memory report
    st.session_state.pipeline_report = report


# ── State Init ───────────────────────────────────────────────────────────────
if "pipeline_report" not in st.session_state:
    # Try to auto-load the latest run so images survive page refresh
    _report, _run_folder = _load_latest_report()
    st.session_state.pipeline_report = _report
    st.session_state.run_folder = _run_folder
    if _report:
        logging.info(f"Auto-loaded latest report from {_run_folder}")
else:
    _run_folder = st.session_state.run_folder
if "scenes" not in st.session_state:
    st.session_state.scenes = None
if "redo_scene" not in st.session_state:
    st.session_state.redo_scene = None
if "run_folder" not in st.session_state:
    st.session_state.run_folder = _run_folder
if "script_text" not in st.session_state:
    st.session_state.script_text = ""
if "pipeline_running" not in st.session_state:
    st.session_state.pipeline_running = False


# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown('<p class="ancap-logo">Psimplicity</p>', unsafe_allow_html=True)
    st.markdown('<p class="ancap-sub">INTELLIGENCE ARCHITECTS</p>', unsafe_allow_html=True)
    st.divider()

    # ── Session Selector ──────────────────────────────────────────────────────
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    # Scan for existing sessions with metadata
    def _load_sessions():
        sessions = []
        for d in sorted(output_dir.iterdir(), reverse=True):
            if not d.is_dir() or not d.name.startswith("run_"):
                continue
            report_path = d / "qc_report.json"
            meta = {}
            if report_path.exists():
                try:
                    with open(report_path, encoding='utf-8') as f:
                        rpt = json.load(f)
                    meta = {
                        "style": rpt.get("style_preset", ""),
                        "scenes": rpt.get("total_scenes", 0),
                        "passed": rpt.get("passed_scenes", 0),
                        "avg_score": rpt.get("average_final_score", 0),
                        "images": rpt.get("total_images_generated", 0),
                    }
                except Exception:
                    pass
            # Parse timestamp from folder name
            clean = d.name.removeprefix("run_")
            parts = clean.rsplit("_", 1)
            ts_str = ""
            proj_name = ""
            if len(parts) == 2 and parts[-1].isdigit():
                date_part = parts[0]
                time_part = parts[1]
                if date_part.isdigit() and len(date_part) == 8:
                    ts_str = f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:8]} {time_part[:2]}:{time_part[2:4]}"
                else:
                    name_parts = date_part.rsplit("_", 1)
                    if len(name_parts) == 2 and name_parts[-1].isdigit():
                        proj_name = name_parts[0].replace("_", " ")
                        dp = name_parts[1]
                        ts_str = f"{dp[:4]}-{dp[4:6]}-{dp[6:8]} {time_part[:2]}:{time_part[2:4]}"
            sessions.append({
                "folder": d.name,
                "path": str(d),
                "project_name": proj_name,
                "timestamp": ts_str,
                "has_report": report_path.exists(),
                **meta,
            })
        return sessions

    sessions = _load_sessions()[:20]  # Cap to 20 most recent

    if "new_project_mode" not in st.session_state:
        st.session_state.new_project_mode = False

    def _session_label(s):
        parts = []
        if s.get("project_name"):
            parts.append(s["project_name"])
        if s.get("style"):
            parts.append(s["style"])
        if s.get("scenes"):
            parts.append(f"{s['scenes']} scenes")
        if s.get("avg_score"):
            parts.append(f"⭐ {s['avg_score']}")
        if s.get("timestamp"):
            parts.append(s["timestamp"])
        if not s.get("has_report"):
            parts.append("(incomplete)")
        return " · ".join(parts) if parts else s["folder"]

    st.markdown("**🎬 Project**")
    col_proj, col_new = st.columns([4, 1], gap="small")

    with col_new:
        def _new_project():
            st.session_state.new_project_mode = True
            st.session_state.pipeline_report = None
            st.session_state.run_folder = None
            st.session_state.scenes = None
            st.session_state.redo_scene = None
            st.session_state.script_text = ""
        st.button("➕", key="new_project_btn",
                  help="Start a new project", on_click=_new_project)

    project_name = ""

    if sessions:
        with col_proj:
            labels = [_session_label(s) for s in sessions]
            def _on_session_change():
                st.session_state.new_project_mode = False
            selected_idx = st.selectbox(
                "Session",
                range(len(labels)),
                format_func=lambda i: labels[i],
                key="session_selector",
                label_visibility="collapsed",
                on_change=_on_session_change
            )

            if not st.session_state.get("new_project_mode", False):
                sel = sessions[selected_idx]
                project_name = sel.get("project_name", "")
                # Resume: load session report + folder
                sel_path = Path(sel["path"])
                report_file = sel_path / "qc_report.json"
                if report_file.exists() and str(sel_path) != st.session_state.get("run_folder"):
                    try:
                        with open(report_file, encoding='utf-8') as f:
                            st.session_state.pipeline_report = json.load(f)
                        st.session_state.run_folder = str(sel_path)
                        # Restore cached scenes for redo
                        scenes_file = sel_path / "scenes.json"
                        if scenes_file.exists():
                            from modules.scene_parser import Scene, Visual
                            with open(scenes_file, encoding='utf-8') as sf:
                                raw_scenes = json.load(sf)
                            restored = []
                            for sd in raw_scenes:
                                visuals = [Visual(**v) for v in sd.pop("visuals", [])]
                                restored.append(Scene(**sd, visuals=visuals))
                            st.session_state.scenes = restored
                        else:
                            # Fallback: reconstruct from report (old sessions)
                            from modules.scene_parser import Scene, Visual
                            rr = st.session_state.pipeline_report.get("results", [])
                            if rr:
                                fb = []
                                for r in rr:
                                    desc = r.get("final_prompt", r.get("scene_title", ""))
                                    vrs = r.get("visual_results", [])
                                    vis = [Visual(
                                        visual_type=vr.get("visual_type", "key_visual"),
                                        visual_description=vr.get("final_prompt", desc),
                                    ) for vr in vrs] if vrs else []
                                    fb.append(Scene(
                                        scene_number=r.get("scene_number", len(fb) + 1),
                                        scene_title=r.get("scene_title", f"Scene {len(fb) + 1}"),
                                        visual_description=desc,
                                        visuals=vis,
                                    ))
                                st.session_state.scenes = fb
                    except Exception:
                        pass

                # Delete button for selected session
                def _delete_session():
                    idx = st.session_state.get("session_selector", 0)
                    target = sessions[idx]
                    target_path = Path(target["path"])
                    if target_path.exists():
                        shutil.rmtree(target_path, ignore_errors=True)
                    # Reset to fresh state
                    st.session_state.session_selector = 0
                    st.session_state.new_project_mode = True
                    st.session_state.pipeline_report = None
                    st.session_state.run_folder = None
                    st.session_state.scenes = None
                st.button(
                    "🗑 Delete Session",
                    key="delete_session_btn",
                    help="Permanently delete this session and its files",
                    on_click=_delete_session,
                    width="stretch"
                )
    else:
        # No sessions at all — force new project mode
        st.session_state.new_project_mode = True

    if st.session_state.new_project_mode:
        project_name = st.text_input(
            "New project name",
            value="",
            placeholder="e.g. Dan's Philosophy Series",
            key="new_project_input",
            label_visibility="collapsed"
        )
        if project_name:
            st.caption(f"📁 `output/run_{re.sub(r'[^a-zA-Z0-9_-]', '_', project_name)}_...`")

    # Config
    config_path = st.text_input("Config file", value="config.json")
    
    # Style preset selection
    preset_dir = Path("style_presets")
    presets = list(preset_dir.glob("*.json")) if preset_dir.exists() else []
    preset_names = [p.stem.replace("_", " ").title() for p in presets]
    
    if presets:
        selected_preset_idx = st.selectbox(
            "Style Preset",
            range(len(presets)),
            format_func=lambda i: preset_names[i]
        )
        selected_preset = str(presets[selected_preset_idx])
        
        # Show preset details
        with open(selected_preset, encoding='utf-8') as f:
            preset_data = json.load(f)
        if st.checkbox("Show preset details", value=False, key="preset_toggle"):
            st.markdown(f"""
<div style="background:#161b22; border:1px solid #21262d; border-radius:8px; padding:12px 16px; font-size:13px; color:#c9d1d9; margin-top:4px;">
<b style="color:#d4af37;">Art Style:</b> {preset_data.get('art_style', 'N/A')}<br>
<b style="color:#d4af37;">Palette:</b> {preset_data.get('color_palette', 'N/A')}<br>
<b style="color:#d4af37;">Mood:</b> {', '.join(preset_data.get('mood_keywords', []))}
</div>""", unsafe_allow_html=True)
    else:
        st.warning("No style presets found in `style_presets/`")
        selected_preset = None

    # ── Brand DNA (Brand Bible from Reference Images) ────────────────────────
    st.divider()
    if "brand_bible_data" not in st.session_state:
        st.session_state.brand_bible_data = None
    if "brand_bible_analyzing" not in st.session_state:
        st.session_state.brand_bible_analyzing = False

    with st.expander("🧬 Brand DNA", expanded=False):
        st.caption("Upload brand assets + describe your brand — we'll extract the visual DNA.")
        brand_images = st.file_uploader(
            "Brand reference images",
            type=["png", "jpg", "jpeg", "webp"],
            accept_multiple_files=True,
            key="brand_image_upload",
            label_visibility="collapsed",
        )
        brand_context = st.text_area(
            "Brand Brief",
            placeholder=(
                "Example: This is our shampoo bottle — Pure Plant is a premium "
                "herbal shampoo brand from Pakistan. We target GenZ consumers who "
                "value all-natural, chemical-free hair care.\n\n"
                "KEY HERBS: Bhringraj (Eclipta Alba), Shikakai, Amla (Indian "
                "Gooseberry), Neem, Aloe Vera, Hibiscus, Brahmi, Fenugreek, "
                "Henna, Curry Leaf, Tulsi (Holy Basil), Moringa.\n\n"
                "TAGLINE: \"Nature's Science for Your Hair\"\n\n"
                "VISUAL DIRECTION: Clean, botanical, premium aesthetic. Earthy "
                "greens + warm golds. Editorial photography feel. The bottle "
                "is our hero — sleek amber with kraft label."
            ),
            height=160,
            key="brand_context_input",
        )

        if brand_images:
            # Show thumbnails
            thumb_cols = st.columns(min(len(brand_images), 4))
            for i, img in enumerate(brand_images):
                with thumb_cols[i % len(thumb_cols)]:
                    st.image(img, width=80, caption=img.name[:15])

        # Show Extract DNA button when images OR context is provided
        if brand_images or brand_context:
            if st.button("🧬 Extract DNA", key="analyze_brand_btn", use_container_width=True, type="primary"):
                st.session_state.brand_bible_analyzing = True
                try:
                    from modules.brand_bible import analyze_brand_images
                    with st.spinner("🧬 Extracting brand visual DNA..."):
                        bb = analyze_brand_images(
                            image_sources=brand_images or [],
                            custom_instructions=brand_context,
                        )
                    st.session_state.brand_bible_data = bb
                    st.session_state.brand_bible_analyzing = False
                    st.rerun()
                except Exception as e:
                    st.error(f"Analysis failed: {e}")
                    st.session_state.brand_bible_analyzing = False

        # Show extracted brand bible
        if st.session_state.brand_bible_data:
            bb = st.session_state.brand_bible_data
            st.markdown(f"""
<div style="background:#161b22; border:1px solid #21262d; border-radius:8px; padding:12px 16px; font-size:13px; color:#c9d1d9; margin-top:8px;">
<b style="color:#00d4aa;">✓ {bb.get('brand_name', 'Brand')} DNA Loaded</b><br>
<b style="color:#d4af37;">Identity:</b> {bb.get('visual_identity', 'N/A')[:120]}...<br>
<b style="color:#d4af37;">Mood:</b> {', '.join(bb.get('mood_signature', []))}<br>
<b style="color:#d4af37;">Personality:</b> {bb.get('brand_personality', 'N/A')[:100]}
</div>""", unsafe_allow_html=True)
            if st.button("🗑 Clear Brand DNA", key="clear_brand_btn"):
                st.session_state.brand_bible_data = None
                st.rerun()

    st.divider()
    
    # Pipeline settings
    st.markdown("### ⚙️ Settings")
    pass_threshold = st.slider("Pass Threshold", 1.0, 10.0, 7.0, 0.5)
    max_retries = st.slider("Max Retries per Scene", 1, 5, 3)
    target_scenes = st.number_input("Target Scenes", 0, 200, 0, 1,
                                     help="How many visual scenes to split your script into. "
                                          "Each scene may produce 1-3 visuals (establishing, key, detail shots). "
                                          "0 = auto-detect (the AI decides the best split). "
                                          "Rule of thumb: ~8 scenes per minute of script.")

    # Stats
    if st.session_state.pipeline_report:
        report = st.session_state.pipeline_report
        st.divider()
        st.markdown("### 📊 Last Run")
        col1, col2 = st.columns(2)
        col1.metric("Passed", f"{report['passed_scenes']}/{report['total_scenes']}")
        col2.metric("Avg Score", f"{report['average_final_score']}/10")
        st.caption(f"⏱ {report['duration_seconds']}s | 🖼 {report['total_images_generated']} generated")

    # ── Engine Selector ───────────────────────────────────────────────────────
    st.divider()
    with st.expander("🎛 Engine Selector", expanded=True):
        # Load model registry from config
        try:
            with open(config_path, encoding='utf-8') as _cf:
                _full_cfg = json.load(_cf)
            available = _full_cfg.get("available_models", {})
        except Exception:
            available = {}

        # --- Parser Model ---
        parser_list = available.get("parsers", [
            {"id": "google/gemini-3-flash-preview", "label": "Gemini 3 Flash ⚡", "tier": "fast"},
        ])
        # Build display labels with tier badges
        _tier_badges = {"fast": "⚡", "balanced": "⚖️", "premium": "💎"}
        parser_labels = []
        for p in parser_list:
            tier = p.get("tier", "")
            badge = _tier_badges.get(tier, "")
            # Use existing label if it already has emoji, otherwise add badge
            lbl = p["label"]
            if badge and badge not in lbl:
                lbl = f"{lbl} {badge}"
            parser_labels.append(lbl)
        parser_idx = st.selectbox(
            "🧠 Script Parser",
            range(len(parser_list)),
            format_func=lambda i: parser_labels[i],
            key="engine_parser",
            help="LLM that analyzes your script. ⚡Fast · ⚖️Balanced · 💎Premium"
        )
        selected_parser_model = parser_list[parser_idx]["id"]

        # --- Critic Model ---
        critic_same = st.checkbox("Critic same as parser", value=True, key="critic_same_toggle")
        if critic_same:
            selected_critic_model = selected_parser_model
        else:
            critic_list = available.get("parsers", parser_list)  # reuse parser list
            critic_labels = [p["label"] for p in critic_list]
            critic_idx = st.selectbox(
                "🎨 Art Critic",
                range(len(critic_list)),
                format_func=lambda i: critic_labels[i],
                key="engine_critic",
                help="LLM model that scores and critiques generated images"
            )
            selected_critic_model = critic_list[critic_idx]["id"]

        st.markdown("---")

        # --- Image Generator ---
        img_list = available.get("image_generators", [
            {"id": "gemini-image", "label": "Nano Banana Pro 🍌", "config_key": "gemini_image"},
            {"id": "imagen-3", "label": "Imagen 3.0 🎨", "config_key": "imagen"},
        ])
        img_labels = [g["label"] for g in img_list]
        img_idx = st.selectbox(
            "🖼️ Image Engine",
            range(len(img_list)),
            format_func=lambda i: img_labels[i],
            key="engine_image",
            help="AI model that generates the final images"
        )
        selected_image_config_key = img_list[img_idx]["config_key"]

        # Show active engine summary
        st.caption(f"Parser: `{selected_parser_model}` · Image: `{img_list[img_idx]['label']}`")

    # ── Configuration Panel ────────────────────────────────────────────────────
    st.divider()
    with st.expander("🔑 Configuration"):
        st.caption("Keys are saved to `.env` (gitignored). Never committed.")

        # Load current config for defaults
        try:
            with open(config_path, encoding='utf-8') as f:
                _cfg = json.loads(f.read())
        except Exception:
            _cfg = {}

        # --- Gemini API Key (primary for Google engines) ---
        st.markdown("**🔮 Gemini API Key** *(powers Nano Banana Pro & Imagen 3)*")
        current_gemini_key = os.environ.get("GEMINI_API_KEY", "")
        new_gemini_key = st.text_input(
            "Gemini API Key",
            value=current_gemini_key,
            type="password",
            key="cfg_gemini_api_key",
            help="Get yours free at aistudio.google.com — no GCP project needed"
        )

        st.markdown("---")

        # --- LLM Provider (OpenRouter for parsing & critique) ---
        st.markdown("**🧠 LLM Provider** *(script parsing & critique)*")
        current_or_key = os.environ.get("OPENROUTER_API_KEY", "")
        new_or_key = st.text_input(
            "OpenRouter API Key",
            value=current_or_key,
            type="password",
            key="cfg_openrouter_key",
            help="Get yours at openrouter.ai/keys"
        )

        st.markdown("---")

        # --- DALL-E key (only when DALL-E is selected) ---
        new_dalle_key = ""
        if selected_image_config_key == "dalle":
            st.markdown("**🎨 DALL-E 3** *(OpenAI image engine)*")
            current_dalle_key = os.environ.get("OPENAI_API_KEY",
                                                _cfg.get("dalle", {}).get("api_key", ""))
            new_dalle_key = st.text_input(
                "OpenAI API Key", value=current_dalle_key,
                type="password", key="cfg_dalle_key",
                help="Get yours at platform.openai.com/api-keys"
            )
            st.markdown("---")

        # --- Advanced: Service Account (hidden by default) ---
        new_project_id = ""
        new_region = ""
        new_sa_path = ""
        with st.expander("⚙️ Advanced (Service Account)", expanded=False):
            st.caption("Only needed if you prefer SA JSON over an API key.")
            _vertex_key = "gemini_image" if "gemini_image" in _cfg else "imagen"
            current_project_id = _cfg.get(_vertex_key, {}).get("project_id", "")
            current_region = _cfg.get(_vertex_key, {}).get("region", "us-central1")
            current_sa_path = _cfg.get(_vertex_key, {}).get("service_account_path", "n8n-vertex.json")

            new_project_id = st.text_input(
                "Project ID", value=current_project_id,
                key="cfg_project_id", help="Google Cloud project ID"
            )
            new_region = st.text_input(
                "Region", value=current_region,
                key="cfg_region", help="e.g. us-central1"
            )
            new_sa_path = st.text_input(
                "Service Account JSON", value=current_sa_path,
                key="cfg_sa_path", help="Path to your GCP service account file"
            )

        # ── Save Button ───────────────────────────────────────────────────
        if st.button("💾 Save Configuration", key="save_keys_btn"):
            changed = False

            # Helper: upsert a key in .env
            def _save_env_key(key_name: str, key_value: str):
                env_path = Path(".env")
                env_lines = []
                key_found = False
                if env_path.exists():
                    with open(env_path, "r", encoding='utf-8') as ef:
                        for line in ef:
                            if line.startswith(f"{key_name}="):
                                env_lines.append(f"{key_name}={key_value}\n")
                                key_found = True
                            else:
                                env_lines.append(line)
                if not key_found:
                    env_lines.append(f"{key_name}={key_value}\n")
                with open(env_path, "w", encoding='utf-8') as ef:
                    ef.writelines(env_lines)
                os.environ[key_name] = key_value

            # Save Gemini API key to .env
            if new_gemini_key and new_gemini_key != current_gemini_key:
                _save_env_key("GEMINI_API_KEY", new_gemini_key)
                changed = True

            # Save OpenRouter key to .env
            if new_or_key and new_or_key != current_or_key:
                _save_env_key("OPENROUTER_API_KEY", new_or_key)
                changed = True

            # Update config.json based on active auth mode
            try:
                with open(config_path, "r", encoding='utf-8') as cf:
                    cfg_data = json.load(cf)

                # Determine if API key mode is active
                gemini_key = new_gemini_key or current_gemini_key

                if selected_image_config_key == "dalle":
                    # DALL-E mode
                    cfg_data["dalle"] = {"api_key": "${OPENAI_API_KEY}"}
                    cfg_data.pop("gemini_api_key", None)
                    if new_dalle_key:
                        _save_env_key("OPENAI_API_KEY", new_dalle_key)
                elif gemini_key:
                    # API key mode for Google engines
                    engine = "imagen-3" if selected_image_config_key == "imagen" else "gemini-image"
                    cfg_data["gemini_api_key"] = {
                        "api_key": "${GEMINI_API_KEY}",
                        "engine": engine
                    }
                    # Remove SA-based keys (API key takes priority in factory)
                    cfg_data.pop("gemini_image", None)
                    cfg_data.pop("imagen", None)
                    cfg_data.pop("dalle", None)
                elif new_sa_path and new_project_id:
                    # Service Account mode (advanced)
                    if selected_image_config_key in ("gemini_image", "imagen"):
                        cfg_data[selected_image_config_key] = {
                            "service_account_path": new_sa_path,
                            "project_id": new_project_id,
                            "region": new_region or "us-central1"
                        }
                        cfg_data.pop("gemini_api_key", None)
                        cfg_data.pop("dalle", None)
                        # Clean up the other provider
                        other = "imagen" if selected_image_config_key == "gemini_image" else "gemini_image"
                        cfg_data.pop(other, None)

                with open(config_path, "w", encoding='utf-8') as cf:
                    json.dump(cfg_data, cf, indent=4)
                changed = True
            except Exception as e:
                st.error(f"Failed to update config: {e}")

            if changed:
                st.success("✅ Configuration saved!")
                st.rerun()
            else:
                st.info("No changes detected.")

    # ── CEO Signature ─────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("""
<div style="text-align:center; padding:8px 0 4px; opacity:0.5;">
    <span style="font-size:11px; color:#8b949e; letter-spacing:0.5px;">Built by</span><br>
    <span style="font-size:13px; color:#d4af37; font-weight:600; letter-spacing:0.3px;">Junaid Sheikh</span><br>
    <span style="font-size:11px; color:#8b949e;">CEO · <a href="https://psio.io" target="_blank" style="color:#d4af37; text-decoration:none;">Psio.io</a></span>
</div>
""", unsafe_allow_html=True)


# ── Main Area Header ─────────────────────────────────────────────────────────
st.markdown('<p class="main-title">Psimplicity Pipeline</p>', unsafe_allow_html=True)
st.markdown('<p class="main-subtitle">Consciousness Interface · Script to Image Generation</p>', unsafe_allow_html=True)

# ── Main Content Area: Left Stats + Right Image Grid ─────────────────────────
left_col, right_col = st.columns([1, 2])

with left_col:
    # Stats / Summary Panel
    if st.session_state.pipeline_report:
        report = st.session_state.pipeline_report
        passed = report["passed_scenes"]
        total = report["total_scenes"]
        avg = report["average_final_score"]
        
        total_visuals = report.get('total_visuals', total)
        st.markdown("""
        <div class="stats-panel">
            <h3>📊 Generation Summary</h3>
            <div class="stat-row">
                <span class="stat-label">Total Scenes</span>
                <span class="stat-value">{}</span>
            </div>
            <div class="stat-row">
                <span class="stat-label">Total Visuals</span>
                <span class="stat-value" style="color: #58a6ff;">{}</span>
            </div>
            <div class="stat-row">
                <span class="stat-label">Passed ✅</span>
                <span class="stat-value" style="color: #3fb950;">{}</span>
            </div>
            <div class="stat-row">
                <span class="stat-label">Needs Review ⚠️</span>
                <span class="stat-value" style="color: #d29922;">{}</span>
            </div>
            <div class="stat-row">
                <span class="stat-label">Average Score</span>
                <span class="stat-value" style="color: #d4af37;">{}/10</span>
            </div>
            <div class="stat-row">
                <span class="stat-label">Total Generated</span>
                <span class="stat-value">{} images</span>
            </div>
            <div class="stat-row">
                <span class="stat-label">Duration</span>
                <span class="stat-value">{}s</span>
            </div>
            <div class="stat-row">
                <span class="stat-label">👤 User Reviewed</span>
                <span class="stat-value" style="color: #58a6ff;">{}  <span style="color: #3fb950;">✓{}</span> <span style="color: #f85149;">✗{}</span></span>
            </div>
        </div>
        """.format(
            total, total_visuals, passed, total - passed, avg,
            report.get('total_images_generated', total),
            report.get('duration_seconds', 0),
            report.get('user_review_summary', {}).get('total_reviewed', 0),
            report.get('user_review_summary', {}).get('approved', 0),
            report.get('user_review_summary', {}).get('rejected', 0),
        ), unsafe_allow_html=True)
        
        # QC Report Download
        if st.session_state.run_folder:
            run_path = Path(st.session_state.run_folder)
            report_path = run_path / "qc_report.json"
            if report_path.exists():
                with open(report_path, encoding='utf-8') as f:
                    report_json = f.read()
                st.download_button(
                    "📥 Download QC Report",
                    data=report_json,
                    file_name="qc_report.json",
                    mime="application/json",
                    width="stretch"
                )
            
            # Open output folder in Explorer
            if st.button("📂 Open Output Folder", key="open_folder_btn"):
                import subprocess
                abs_folder = Path(run_path).resolve() if not Path(run_path).is_absolute() else Path(run_path)
                if abs_folder.exists():
                    subprocess.Popen(f'explorer "{abs_folder}"')
                    st.toast(f"📂 Opened: {abs_folder.name}", icon="📂")
                else:
                    st.toast(f"⚠️ Folder not found: {abs_folder}", icon="⚠️")
            
            # ── Smart Collection: User verdict overrides AI score ──────────
            # Approved = auto-passed (unless user rejected) + user-approved fails
            approved_paths = []
            all_image_paths = []
            for r in report.get("results", []):
                vr_list = r.get("visual_results", [])
                items = vr_list if vr_list else [r]
                for item in items:
                    img = item.get("final_image_path")
                    if not img:
                        continue
                    all_image_paths.append(img)
                    ai_passed = item.get("passed", False)
                    uf = item.get("user_feedback")
                    # User verdict is final authority
                    if uf:
                        if uf["verdict"] == "approved":
                            approved_paths.append(img)
                        # "rejected" → excluded even if AI passed
                    elif ai_passed:
                        approved_paths.append(img)
            
            # Show counts summary
            user_overrides = sum(
                1 for r in report.get("results", [])
                for item in (r.get("visual_results") or [r])
                if not item.get("passed") and (item.get("user_feedback") or {}).get("verdict") == "approved"
            )
            user_rejected = sum(
                1 for r in report.get("results", [])
                for item in (r.get("visual_results") or [r])
                if item.get("passed") and (item.get("user_feedback") or {}).get("verdict") == "rejected"
            )
            if user_overrides or user_rejected:
                override_parts = []
                if user_overrides:
                    override_parts.append(f"+{user_overrides} user-approved")
                if user_rejected:
                    override_parts.append(f"-{user_rejected} user-rejected")
                st.caption(f"👤 Override: {', '.join(override_parts)}")
            
            # Primary: Collect Approved (AI passed + user overrides - user rejections)
            if approved_paths:
                if st.button(f"✅ Collect Approved ({len(approved_paths)})", key="collect_approved_btn"):
                    approved_dir = run_path / "approved"
                    approved_dir.mkdir(exist_ok=True)
                    
                    collected = 0
                    for p in approved_paths:
                        src = Path(p)
                        if src.exists():
                            shutil.copy2(src, approved_dir / src.name)
                            collected += 1
                    
                    zip_buffer = io.BytesIO()
                    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                        for img_file in approved_dir.iterdir():
                            if img_file.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
                                zf.write(img_file, img_file.name)
                    zip_buffer.seek(0)
                    
                    st.success(f"✅ {collected} approved images → `approved/` folder")
                    st.download_button(
                        "📦 Download Approved (ZIP)",
                        data=zip_buffer,
                        file_name="approved_images.zip",
                        mime="application/zip",
                        width="stretch",
                        key="download_approved_zip"
                    )
            
            # Secondary: Collect ALL (everything regardless of status)
            remaining = len(all_image_paths) - len(approved_paths)
            if all_image_paths and remaining > 0:
                if st.button(f"📸 Collect All ({len(all_image_paths)})", key="collect_all_btn"):
                    collected_dir = run_path / "collected"
                    collected_dir.mkdir(exist_ok=True)
                    
                    collected = 0
                    for p in all_image_paths:
                        src = Path(p)
                        if src.exists():
                            shutil.copy2(src, collected_dir / src.name)
                            collected += 1
                    
                    zip_buffer_all = io.BytesIO()
                    with zipfile.ZipFile(zip_buffer_all, "w", zipfile.ZIP_DEFLATED) as zf:
                        for img_file in collected_dir.iterdir():
                            if img_file.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
                                zf.write(img_file, img_file.name)
                    zip_buffer_all.seek(0)
                    
                    st.success(f"📸 {collected} images → `collected/` folder")
                    st.download_button(
                        "📦 Download All (ZIP)",
                        data=zip_buffer_all,
                        file_name="all_images.zip",
                        mime="application/zip",
                        width="stretch",
                        key="download_all_zip"
                    )
    else:
        # Empty stats panel
        st.markdown("""
        <div class="stats-panel">
            <h3>📊 Generation Summary</h3>
            <div style="text-align: center; padding: 40px 20px; color: #6e7681;">
                <p style="font-size: 2rem; margin-bottom: 12px;">🎬</p>
                <p>No generation data yet</p>
                <p style="font-size: 0.85rem; margin-top: 8px;">Enter a script below to start</p>
            </div>
        </div>
        """, unsafe_allow_html=True)

with right_col:
    # Image Grid Display
    if st.session_state.pipeline_report:
        report = st.session_state.pipeline_report
        results = report.get("results", [])
        
        if results:
            st.markdown("### Generated Images")
            st.caption("Click **Redo** on any scene to regenerate all its visuals with the AI QC loop.")
            
            # Visual type badges for display
            _VTYPE_BADGE = {
                "establishing": "🏔 Establishing",
                "key_visual":   "🎯 Key Visual",
                "detail":       "🔍 Detail",
            }
            
            # Flatten all visuals for the grid
            # Each item: (scene result dict, visual result dict or None)
            flat_items = []
            for result in results:
                vr_list = result.get("visual_results", [])
                if vr_list:
                    for vr in vr_list:
                        flat_items.append((result, vr))
                else:
                    # Legacy single-image scene (backward compat)
                    flat_items.append((result, None))
            
            # 2-column grid
            for row_start in range(0, len(flat_items), 2):
                cols = st.columns(2)
                for col_idx, (result, vr) in enumerate(flat_items[row_start:row_start + 2]):
                    with cols[col_idx]:
                        scene_num = result["scene_number"]
                        title = result["scene_title"]
                        
                        # Use per-visual data if available
                        if vr:
                            score = vr["final_score"]
                            vpassed = vr["passed"]
                            attempts = vr["attempts"]
                            image_path = vr.get("final_image_path", "")
                            final_prompt = vr.get("final_prompt", "")
                            vtype = vr.get("visual_type", "key_visual")
                            vtype_label = _VTYPE_BADGE.get(vtype, vtype)
                        else:
                            score = result["final_score"]
                            vpassed = result["passed"]
                            attempts = result["attempts"]
                            image_path = result.get("final_image_path", "")
                            final_prompt = result.get("final_prompt", "")
                            vtype_label = ""
                        
                        # Score badge — user verdict overrides AI
                        _uf = (vr or result).get("user_feedback")
                        if _uf and _uf["verdict"] == "approved" and not vpassed:
                            badge = f'<span class="score-pass" style="background: rgba(210,153,34,0.15); color: #d4af37; border-color: rgba(210,153,34,0.3);">{score}/10 USER PASS</span>'
                        elif _uf and _uf["verdict"] == "rejected" and vpassed:
                            badge = f'<span class="score-fail">{score}/10 USER ✗</span>'
                        elif vpassed:
                            badge = f'<span class="score-pass">{score}/10 PASS</span>'
                        elif score >= 5:
                            badge = f'<span class="score-warn">{score}/10</span>'
                        else:
                            badge = f'<span class="score-fail">{score}/10 FAIL</span>'
                        
                        # Visual type badge inline
                        vtype_html = f'<span style="background: rgba(88,166,255,0.15); color: #58a6ff; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; margin-left: 6px;">{vtype_label}</span>' if vtype_label else ""
                        
                        # Glassmorphism card header
                        st.markdown(f"""
                        <div class="image-card">
                            <div class="image-card-title">Scene {scene_num}: {title}{vtype_html}</div>
                            <div class="image-card-meta">
                                {badge}
                                <span style="color: #6e7681; font-size: 0.85rem;">({attempts} attempt{'s' if attempts > 1 else ''})</span>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        # Display image
                        if image_path and Path(image_path).exists():
                            st.image(image_path, width="stretch")
                        else:
                            st.warning("Image not found")
                        
                        # Prompt display card
                        if final_prompt:
                            short_prompt = final_prompt[:300] + ("..." if len(final_prompt) > 300 else "")
                            st.markdown(f"""
                            <div class="prompt-card">
                                <div class="prompt-card-label">Generation Prompt</div>
                                {short_prompt}
                            </div>
                            """, unsafe_allow_html=True)
                        
                        # ── User Feedback ──────────────────────────────
                        _fb_key = f"{scene_num}_{vr['visual_type'] if vr else 'main'}"
                        existing_fb = (vr or result).get("user_feedback")
                        
                        if existing_fb:
                            _badge_cls = "approved" if existing_fb["verdict"] == "approved" else "rejected"
                            _badge_icon = "✅" if existing_fb["verdict"] == "approved" else "❌"
                            _badge_text = "Approved" if existing_fb["verdict"] == "approved" else "Rejected"
                            st.markdown(f'<div class="feedback-badge {_badge_cls}">{_badge_icon} {_badge_text}</div>', unsafe_allow_html=True)
                            if existing_fb.get("note"):
                                st.caption(f"💬 {existing_fb['note']}")
                            # Allow changing verdict
                            with st.expander("✏️ Change feedback", expanded=False):
                                _fb_cols = st.columns(2)
                                with _fb_cols[0]:
                                    if st.button("👍", key=f"re_approve_{_fb_key}", use_container_width=True):
                                        _save_user_feedback(st.session_state.run_folder, scene_num, vr['visual_type'] if vr else 'main', 'approved', existing_fb.get('note', ''))
                                        st.rerun()
                                with _fb_cols[1]:
                                    if st.button("👎", key=f"re_reject_{_fb_key}", use_container_width=True):
                                        _save_user_feedback(st.session_state.run_folder, scene_num, vr['visual_type'] if vr else 'main', 'rejected', existing_fb.get('note', ''))
                                        st.rerun()
                                _new_note = st.text_input("Update note", value=existing_fb.get("note", ""), key=f"note_edit_{_fb_key}", placeholder="Optional feedback note...")
                                if _new_note != existing_fb.get("note", ""):
                                    if st.button("💾 Save note", key=f"save_note_{_fb_key}"):
                                        _save_user_feedback(st.session_state.run_folder, scene_num, vr['visual_type'] if vr else 'main', existing_fb['verdict'], _new_note)
                                        st.rerun()
                        else:
                            st.markdown('<div class="feedback-badge pending">⏳ Awaiting Review</div>', unsafe_allow_html=True)
                            _fb_cols = st.columns(2)
                            with _fb_cols[0]:
                                if st.button("👍 Approve", key=f"approve_{_fb_key}", use_container_width=True):
                                    _save_user_feedback(st.session_state.run_folder, scene_num, vr['visual_type'] if vr else 'main', 'approved', '')
                                    st.rerun()
                            with _fb_cols[1]:
                                if st.button("👎 Reject", key=f"reject_{_fb_key}", use_container_width=True):
                                    _save_user_feedback(st.session_state.run_folder, scene_num, vr['visual_type'] if vr else 'main', 'rejected', '')
                                    st.rerun()
                            _fb_note = st.text_input("Feedback note", key=f"note_{_fb_key}", placeholder="Optional: what's wrong?")
                        
                        # Redo controls (shown on every visual card)
                        _vkey = f"{scene_num}_{vr['visual_type'] if vr else 'main'}"
                        with st.expander("🔄 Redo this scene"):
                            edited_prompt = st.text_area(
                                "Edit prompt (or leave as-is)",
                                value=final_prompt if final_prompt else "No prompt recorded",
                                key=f"prompt_{_vkey}",
                                height=100
                            )
                            guidance = st.text_input(
                                "Additional direction",
                                key=f"guidance_{_vkey}",
                                placeholder='e.g. "more dramatic lighting, closer framing"'
                            )
                            if st.button("⚡ Regenerate", key=f"redo_{_vkey}", type="secondary",
                                         width="stretch"):
                                st.session_state.redo_scene = {
                                    "scene_number": scene_num,
                                    "guidance": guidance,
                                    "custom_prompt": edited_prompt if edited_prompt != final_prompt else None
                                }
                                st.rerun()
                        
                        # Score breakdown
                        history = (vr or result).get("history", [])
                        if history:
                            last = history[-1]
                            scores = last.get("scores", {})
                            if scores:
                                unique_key = f"scores_{scene_num}_{vr['visual_type'] if vr else 'main'}"
                                with st.expander(f"📊 Score Breakdown ({unique_key})"):
                                    for dim, val in scores.items():
                                        label = dim.replace("_", " ").title()
                                        color = "green" if val >= 7 else ("orange" if val >= 5 else "red")
                                        st.markdown(f":{color}[**{label}**] {val}/10")
                                    feedback_text = last.get("feedback", "")
                                    if feedback_text:
                                        st.caption(f"*{feedback_text}*")
    else:
        # Empty State Placeholder
        st.markdown("""
        <div class="empty-state">
            <div class="empty-state-icon">🖼</div>
            <div class="empty-state-text">Generated images will appear here</div>
            <div class="empty-state-sub">Enter your script below and click Generate to create stunning visuals</div>
        </div>
        """, unsafe_allow_html=True)


# ── Script Input Section ────────────────────────────────────────────────────
st.markdown("""
<div class="script-input-section">
    <div class="script-input-label">📝 Script Input</div>
    <div class="script-input-hint">Paste a 3-8 minute video script below and hit Generate</div>
</div>
""", unsafe_allow_html=True)

script_text = st.text_area(
    "Script Input",
    height=200,
    placeholder="Paste a 3-8 minute video script here...\n\nThe system will break it into scenes and generate a styled image for each one.",
    label_visibility="collapsed",
    key="script_text"
)

# Buttons row
col_gen, col_stop, col_clear, col_spacer = st.columns([1.5, 0.8, 1, 4.2])
with col_gen:
    def _start_pipeline():
        st.session_state.pipeline_running = True
    generate_btn = st.button(
        "🚀 Generate Images",
        type="primary",
        width="stretch",
        disabled=st.session_state.pipeline_running,
        on_click=_start_pipeline
    )
with col_stop:
    def _stop_pipeline():
        st.session_state.pipeline_running = False
    st.button(
        "⏹ Stop",
        width="stretch",
        on_click=_stop_pipeline,
        disabled=not st.session_state.pipeline_running
    )
with col_clear:
    def _clear_all():
        st.session_state.script_text = ""
        st.session_state.pipeline_report = None
        st.session_state.scenes = None
        st.session_state.run_folder = None
        st.session_state.pipeline_running = False
    st.button("🗑 Clear", on_click=_clear_all)

# ── Stale pipeline guard ────────────────────────────────────────────────────
# Pipeline runs synchronously. If pipeline_running=True but Generate was NOT
# just clicked, the pipeline died mid-rerun (user changed a widget).
# Reset the flag so the Generate button becomes clickable again.
if st.session_state.pipeline_running and not generate_btn:
    st.session_state.pipeline_running = False
    st.toast("⚠️ Pipeline was interrupted — Generate button re-enabled.", icon="🔄")
    st.rerun()


# ── Easter Egg Loading Messages ─────────────────────────────────────────────
_EASTER_EGGS = [
    "🎨 Mixing the perfect palette…",
    "🎬 The Director is reviewing the script…",
    "📸 Framing the shot — hold still…",
    "🧠 AI is having a creative moment…",
    "✨ Sprinkling some pixel magic…",
    "🖌️ Bob Ross would be proud…",
    "🎭 Setting the stage for Scene {n}…",
    "🔮 Consulting the crystal GPU…",
    "🎪 Assembling the visual circus…",
    "🌄 Rendering photons at light speed…",
    "☕ Brewing creativity (may take a sip)…",
    "🎯 Aiming for a 10/10 on Scene {n}…",
    "🪄 Abracadabra… image incoming…",
    "🏗️ Building Scene {n} brick by pixel…",
    "🎶 Composing the visual symphony…",
    "🔬 Art Director is squinting at pixels…",
    "🚀 Launching Scene {n} into orbit…",
    "🧪 Experimenting with visual formulas…",
    "🌈 Calibrating the rainbow engine…",
    "💎 Polishing every pixel to perfection…",
    # ── Round 2: OJ & Friends ──
    "🪝 Loading OJ's Hook to bring in the picture…",
    "🎣 OJ is casting the visual line — wait for the catch…",
    "🧲 OJ's Hook locked on Scene {n} — reeling it in…",
    "🦾 The AI muscle is flexing on this one…",
    "🎞️ Rolling camera… and… ACTION!",
    "🍿 Grab some popcorn — Scene {n} is cooking…",
    "🧑‍🎨 Picasso called, he wants his pixels back…",
    "🗡️ Sharpening the edges of every frame…",
    "🪐 Scene {n} just entered the visual multiverse…",
    "🛸 Beaming down the composition from orbit…",
    "🎰 Spinning the style roulette for Scene {n}…",
    "🏄 Riding the gradient wave…",
    "⚡ Zapping neurons — almost there…",
    "🫧 Blowing pixel bubbles into shape…",
    "🧊 Freezing the perfect frame…",
]

def _pick_easter_egg(scene_num=0, total=0):
    """Return a random easter egg with scene number substituted."""
    msg = random.choice(_EASTER_EGGS)
    return msg.format(n=scene_num, total=total)


# ── Pipeline Execution ──────────────────────────────────────────────────────
if generate_btn and (not script_text or not script_text.strip()):
    st.warning("⚠️ Paste a script above before generating.")
if generate_btn and not selected_preset:
    st.warning("⚠️ Select a style preset in the sidebar.")

if generate_btn and script_text and selected_preset:

    # ── Instant feedback: show status banner immediately ──
    status_placeholder = st.empty()
    status_placeholder.markdown("""
    <div class="pipeline-status">
        <div class="status-emoji">🚀</div>
        <div class="status-text">Launching Pipeline…</div>
        <div class="status-sub">Loading config &amp; warming up the AI engines</div>
    </div>
    """, unsafe_allow_html=True)

    with open(config_path, encoding='utf-8') as f:
        raw = f.read()
    # Resolve ${ENV_VAR} placeholders
    raw = re.sub(r'\$\{(\w+)\}', lambda m: os.environ.get(m.group(1), m.group(0)), raw)
    config = json.loads(raw)
    
    # Override settings from sidebar
    config["pipeline"]["pass_threshold"] = pass_threshold
    config["pipeline"]["max_retries"] = max_retries

    # ── Runtime API key injection ─────────────────────────────────────
    # If GEMINI_API_KEY is available and user picked a Google engine,
    # inject gemini_api_key config so the factory uses the simple SDK.
    _gemini_key_runtime = os.environ.get("GEMINI_API_KEY", "")
    if _gemini_key_runtime and selected_image_config_key in ("gemini_image", "imagen"):
        engine_map = {"gemini_image": "gemini-image", "imagen": "imagen-3"}
        config["gemini_api_key"] = {
            "api_key": _gemini_key_runtime,
            "engine": engine_map[selected_image_config_key],
        }
        selected_image_config_key = "gemini_api_key"

    # Seedream via OpenRouter
    _openrouter_key = os.environ.get("OPENROUTER_API_KEY", "")
    if _openrouter_key and selected_image_config_key == "seedream":
        config["seedream"] = {
            "api_key": _openrouter_key,
            "base_url": "https://openrouter.ai/api/v1",
            "model": "bytedance-seed/seedream-4.5",
        }

    orchestrator = Orchestrator(
        config,
        parser_model_override=selected_parser_model,
        critic_model_override=selected_critic_model,
        image_provider_key=selected_image_config_key
    )
    
    # ── Progress area with easter eggs ──
    status_placeholder.empty()
    progress_placeholder = st.empty()
    egg_placeholder = st.empty()
    with progress_placeholder.container():
        st.markdown("### ⏳ Generating...")
        progress_bar = st.progress(0, text="Starting pipeline...")

    _last_egg_time = [0.0]  # mutable for closure

    class PipelineStopped(Exception):
        """Raised when user clicks the stop button."""
        pass

    def update_progress(scene_num, total, status, image_path):
        # Check if user clicked Stop
        if not st.session_state.get("pipeline_running", True):
            raise PipelineStopped("Pipeline stopped by user.")
        if total > 0:
            pct = scene_num / total
            progress_bar.progress(pct, text=status)
        else:
            # Parsing phase (total unknown yet) — show status without moving bar
            progress_bar.progress(0, text=status)
        # Rotate easter egg every 4 seconds
        now = time.time()
        if now - _last_egg_time[0] > 4.0:
            egg_placeholder.markdown(
                f'<div style="text-align:center; color:#8b949e; font-size:0.85rem; '
                f'padding:4px 0; font-style:italic;">'
                f'{_pick_easter_egg(scene_num, total)}</div>',
                unsafe_allow_html=True
            )
            _last_egg_time[0] = now

    try:
        with st.spinner("Running pipeline..."):
            report = orchestrator.run(
                script=script_text,
                style_preset_path=selected_preset,
                progress_callback=update_progress,
                target_scenes=target_scenes,
                project_name=project_name if project_name else None,
                brand_bible_data=st.session_state.get("brand_bible_data"),
            )

        st.session_state.pipeline_report = report.to_dict()
        # Build matching folder name (must mirror orchestrator logic)
        safe_name = re.sub(r'[^\w\-]', '_', project_name) if project_name else ""
        folder_prefix = f"run_{safe_name}_{report.timestamp}" if safe_name else f"run_{report.timestamp}"
        st.session_state.run_folder = str(Path(config["output"]["folder"]) / folder_prefix)
        
        # Load cached scenes from orchestrator's scenes.json for redo
        scenes_file = Path(st.session_state.run_folder) / "scenes.json"
        if scenes_file.exists():
            from modules.scene_parser import Scene, Visual
            with open(scenes_file, encoding='utf-8') as sf:
                raw_scenes = json.load(sf)
            restored = []
            for sd in raw_scenes:
                visuals = [Visual(**v) for v in sd.pop("visuals", [])]
                restored.append(Scene(**sd, visuals=visuals))
            st.session_state.scenes = restored
        
        progress_placeholder.empty()
        egg_placeholder.empty()
    except PipelineStopped:
        st.warning("⏹ Pipeline stopped by user.")
        progress_placeholder.empty()
        egg_placeholder.empty()
    except Exception as e:
        st.error(f"Pipeline error: {e}")
        import traceback
        st.code(traceback.format_exc())
    finally:
        st.session_state.pipeline_running = False
    st.rerun()


# ── Redo Handler ─────────────────────────────────────────────────────────────
if st.session_state.redo_scene:
    redo = st.session_state.redo_scene
    scene_num = redo["scene_number"]
    guidance = redo.get("guidance", "")
    custom_prompt = redo.get("custom_prompt")

    # Wrap EVERYTHING in try/except — never crash the session
    try:
        with open(config_path, encoding='utf-8') as f:
            raw = f.read()
        raw = re.sub(r'\$\{(\w+)\}', lambda m: os.environ.get(m.group(1), m.group(0)), raw)
        config = json.loads(raw)
        config["pipeline"]["pass_threshold"] = pass_threshold
        config["pipeline"]["max_retries"] = max_retries

        # Runtime API key injection (same as main pipeline)
        _redo_image_key = selected_image_config_key
        _gemini_key_redo = os.environ.get("GEMINI_API_KEY", "")
        if _gemini_key_redo and _redo_image_key in ("gemini_image", "imagen"):
            engine_map = {"gemini_image": "gemini-image", "imagen": "imagen-3"}
            config["gemini_api_key"] = {
                "api_key": _gemini_key_redo,
                "engine": engine_map[_redo_image_key],
            }
            _redo_image_key = "gemini_api_key"

        # Seedream via OpenRouter (redo path)
        _openrouter_key_redo = os.environ.get("OPENROUTER_API_KEY", "")
        if _openrouter_key_redo and _redo_image_key == "seedream":
            config["seedream"] = {
                "api_key": _openrouter_key_redo,
                "base_url": "https://openrouter.ai/api/v1",
                "model": "bytedance-seed/seedream-4.5",
            }

        orchestrator = Orchestrator(
            config,
            parser_model_override=selected_parser_model,
            critic_model_override=selected_critic_model,
            image_provider_key=_redo_image_key
        )

        # Guard: restore scenes from disk if missing (e.g. resumed session)
        if not st.session_state.scenes and st.session_state.run_folder:
            scenes_file = Path(st.session_state.run_folder) / "scenes.json"
            if scenes_file.exists():
                from modules.scene_parser import Scene, Visual
                with open(scenes_file, encoding='utf-8') as sf:
                    raw_scenes = json.load(sf)
                restored = []
                for sd in raw_scenes:
                    visuals = [Visual(**v) for v in sd.pop("visuals", [])]
                    restored.append(Scene(**sd, visuals=visuals))
                st.session_state.scenes = restored

        # Fallback: reconstruct scenes from pipeline report (old sessions without scenes.json)
        if not st.session_state.scenes and st.session_state.pipeline_report:
            from modules.scene_parser import Scene, Visual
            report_results = st.session_state.pipeline_report.get("results", [])
            if report_results:
                fallback = []
                for r in report_results:
                    desc = r.get("final_prompt", r.get("scene_title", ""))
                    vrs = r.get("visual_results", [])
                    visuals = []
                    if vrs:
                        for vr in vrs:
                            visuals.append(Visual(
                                visual_type=vr.get("visual_type", "key_visual"),
                                visual_description=vr.get("final_prompt", desc),
                            ))
                    fallback.append(Scene(
                        scene_number=r.get("scene_number", len(fallback) + 1),
                        scene_title=r.get("scene_title", f"Scene {len(fallback) + 1}"),
                        visual_description=desc,
                        visuals=visuals,
                    ))
                st.session_state.scenes = fallback
                logging.info(f"Reconstructed {len(fallback)} scenes from pipeline report")

        if not st.session_state.scenes:
            st.toast("⚠️ Cannot redo — no scenes cached. Re-run Generate first.", icon="⚠️")
            st.session_state.redo_scene = None
        else:
            # Redo progress UI
            redo_status = st.empty()
            redo_progress = st.empty()
            redo_step = st.empty()

            def _redo_progress(current, total, status_text, image_path):
                """Progress callback for redo — updates the progress bar."""
                pct = (current / total) if total > 0 else 0
                redo_progress.progress(min(pct, 1.0), text=status_text)

            redo_status.markdown(f"""
            <div class="pipeline-status">
                <div class="status-emoji">⚡</div>
                <div class="status-text">Regenerating Scene {scene_num}…</div>
                <div class="status-sub">{_pick_easter_egg(scene_num)}</div>
            </div>
            """, unsafe_allow_html=True)
            redo_progress.progress(0.0, text="Preparing…")

            new_result = orchestrator.redo_scene(
                scene_number=scene_num,
                scenes=st.session_state.scenes,
                style_preset_path=selected_preset,
                guidance=guidance if guidance else None,
                run_folder=st.session_state.run_folder,
                progress_callback=_redo_progress,
            )

            redo_progress.progress(1.0, text="✅ Done!")
            redo_status.empty()
            redo_progress.empty()
            redo_step.empty()

            # Update the report with new result
            report = st.session_state.pipeline_report
            for i, r in enumerate(report["results"]):
                if r["scene_number"] == scene_num:
                    report["results"][i] = new_result.to_dict()
                    break

            # Recalculate stats
            all_scores = [r["final_score"] for r in report["results"]]
            report["average_final_score"] = round(sum(all_scores) / len(all_scores), 1)
            report["passed_scenes"] = sum(1 for r in report["results"] if r["passed"])
            report["failed_scenes"] = report["total_scenes"] - report["passed_scenes"]

            st.session_state.pipeline_report = report
            st.session_state.redo_scene = None
            st.rerun()

    except Exception as e:
        # NEVER let redo crash the session — just show a toast
        st.toast(f"⚠️ Redo failed: {e}", icon="❌")
        logging.error(f"Redo handler error: {e}", exc_info=True)
        st.session_state.redo_scene = None

