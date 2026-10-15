"""Luna Vault Streamlit application entry point."""

import hashlib
from pathlib import Path

import streamlit as st
from PIL import Image

from config import UIConfig
from styles import apply_app_styles, render_app_header
from tabs.favorites_page import FavoritesPage
from tabs.hidden_page import HiddenPage
from tabs.shared import LunaVaultUI
from tabs.upload_page import UploadPage
from tabs.view_page import ViewImagesPage


class LunaVaultApp:
    """Compose and render the Luna Vault Streamlit interface."""

    LOGO_PATH = Path(__file__).resolve().parent / "assets" / "lunavault_logo_10kb.png"

    def __init__(self) -> None:
        self.config = UIConfig.from_env()
        self.shared_ui = LunaVaultUI(self.config)

    @staticmethod
    def set_gallery_view(mode: str) -> None:
        st.session_state.gallery_view_mode = mode

    @classmethod
    def source_revision(cls) -> str:
        source_root = Path(__file__).resolve().parent
        source_files = sorted(source_root.rglob("*.py"))
        source_files.extend(
            [source_root / ".streamlit" / "config.toml", cls.LOGO_PATH]
        )
        digest = hashlib.sha256()
        for source_file in source_files:
            if source_file.is_file():
                digest.update(source_file.relative_to(source_root).as_posix().encode())
                digest.update(source_file.read_bytes())
        return digest.hexdigest()

    @classmethod
    def show_reload_notice(cls) -> None:
        revision = cls.source_revision()
        previous_revision = st.session_state.get("ui_source_revision")
        st.session_state.ui_source_revision = revision
        if previous_revision is not None and previous_revision != revision:
            st.toast("Luna Vault updated", icon=":material/refresh:")

    def render_header(self) -> bool:
        brand_column, controls_column = st.columns(
            [5, 4], vertical_alignment="center", gap="medium"
        )
        with brand_column:
            render_app_header(self.LOGO_PATH)
        with controls_column:
            grid_column, list_column, upload_column = st.columns(
                [1, 1, 3], vertical_alignment="center", gap="small"
            )
            grid_column.button(
                ":material/grid_view:",
                help="Grid view",
                type=(
                    "primary"
                    if st.session_state.gallery_view_mode == "grid"
                    else "secondary"
                ),
                key="use_grid_view",
                on_click=self.set_gallery_view,
                args=("grid",),
                width="stretch",
            )
            list_column.button(
                ":material/view_list:",
                help="List view",
                type=(
                    "primary"
                    if st.session_state.gallery_view_mode == "list"
                    else "secondary"
                ),
                key="use_list_view",
                on_click=self.set_gallery_view,
                args=("list",),
                width="stretch",
            )
            return upload_column.button(
                "Upload Images",
                icon=":material/upload:",
                type="primary",
                key="open_upload_dialog",
                width="stretch",
            )

    def render_upload_dialog(self) -> None:
        @st.dialog("Upload images", width="large")
        def upload_dialog() -> None:
            UploadPage(self.config).render()

        upload_dialog()

    def selected_section(self) -> str:
        user_agent = st.context.headers.get("User-Agent", "")
        compact = self.shared_ui._is_mobile_user_agent(user_agent)
        labels = (
            [":material/visibility:", ":material/star:", ":material/lock:"]
            if compact
            else [
                ":material/visibility: View Images",
                ":material/star: Favorite Images",
                ":material/lock: Hidden Images",
            ]
        )
        tab_keys = ["view", "favorites", "hidden"]
        selected = st.container(key="gallery_navigation").segmented_control(
            "Gallery section",
            tab_keys,
            default=st.session_state.get("active_gallery_section", "view"),
            format_func=dict(zip(tab_keys, labels)).__getitem__,
            key="gallery_section_compact" if compact else "gallery_section_full",
            label_visibility="collapsed",
            width="stretch",
        )
        if selected is None:
            return st.session_state.active_gallery_section
        st.session_state.active_gallery_section = selected
        return selected

    def render(self) -> None:
        self.shared_ui.initialize_state()
        self.show_reload_notice()
        apply_app_styles(st.session_state.color_theme)
        if self.render_header():
            self.render_upload_dialog()

        selected_tab = self.selected_section()
        metadata = self.shared_ui.api.metadata()
        metadata_by_name = {item["name"]: item for item in metadata}
        vault_images = [
            path
            for path in self.shared_ui.list_vault_images()
            if path.name in metadata_by_name
        ]

        if selected_tab == "view":
            ViewImagesPage(self.config).render(vault_images, metadata_by_name)
        elif selected_tab == "favorites":
            FavoritesPage(self.config).render(vault_images, metadata_by_name)
        else:
            HiddenPage(self.config).render(vault_images, metadata_by_name)

    @classmethod
    def run(cls) -> None:
        st.set_page_config(
            page_title="Luna Vault",
            page_icon=Image.open(cls.LOGO_PATH),
            layout="wide",
            initial_sidebar_state="collapsed",
        )
        cls().render()


if __name__ == "__main__":
    LunaVaultApp.run()
