"""Favorites collection using the same gallery experience as View Images."""

from pathlib import Path

import streamlit as st

from tabs.shared import LunaVaultUI
from tabs.view_page import ViewPage


class FavoriteGallery(ViewPage):
    """View-style gallery with Favorite-specific item actions."""

    def render_image_menu(
        self, container, image_path: Path, generation: int, key_prefix: str
    ) -> None:
        """Render only download and delete inside the Favorite item menu."""
        with container.popover(":material/more_vert:", use_container_width=True):
            download_column, delete_column = st.columns(2, gap="small")
            download_column.download_button(
                ":material/download:",
                data=image_path.read_bytes(),
                file_name=self.display_name(image_path.name),
                mime=f"image/{image_path.suffix.lower().lstrip('.')}",
                width="stretch",
                key=f"{key_prefix}_download_{generation}_{image_path.name}",
            )
            if delete_column.button(
                ":material/delete:",
                width="stretch",
                key=f"{key_prefix}_delete_{generation}_{image_path.name}",
            ):
                st.session_state.pending_view_hide = None
                st.session_state.pending_view_delete = image_path.name
                st.rerun()


class FavoritesPage(LunaVaultUI):
    """Render Favorite images without a secondary Add Images tab."""

    def render(
        self, visible_images: list[Path], metadata_by_name: dict[str, dict]
    ) -> None:
        """Render Favorites with the View Images layout and interactions."""
        favorite_names = {item["name"] for item in self.api.favorites()}
        favorite_images = [
            path for path in visible_images if path.name in favorite_names
        ]
        query = (
            st.text_input(
                "Search Favorites by image name",
                placeholder=self.gallery_search_placeholder(),
                key="favorite_name_search",
                icon=":material/search:",
                label_visibility="collapsed",
            )
            .strip()
            .casefold()
        )
        filtered = [
            path
            for path in favorite_images
            if query in self.display_name(path.name).casefold()
        ]
        if query and not filtered:
            st.info("No favorite image names match your search.")
            return
        FavoriteGallery(self.config).render(filtered, metadata_by_name)
