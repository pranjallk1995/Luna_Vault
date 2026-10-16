"""Luna Visia Streamlit application entry point."""

import hashlib
import inspect
from pathlib import Path

import streamlit as st
from PIL import Image

from config import UIConfig
from styles import LunaStyle
from tabs.favorites_page import FavoritesPage
from tabs.hidden_page import HiddenPage
from tabs.shared import LunaVisiaUI
from tabs.upload_page import UploadPage
from tabs.view_page import ViewImagesPage


class LunaVisiaApp:
    """Compose and render the Luna Visia Streamlit interface."""

    SECTION_KEY = "gallery-section"
    LAST_SECTION_KEY = "gallery-section-last"

    def __init__(self) -> None:
        self.config = UIConfig.from_env()
        self.shared_ui = LunaVisiaUI(self.config)

    @staticmethod
    def set_gallery_view(mode: str) -> None:
        st.session_state.gallery_view_mode = mode

    @classmethod
    def source_revision(cls) -> str:
        source_root = Path(__file__).resolve().parent
        source_files = sorted(source_root.rglob("*.py"))
        source_files.extend(
            [source_root / ".streamlit" / "config.toml", UIConfig.LOGO_PATH]
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
            st.toast("Luna Visia updated", icon=":material/refresh:")

    def render_header(self) -> bool:
        return LunaStyle.header(
            UIConfig.LOGO_PATH,
            st.session_state.gallery_view_mode,
            self.set_gallery_view,
        )

    def render_upload_dialog(self) -> None:
        @st.dialog("Upload images", width="large")
        def upload_dialog() -> None:
            UploadPage(self.config).render()

        upload_dialog()

    @classmethod
    def preserve_section_selection(cls) -> None:
        """Retain the last gallery section when the active segment is clicked."""
        selected = st.session_state.get(cls.SECTION_KEY)
        if selected is None:
            st.session_state[cls.SECTION_KEY] = st.session_state.get(
                cls.LAST_SECTION_KEY, "view"
            )
        else:
            st.session_state[cls.LAST_SECTION_KEY] = selected

    def selected_section(self) -> str:
        labels = [
            ":material/visibility: View Images",
            ":material/star: Favorite Images",
            ":material/lock: Hidden Images",
        ]
        tab_keys = ["view", "favorites", "hidden"]
        navigation_options = {
            "options": tab_keys,
            "format_func": dict(zip(tab_keys, labels)).__getitem__,
            "key": self.SECTION_KEY,
            "on_change": self.preserve_section_selection,
            "label_visibility": "collapsed",
        }
        if self.SECTION_KEY not in st.session_state:
            navigation_options["default"] = "view"
        if "width" in inspect.signature(st.segmented_control).parameters:
            navigation_options["width"] = "stretch"
        navigation_container = st.container(key="gallery_navigation")
        active_section = st.session_state.get(
            self.SECTION_KEY,
            st.session_state.get(self.LAST_SECTION_KEY, "view"),
        )
        navigation_container.markdown(
            f'<span class="lv-selected-{active_section}"></span>',
            unsafe_allow_html=True,
        )
        selected = navigation_container.segmented_control(
            "Gallery section",
            **navigation_options,
        )
        return selected or st.session_state.get(self.LAST_SECTION_KEY, "view")

    def render(self) -> None:
        self.shared_ui.initialize_state()
        self.show_reload_notice()
        LunaStyle.apply(st.session_state.color_theme)
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
            page_title="Luna Visia",
            page_icon=Image.open(UIConfig.LOGO_PATH),
            layout="wide",
            initial_sidebar_state="collapsed",
        )
        cls().render()


if __name__ == "__main__":
    LunaVisiaApp.run()
