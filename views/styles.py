def get_custom_css():
    return """
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
"""

def inject_js():
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
