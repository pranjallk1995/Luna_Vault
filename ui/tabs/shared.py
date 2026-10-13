"""Shared Streamlit gallery and state helpers."""

import html
import time
from pathlib import Path

import streamlit as st
from PIL import Image, ImageOps

from config import UIConfig


@st.cache_data(show_spinner=False, max_entries=256)
def cached_gallery_thumbnail(
    image_path: str,
    modified_ns: int,
    max_size: tuple[int, int],
) -> Image.Image:
    """Build a natural-aspect thumbnail bounded to the gallery card size."""
    del modified_ns  # Included in the cache key to invalidate modified images.

    with Image.open(image_path) as source:
        source.draft("RGB", max_size)
        preview = ImageOps.exif_transpose(source).convert("RGB")
        preview.thumbnail(max_size)

    return preview


class LunaVaultUI:
    """Provide shared state, image, pagination, and gallery UI behavior."""

    def __init__(self, config: UIConfig) -> None:
        """Initialize this component and its required dependencies."""
        self.config = config
        self.image_dir = config.image_dir
        self.image_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _is_mobile_user_agent(user_agent: str) -> bool:
        """Identify common phone and tablet browser user agents."""
        normalized = user_agent.casefold()
        return any(
            token in normalized
            for token in ("android", "iphone", "ipad", "ipod", "mobile")
        )

    def gallery_column_count(self) -> int:
        """Use one gallery column on mobile and the configured count elsewhere."""
        if st.session_state.get("gallery_view_mode") == "list":
            return 1
        user_agent = st.context.headers.get("User-Agent", "")
        return (
            1
            if self._is_mobile_user_agent(user_agent)
            else self.config.gallery_columns
        )

    def gallery_search_placeholder(self) -> str:
        """Use a compact search hint on mobile displays."""
        return (
            "Filename"
            if self.gallery_column_count() == 1
            else "Type part of a filename"
        )

    @staticmethod
    def initialize_state() -> None:
        """Initialize all Streamlit session-state values used by the application."""
        defaults = {
            "color_theme": "dark",
            "gallery_view_mode": "grid",
            "saved_uploads": set(),
            "uploaded_images": [],
            "uploader_key": 0,
            "gallery_generation": 0,
            "gallery_page": 0,
            "gallery_selection": set(),
            "pending_delete": [],
            "view_generation": 0,
            "view_page": 0,
            "pending_view_delete": None,
            "view_delete_notice": None,
            "download_generation": 0,
            "download_page": 0,
            "download_selection": set(),
            "hidden_auth_token": None,
            "hidden_generation": 0,
            "hidden_page": 0,
            "hidden_selection": set(),
            "pending_hidden_delete": None,
            "hide_generation": 0,
            "hide_page": 0,
            "hide_selection": set(),
            "favorite_generation": 0,
            "favorite_page": 0,
            "favorite_selection": set(),
            "pending_favorite_delete": None,
            "add_favorite_generation": 0,
            "add_favorite_page": 0,
            "add_favorite_selection": set(),
            "gallery_transitions": {},
        }
        for key, value in defaults.items():
            if key not in st.session_state:
                st.session_state[key] = value

    @staticmethod
    def clear_search(state_key: str) -> None:
        """Reset a named search field in Streamlit session state."""
        st.session_state[state_key] = ""

    def list_vault_images(self) -> list[Path]:
        """List supported vault files newest first without decoding images."""
        return sorted(
            (
                path
                for path in self.image_dir.iterdir()
                if path.is_file()
                and path.suffix.lower() in self.config.image_extensions
            ),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )

    @staticmethod
    def display_name(stored_name: str) -> str:
        """Remove the internal storage prefix from a user-facing filename."""
        prefix, separator, original_name = stored_name.partition("_")
        if (
            separator
            and len(prefix) == 32
            and all(character in "0123456789abcdef" for character in prefix.lower())
        ):
            return original_name
        return stored_name

    def render_image_name(self, container, stored_name: str) -> None:
        """Render a single-line, truncated filename with its full value as a tooltip."""
        display_name = html.escape(self.display_name(stored_name), quote=True)
        container.markdown(
            f"""<div title="{display_name}" style="
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
                color: var(--lv-muted);
                font-size: 0.875rem;
                line-height: 1.25rem;
                margin-bottom: 0.25rem;
            ">{display_name}</div>""",
            unsafe_allow_html=True,
        )

    def create_gallery_thumbnail(self, image_path: Path) -> Image.Image:
        """Return a cached, aspect-preserving thumbnail for a vault image."""
        return cached_gallery_thumbnail(
            str(image_path),
            image_path.stat().st_mtime_ns,
            self.config.card_size,
        )

    @staticmethod
    def change_gallery_page(
        state_key: str, selector_key: str, target_page: int
    ) -> None:
        """Queue a button-driven page change so the old grid can animate out."""
        st.session_state.gallery_transitions[state_key] = {
            "phase": "out",
            "target": target_page,
        }
        st.session_state[selector_key] = target_page + 1

    @staticmethod
    def sync_gallery_page(state_key: str, selector_key: str) -> None:
        """Queue a selector-driven page change without replacing widget state."""
        target_page = st.session_state[selector_key] - 1
        if target_page != st.session_state[state_key]:
            st.session_state.gallery_transitions[state_key] = {
                "phase": "out",
                "target": target_page,
            }

    @staticmethod
    def gallery_transition_phase(state_key: str) -> str:
        """Return the active animation phase for a gallery."""
        transition = st.session_state.gallery_transitions.get(state_key)
        return transition["phase"] if transition else "idle"

    def render_gallery_transition_marker(self, state_key: str) -> None:
        """Mark the current gallery rerun for its scoped CSS animation."""
        phase = self.gallery_transition_phase(state_key)
        st.markdown(
            f'<span class="lv-gallery-transition lv-gallery-{phase}"></span>',
            unsafe_allow_html=True,
        )

    @staticmethod
    def finish_gallery_transition(state_key: str) -> None:
        """Finish exit plus a short gap, then rerun the target page for entry."""
        transition = st.session_state.gallery_transitions.get(state_key)
        if not transition:
            return
        if transition["phase"] == "out":
            # Deltas for the old grid are already emitted. Keep it mounted through
            # the 160 ms exit and a brief 50 ms pause before swapping page state.
            time.sleep(0.21)
            st.session_state[state_key] = transition["target"]
            transition["phase"] = "in"
            st.rerun()
        st.session_state.gallery_transitions.pop(state_key, None)

    def render_gallery_navigation(
        self, page_count: int, state_key: str, key_prefix: str
    ) -> int:
        """Render callback-driven controls and return the bounded page index."""
        current_page = min(max(st.session_state[state_key], 0), page_count - 1)
        st.session_state[state_key] = current_page
        selector_key = f"{key_prefix}_page"
        exiting = self.gallery_transition_phase(state_key) == "out"

        previous_column, page_column, next_column = st.columns([7, 26, 7])
        previous_column.button(
            ":material/arrow_back:",
            disabled=exiting or current_page == 0,
            width="stretch",
            key=f"{key_prefix}_previous",
            on_click=self.change_gallery_page,
            args=(state_key, selector_key, current_page - 1),
        )

        # Callbacks update state before Streamlit instantiates the next rerun.
        page_column.selectbox(
            "Page",
            options=list(range(1, page_count + 1)),
            format_func=lambda page: f"Page {page}",
            index=current_page,
            label_visibility="collapsed",
            disabled=exiting,
            key=selector_key,
            on_change=self.sync_gallery_page,
            args=(state_key, selector_key),
        )

        next_column.button(
            ":material/arrow_forward:",
            disabled=exiting or current_page == page_count - 1,
            width="stretch",
            key=f"{key_prefix}_next",
            on_click=self.change_gallery_page,
            args=(state_key, selector_key, current_page + 1),
        )

        return current_page

    def paginated_images(
        self, vault_images: list[Path], page_state_key: str, key_prefix: str
    ) -> tuple[int, list[Path]]:
        """Render pagination controls and return the images on the active page."""
        page_count = (
            len(vault_images) + self.config.images_per_page - 1
        ) // self.config.images_per_page
        current_page = self.render_gallery_navigation(
            page_count, page_state_key, f"{key_prefix}_{page_count}"
        )
        page_start = current_page * self.config.images_per_page
        return (
            current_page,
            vault_images[page_start : page_start + self.config.images_per_page],
        )

    def render_filename_row(
        self,
        row_images: list[Path],
        metadata_by_name: dict[str, dict] | None = None,
        columns: int | None = None,
    ) -> None:
        """Render filenames and optional persisted metadata below one gallery row."""
        filename_columns = st.columns(columns or self.gallery_column_count())
        for column, image_path in zip(filename_columns, row_images):
            self.render_image_name(column, image_path.name)
            metadata = (metadata_by_name or {}).get(image_path.name)
            if metadata:
                with column.expander("Caption & tags", expanded=False):
                    st.write(metadata["caption"])
                    st.caption("  ".join(f"#{tag}" for tag in metadata["tags"]))
