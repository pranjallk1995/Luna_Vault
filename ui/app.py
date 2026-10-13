"""Luna Vault Streamlit application entry point."""

import os

import hashlib
from pathlib import Path

import httpx
import streamlit as st

from config import UIConfig
from styles import apply_app_styles, render_app_header
from tabs.hidden_page import HiddenPage
from tabs.favorites_page import FavoritesPage
from tabs.shared import LunaVaultUI
from tabs.upload_page import UploadPage
from tabs.view_page import ViewImagesPage


LOGO_PATH = Path(__file__).resolve().parent / "assets" / "luna-vault-logo.png"


def set_gallery_view(mode: str) -> None:
    """Switch every gallery between grid and list presentation."""
    st.session_state.gallery_view_mode = mode


def toggle_color_theme() -> None:
    """Toggle the application between its dark and light palettes."""
    st.session_state.color_theme = (
        "light" if st.session_state.color_theme == "dark" else "dark"
    )


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
    apply_app_styles(st.session_state.color_theme)

    brand_column, controls_column = st.columns(
        [5, 4], vertical_alignment="center", gap="medium"
    )
    with brand_column:
        render_app_header(LOGO_PATH)
    with controls_column:
        theme_column, grid_column, list_column, upload_column = st.columns(
            [1, 1, 1, 3], vertical_alignment="center", gap="small"
        )
        theme_column.button(
            ":material/light_mode:"
            if st.session_state.color_theme == "dark"
            else ":material/dark_mode:",
            help=(
                "Use light theme"
                if st.session_state.color_theme == "dark"
                else "Use dark theme"
            ),
            key="toggle_color_theme",
            on_click=toggle_color_theme,
            width="stretch",
        )
        grid_column.button(
            ":material/grid_view:",
            help="Grid view",
            type="primary" if st.session_state.gallery_view_mode == "grid" else "secondary",
            key="use_grid_view",
            on_click=set_gallery_view,
            args=("grid",),
            width="stretch",
        )
        list_column.button(
            ":material/view_list:",
            help="List view",
            type="primary" if st.session_state.gallery_view_mode == "list" else "secondary",
            key="use_list_view",
            on_click=set_gallery_view,
            args=("list",),
            width="stretch",
        )
        open_upload = upload_column.button(
            "Upload Images",
            icon=":material/upload:",
            type="primary",
            key="open_upload_dialog",
            width="stretch",
        )

    @st.dialog("Upload images", width="large")
    def upload_dialog() -> None:
        """Show the existing drag-and-drop uploader in a modal window."""
        UploadPage(config).render()

    if open_upload:
        upload_dialog()

    if shared_ui.gallery_column_count() == 1:
        tab_labels = [
            ":material/visibility:",
            ":material/star:",
            ":material/lock:",
        ]
    else:
        tab_labels = [
            ":material/visibility: View Images",
            ":material/star: Favorite Images",
            ":material/lock: Hidden Images",
        ]
    view_tab, favorites_tab, hidden_tab = st.tabs(tab_labels)

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


    with view_tab:
        ViewImagesPage(config).render(vault_images, metadata_by_name)
    with favorites_tab:
        FavoritesPage(config).render(vault_images)
    with hidden_tab:
        HiddenPage(config).render(vault_images)


if __name__ == "__main__":
    main()
