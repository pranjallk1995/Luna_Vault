"""Shared visual styling for the Luna Vault Streamlit application."""

import base64
from pathlib import Path

import streamlit as st


def apply_app_styles(theme: str = "dark") -> None:
    """Apply the selected Luna Vault palette without altering widget behavior."""
    palette = (
        "--lv-bg:#f5f7fb;--lv-surface:#ffffff;--lv-control:#eef2f8;"
        "--lv-control-hover:#e2e8f0;--lv-text:#111827;--lv-muted:#64748b;"
        "--lv-border:rgba(71,85,105,.20);--lv-strong:rgba(99,102,241,.48);"
        "--lv-accent:#6366f1;--lv-soft:rgba(99,102,241,.12);"
        if theme == "light"
        else
        "--lv-bg:#080c18;--lv-surface:#11182a;--lv-control:#121a2d;"
        "--lv-control-hover:#1a2440;--lv-text:#f1f5f9;--lv-muted:#9aa6bd;"
        "--lv-border:rgba(148,163,184,.18);--lv-strong:rgba(167,139,250,.42);"
        "--lv-accent:#a78bfa;--lv-soft:rgba(167,139,250,.12);"
    )
    st.markdown(
        f"<style>:root {{{palette}}}</style>", unsafe_allow_html=True
    )
    st.markdown(
        """
        <style>

        .stApp { color:var(--lv-text); background:radial-gradient(circle at 82% -10%,rgba(124,58,237,.14),transparent 30rem),var(--lv-bg); }
        .block-container { max-width:1180px; padding-top:1.35rem; padding-bottom:3rem; }
        .stApp p,.stApp label,.stApp [data-testid="stMarkdownContainer"] { color:var(--lv-text); }
        div[data-testid="stHorizontalBlock"]:has(.lv-header) { align-items:center; margin-bottom:.55rem; }
        div[data-testid="stHorizontalBlock"]:has(.lv-header) .stButton > button { white-space:nowrap; }
        header[data-testid="stHeader"] { background:transparent; }
        #MainMenu,footer,div[data-testid="stDecoration"] { display:none; }
        .lv-header { display:flex; align-items:center; gap:.9rem; margin-bottom:1rem; }
        .lv-mark { display:block; width:2.65rem; height:2.65rem; border:1px solid var(--lv-strong); border-radius:.85rem; object-fit:cover; box-shadow:0 12px 34px rgba(0,0,0,.22); }
        .lv-title { margin:0; color:var(--lv-text); font-family:inherit; font-size:clamp(1.65rem,3vw,2.15rem); font-weight:720; letter-spacing:-.04em; line-height:1; }
        .lv-subtitle { margin:.32rem 0 0; color:var(--lv-muted); font-size:.84rem; }
        div[data-testid="stTabs"] [data-baseweb="tab-list"] { gap:.35rem; padding:.28rem; border:1px solid var(--lv-border); border-radius:.9rem; background:var(--lv-surface); }
        div[data-testid="stTabs"] [data-baseweb="tab"] { height:2.55rem; padding:0 1rem; border-radius:.65rem; color:var(--lv-muted); }
        div[data-testid="stTabs"] [aria-selected="true"] { background:var(--lv-soft); color:#ede9fe; }
        div[data-testid="stTabs"] [data-baseweb="tab-highlight"] { display:none; }
        div[data-testid="stPopover"] > button[data-testid] {
            width:1.75rem!important; min-width:1.75rem!important;
            height:2rem!important; min-height:2rem!important; padding:0!important;
            border:0!important; border-radius:.35rem!important;
            background:transparent!important; box-shadow:none!important;
        }
        div[data-testid="stPopover"] > button[data-testid]:hover,
        div[data-testid="stPopover"] > button[data-testid]:focus {
            border:0!important; background:transparent!important;
            box-shadow:none!important; transform:none!important; outline:0!important;
        }
        div[data-testid="stPopover"] > button[data-testid] svg:last-child {
            display:none!important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] > div { border-color:var(--lv-border); border-radius:14px; background:var(--lv-surface); box-shadow:0 10px 30px rgba(0,0,0,.12); }
        div[data-testid="stFileUploader"] section { min-height:10rem; border:1px dashed rgba(167,139,250,.48); border-radius:14px; background:linear-gradient(145deg,rgba(167,139,250,.09),rgba(17,24,42,.7)); }
        div[data-testid="stFileUploader"] section:hover { border-color:var(--lv-accent); background:rgba(167,139,250,.1); }
        div[data-baseweb="input"] > div,div[data-baseweb="select"] > div { border-color:var(--lv-border)!important; border-radius:.75rem!important; background:var(--lv-surface)!important; }
        .stButton > button,.stDownloadButton > button,div[data-testid="stFormSubmitButton"] > button { min-height:2.55rem; border-color:var(--lv-border); border-radius:.75rem; background:rgba(17,24,42,.82); transition:border-color 140ms ease,background 140ms ease,transform 140ms ease; }
        .stButton > button:hover,.stDownloadButton > button:hover,div[data-testid="stFormSubmitButton"] > button:hover { border-color:var(--lv-strong); background:var(--lv-soft); color:#f5f3ff; transform:translateY(-1px); }
        button[kind="primary"] { border-color:transparent!important; background:linear-gradient(135deg,#8b5cf6,#7c3aed)!important; color:white!important; }
        div[data-testid="stImage"] img { border-radius:.8rem; }
        div[data-testid="stExpander"] { overflow:hidden; border-color:var(--lv-border); border-radius:.35rem; background:rgba(17,24,42,.5); }
        div[data-testid="stAlert"] { border-radius:.85rem; border-color:var(--lv-border); }
        div[data-testid="stForm"] { padding:1.25rem; border-color:var(--lv-border); border-radius:14px; background:rgba(17,24,42,.66); }
        /* Shared control system: native, icon, form, and download buttons. */
        .stButton > button,.stDownloadButton > button,
        div[data-testid="stFormSubmitButton"] > button,
        button[data-testid^="stBaseButton"] {
            min-height:2.625rem!important; height:2.625rem;
            padding:.45rem .9rem!important; border:1px solid var(--lv-border)!important;
            border-radius:.5rem!important; background:var(--lv-control)!important;
            color:var(--lv-text)!important; font-weight:650!important;
            box-shadow:0 1px 0 rgba(255,255,255,.03) inset;
        }
        .stButton > button:hover,.stDownloadButton > button:hover,
        div[data-testid="stFormSubmitButton"] > button:hover,
        button[data-testid^="stBaseButton"]:hover {
            border-color:var(--lv-strong)!important; background:var(--lv-control-hover)!important;
            color:var(--lv-text)!important; transform:translateY(-1px);
        }
        .stButton > button:focus-visible,.stDownloadButton > button:focus-visible,
        button[data-testid^="stBaseButton"]:focus-visible {
            outline:2px solid var(--lv-accent)!important; outline-offset:2px;
        }
        button[data-testid="stBaseButton-primary"],button[kind="primary"] {
            border-color:transparent!important; background:linear-gradient(135deg,#8b5cf6,#7c3aed)!important;
        }
        div[data-testid="stPopover"] button {
            width:1.75rem!important; min-width:1.75rem!important;
            height:2rem!important; min-height:2rem!important; padding:0!important;
            border:0!important; background:transparent!important;
            box-shadow:none!important; transform:none!important; outline:0!important;
        }
        div[data-testid="stPopover"] button:hover,
        div[data-testid="stPopover"] button:focus,
        div[data-testid="stPopover"] button:focus-visible {
            border:0!important; background:transparent!important;
            box-shadow:none!important; transform:none!important; outline:0!important;
        }
        div[data-testid="stPopover"] button svg { display:none!important; }
        div[data-testid="stPopoverBody"] {
            width:6.75rem!important; min-width:6.75rem!important; max-width:6.75rem!important;
            margin-top:-.4rem!important; margin-right:0!important; margin-bottom:0!important;
            padding:.4rem!important; border-radius:.65rem!important;
        }
        div[data-testid="stPopoverBody"] div[data-testid="stHorizontalBlock"] {
            gap:.35rem!important;
        }
        div[data-testid="stPopoverBody"] .stButton > button,
        div[data-testid="stPopoverBody"] .stDownloadButton > button {
            padding:0!important; min-width:2.5rem!important;
        }
        button:disabled { opacity:.42!important; transform:none!important; cursor:not-allowed!important; }
        div[data-baseweb="input"] > div,div[data-baseweb="select"] > div { min-height:2.625rem; border-radius:.5rem!important; }
        .lv-gallery-transition { display:none; }
        @keyframes lv-gallery-out { to { opacity:0; transform:translateY(-16px); } }
        @keyframes lv-gallery-in { from { opacity:0; transform:translateY(16px); } to { opacity:1; transform:translateY(0); } }
        div[data-testid="stElementContainer"]:has(.lv-gallery-out) ~ * {
            animation:lv-gallery-out 160ms ease-in forwards;
            pointer-events:none;
            will-change:opacity,transform;
        }
        div[data-testid="stElementContainer"]:has(.lv-gallery-in) ~ * {
            animation:lv-gallery-in 180ms ease-out both;
            will-change:opacity,transform;
        }
        @media (prefers-reduced-motion:reduce) { div[data-testid="stElementContainer"]:has(.lv-gallery-transition) ~ * { animation:none!important; } }
        @media (max-width:700px) {
            .block-container { padding:.85rem .8rem 2rem; }
            div[data-testid="stHorizontalBlock"]:has(.lv-header) { flex-wrap:wrap!important; }
            div[data-testid="stHorizontalBlock"]:has(.lv-header) > div[data-testid="stColumn"] { flex:1 1 100%!important; width:100%!important; }
            .lv-subtitle { display:none; }
            div[data-testid="stTabs"] [data-baseweb="tab-list"] { width:100%; justify-content:space-around; }
            div[data-testid="stTabs"] [data-baseweb="tab"] { flex:1 1 0; justify-content:center; padding:0 .55rem; }
            div[data-testid="stHorizontalBlock"] { flex-direction:row!important; flex-wrap:nowrap!important; gap:.5rem!important; }
            div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] { min-width:0!important; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_app_header(logo_path: Path) -> None:
    """Render the compact branded application header."""
    logo_base64 = base64.b64encode(logo_path.read_bytes()).decode("ascii")
    st.markdown(
        f"""
        <div class="lv-header">
            <img class="lv-mark" src="data:image/png;base64,{logo_base64}" alt="Luna Vault logo">
            <div>
                <h1 class="lv-title">Luna Vault</h1>
                <p class="lv-subtitle">Private, AI-organized image storage</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
