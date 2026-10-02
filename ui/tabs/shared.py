"""Shared Streamlit gallery and state helpers."""

import html
from pathlib import Path

import streamlit as st
from PIL import Image, ImageOps

from config import UIConfig


@st.cache_data(show_spinner=False, max_entries=256)
def cached_gallery_thumbnail(
    image_path: str,
    modified_ns: int,
    card_size: tuple[int, int],
    background_color: str,
    padding: int,
) -> Image.Image:
    """Build and cache a gallery thumbnail until its source file changes."""
    del modified_ns  # Included in the cache key to invalidate modified images.
    card_width, card_height = card_size
    card = Image.new("RGB", card_size, background_color)
    content_size = (max(1, card_width - padding), max(1, card_height - padding))

    with Image.open(image_path) as source:
        source.draft("RGB", content_size)
        preview = ImageOps.exif_transpose(source).convert("RGB")
        preview.thumbnail(content_size)

    left = (card_width - preview.width) // 2
    top = (card_height - preview.height) // 2
    card.paste(preview, (left, top))
    return card


class LunaVaultUI:
    """Provide shared state, image, pagination, and gallery UI behavior."""

    def __init__(self, config: UIConfig) -> None:
        self.config = config
        self.image_dir = config.image_dir
        self.image_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def initialize_state() -> None:
        defaults = {
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
        }
        for key, value in defaults.items():
            if key not in st.session_state:
                st.session_state[key] = value

    @staticmethod
    def clear_search(state_key: str) -> None:
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
        prefix, separator, original_name = stored_name.partition("_")
        if (
            separator
            and len(prefix) == 32
            and all(character in "0123456789abcdef" for character in prefix.lower())
        ):
            return original_name
        return stored_name

    def render_image_name(self, container, stored_name: str) -> None:
        display_name = html.escape(self.display_name(stored_name), quote=True)
        container.markdown(
            f"""<div title="{display_name}" style="
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
                color: rgba(250, 250, 250, 0.6);
                font-size: 0.875rem;
                line-height: 1.25rem;
                margin-bottom: 0.25rem;
            ">{display_name}</div>""",
            unsafe_allow_html=True,
        )

    def create_gallery_thumbnail(self, image_path: Path) -> Image.Image:
        return cached_gallery_thumbnail(
            str(image_path),
            image_path.stat().st_mtime_ns,
            self.config.card_size,
            self.config.thumbnail_background_color,
            self.config.thumbnail_padding,
        )

    @staticmethod
    def change_gallery_page(
        state_key: str, selector_key: str, target_page: int
    ) -> None:
        st.session_state[state_key] = target_page
        st.session_state[selector_key] = target_page + 1

    @staticmethod
    def sync_gallery_page(state_key: str, selector_key: str) -> None:
        st.session_state[state_key] = st.session_state[selector_key] - 1

    def render_gallery_navigation(
        self, page_count: int, state_key: str, key_prefix: str
    ) -> int:
        """Render callback-driven controls and return the bounded page index."""
        current_page = min(max(st.session_state[state_key], 0), page_count - 1)
        st.session_state[state_key] = current_page
        selector_key = f"{key_prefix}_page"

        previous_column, page_column, next_column = st.columns([1, 2, 1])
        previous_column.button(
            ":material/arrow_back:",
            disabled=current_page == 0,
            width="stretch",
            key=f"{key_prefix}_previous",
            on_click=self.change_gallery_page,
            args=(state_key, selector_key, current_page - 1),
        )

        # Callbacks update state before Streamlit instantiates the next rerun.
        page_column.selectbox(
            "Page",
            options=list(range(1, page_count + 1)),
            index=current_page,
            label_visibility="collapsed",
            key=selector_key,
            on_change=self.sync_gallery_page,
            args=(state_key, selector_key),
        )

        next_column.button(
            ":material/arrow_forward:",
            disabled=current_page == page_count - 1,
            width="stretch",
            key=f"{key_prefix}_next",
            on_click=self.change_gallery_page,
            args=(state_key, selector_key, current_page + 1),
        )

        return current_page

    def paginated_images(
        self, vault_images: list[Path], page_state_key: str, key_prefix: str
    ) -> tuple[int, list[Path]]:
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
    ) -> None:
        filename_columns = st.columns(self.config.gallery_columns)
        for column, image_path in zip(filename_columns, row_images):
            self.render_image_name(column, image_path.name)
            metadata = (metadata_by_name or {}).get(image_path.name)
            if metadata:
                with column.expander("Caption & tags", expanded=False):
                    st.write(metadata["caption"])
                    st.caption("  ".join(f"#{tag}" for tag in metadata["tags"]))
