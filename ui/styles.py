"""Shared visual styling for the Luna Vault Streamlit application."""

import streamlit as st


def apply_app_styles() -> None:
    """Apply Luna Vault's presentation layer without altering widget behavior."""
    st.markdown(
        """
        <style>
        :root { --lv-bg:#080c18; --lv-border:rgba(148,163,184,.18); --lv-strong:rgba(167,139,250,.42); --lv-muted:#9aa6bd; --lv-accent:#a78bfa; --lv-soft:rgba(167,139,250,.12); }
        .stApp { background:radial-gradient(circle at 82% -10%,rgba(124,58,237,.14),transparent 30rem),var(--lv-bg); }
        .block-container { max-width:1180px; padding-top:1.35rem; padding-bottom:3rem; }
        header[data-testid="stHeader"] { background:transparent; }
        #MainMenu,footer,div[data-testid="stDecoration"] { display:none; }
        .lv-header { display:flex; align-items:center; gap:.9rem; margin-bottom:1rem; }
        .lv-mark { display:grid; place-items:center; width:2.65rem; height:2.65rem; border:1px solid var(--lv-strong); border-radius:.85rem; background:linear-gradient(145deg,rgba(167,139,250,.22),rgba(56,189,248,.08)); color:#ddd6fe; font-size:.82rem; font-weight:750; box-shadow:0 12px 34px rgba(0,0,0,.22); }
        .lv-title { margin:0; color:#f8fafc; font-family:inherit; font-size:clamp(1.65rem,3vw,2.15rem); font-weight:720; letter-spacing:-.04em; line-height:1; }
        .lv-subtitle { margin:.32rem 0 0; color:var(--lv-muted); font-size:.84rem; }
        .lv-section { margin:.9rem 0 1.15rem; }
        .lv-eyebrow { color:var(--lv-accent); font-size:.72rem; font-weight:700; letter-spacing:.13em; text-transform:uppercase; }
        .lv-section h2 { margin:.25rem 0; color:#f1f5f9; font-size:1.3rem; letter-spacing:-.025em; }
        .lv-section p { max-width:45rem; margin:0; color:var(--lv-muted); font-size:.88rem; }
        div[data-testid="stTabs"] [data-baseweb="tab-list"] { gap:.35rem; padding:.28rem; border:1px solid var(--lv-border); border-radius:.9rem; background:rgba(17,24,42,.72); }
        div[data-testid="stTabs"] [data-baseweb="tab"] { height:2.55rem; padding:0 1rem; border-radius:.65rem; color:var(--lv-muted); }
        div[data-testid="stTabs"] [aria-selected="true"] { background:var(--lv-soft); color:#ede9fe; }
        div[data-testid="stTabs"] [data-baseweb="tab-highlight"] { display:none; }
        div[data-testid="stVerticalBlockBorderWrapper"] > div { border-color:var(--lv-border); border-radius:14px; background:rgba(17,24,42,.62); box-shadow:0 10px 30px rgba(0,0,0,.12); }
        div[data-testid="stFileUploader"] section { min-height:10rem; border:1px dashed rgba(167,139,250,.48); border-radius:14px; background:linear-gradient(145deg,rgba(167,139,250,.09),rgba(17,24,42,.7)); }
        div[data-testid="stFileUploader"] section:hover { border-color:var(--lv-accent); background:rgba(167,139,250,.1); }
        div[data-baseweb="input"] > div,div[data-baseweb="select"] > div { border-color:var(--lv-border)!important; border-radius:.75rem!important; background:rgba(17,24,42,.84)!important; }
        .stButton > button,.stDownloadButton > button,div[data-testid="stFormSubmitButton"] > button { min-height:2.55rem; border-color:var(--lv-border); border-radius:.75rem; background:rgba(17,24,42,.82); transition:border-color 140ms ease,background 140ms ease,transform 140ms ease; }
        .stButton > button:hover,.stDownloadButton > button:hover,div[data-testid="stFormSubmitButton"] > button:hover { border-color:var(--lv-strong); background:var(--lv-soft); color:#f5f3ff; transform:translateY(-1px); }
        button[kind="primary"] { border-color:transparent!important; background:linear-gradient(135deg,#8b5cf6,#7c3aed)!important; color:white!important; }
        div[data-testid="stImage"] img { border-radius:.8rem; }
        div[data-testid="stExpander"] { overflow:hidden; border-color:var(--lv-border); border-radius:.35rem; background:rgba(17,24,42,.5); }
        div[data-testid="stAlert"] { border-radius:.85rem; border-color:var(--lv-border); }
        div[data-testid="stForm"] { padding:1.25rem; border-color:var(--lv-border); border-radius:14px; background:rgba(17,24,42,.66); }
        div[data-testid="stSegmentedControl"] { padding:.25rem; border:1px solid var(--lv-border); border-radius:.85rem; background:rgba(17,24,42,.66); }
        @media (max-width:700px) { .block-container { padding:.85rem .8rem 2rem; } .lv-subtitle { display:none; } div[data-testid="stTabs"] [data-baseweb="tab"] { padding:0 .55rem; } }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_app_header() -> None:
    """Render the compact branded application header."""
    st.markdown(
        """
        <div class="lv-header">
            <div class="lv-mark">LV</div>
            <div>
                <h1 class="lv-title">Luna Vault</h1>
                <p class="lv-subtitle">Private, AI-organized image storage</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_section_intro(eyebrow: str, title: str, description: str) -> None:
    """Render a consistent heading for a top-level app section."""
    st.markdown(
        f"""
        <div class="lv-section">
            <div class="lv-eyebrow">{eyebrow}</div>
            <h2>{title}</h2>
            <p>{description}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
