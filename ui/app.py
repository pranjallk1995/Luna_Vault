"""Luna Vault Streamlit application entry point."""

import os

import hashlib
from pathlib import Path

import httpx
import streamlit as st

from config import UIConfig
from styles import apply_app_styles, render_app_header, render_section_intro
from tabs.hidden_page import HiddenPage
from tabs.favorites_page import FavoritesPage
from tabs.shared import LunaVaultUI
from tabs.upload_page import UploadPage
from tabs.view_page import ViewImagesPage


LOGO_PATH = Path(__file__).resolve().parent / "assets" / "luna-vault-logo.png"


def source_revision() -> str:
    """Return a stable digest of the UI source currently loaded by Streamlit."""
    source_root = Path(__file__).resolve().parent
    source_files = sorted(source_root.rglob("*.py"))
    source_files.append(source_root / ".streamlit" / "config.toml")
    source_files.append(LOGO_PATH)
    digest = hashlib.sha256()
    for source_file in source_files:
        if not source_file.is_file():
            continue
        digest.update(source_file.relative_to(source_root).as_posix().encode())
        digest.update(source_file.read_bytes())
    return digest.hexdigest()


def show_reload_notice() -> None:
    """Notify an existing session only when its loaded UI source has changed."""
    revision = source_revision()
    previous_revision = st.session_state.get("ui_source_revision")
    st.session_state.ui_source_revision = revision
    if previous_revision is not None and previous_revision != revision:
        st.toast("Luna Vault updated", icon=":material/refresh:")


def main() -> None:
    """Configure Streamlit and render the active Luna Vault page."""
    st.set_page_config(
        page_title="Luna Vault",
        page_icon=str(LOGO_PATH),
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    config = UIConfig.from_env()
    shared_ui = LunaVaultUI(config)
    shared_ui.initialize_state()
    show_reload_notice()
    apply_app_styles()
    render_app_header(LOGO_PATH)

    if shared_ui.gallery_column_count() == 1:
        tab_labels = [
            ":material/upload:",
            ":material/visibility:",
            ":material/star:",
            ":material/lock:",
        ]
    else:
        tab_labels = [
            ":material/upload: Upload Images",
            ":material/visibility: View Images",
            ":material/star: Favorite Images",
            ":material/lock: Hidden Images",
        ]
    upload_tab, view_tab, favorites_tab, hidden_tab = st.tabs(tab_labels)

    metadata_response = httpx.get(
        f"{config.api_url}/api/metadata",
        headers=config.api_headers,
        timeout=10.0,
    )
    metadata_response.raise_for_status()
    metadata = metadata_response.json()["images"]
    metadata_by_name = {item["name"]: item for item in metadata}
    vault_images = [
        path
        for path in shared_ui.list_vault_images()
        if path.name in metadata_by_name
    ]

    with upload_tab:
        render_section_intro(
            "Ingest",
            "Add images",
            "Upload one or many images and let Luna Vault generate searchable details.",
        )
        UploadPage(config).render()
    with view_tab:
        render_section_intro(
            "Library",
            "Browse your vault",
            "Find, inspect, download, or remove images from your private collection.",
        )
        ViewImagesPage(config).render(vault_images, metadata_by_name)
    with favorites_tab:
        render_section_intro(
            "Curated",
            "Your favorites",
            "Keep the images you return to most in one focused collection.",
        )
        FavoritesPage(config).render(vault_images)
    with hidden_tab:
        render_section_intro(
            "Protected space",
            "Hidden vault",
            "Keep sensitive images behind a separate password-protected view.",
        )
        HiddenPage(config).render(vault_images)


if __name__ == "__main__":
    main()
