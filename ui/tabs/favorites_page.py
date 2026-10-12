"""Favorites collection page for Luna Vault."""

from pathlib import Path

import httpx
import streamlit as st

from tabs.gallery import SelectableGallery


class FavoritesPage(SelectableGallery):
    """Render persisted favorites and the visible images available to add."""

    def _render_favorite_actions(
        self, column, image_path: Path, generation: int, page: int
    ) -> None:
        """Render full-view, download, and delete controls for a favorite image."""
        view_column, download_column, delete_column = column.columns(3)

        if view_column.button(
            ":material/fullscreen:",
            help="View full image",
            width="stretch",
            key=f"favorite_full_{generation}_{page}_{image_path.name}",
        ):

            @st.dialog(self.display_name(image_path.name), width="large")
            def show_favorite_full_image(path: Path = image_path) -> None:
                """Render the selected favorite image at full size."""
                st.image(path, width="stretch")

            show_favorite_full_image()

        download_column.download_button(
            ":material/download:",
            data=image_path.read_bytes(),
            file_name=self.display_name(image_path.name),
            mime=f"image/{image_path.suffix.lower().lstrip('.')}",
            help="Download image",
            width="stretch",
            key=f"favorite_download_{generation}_{page}_{image_path.name}",
        )

        if delete_column.button(
            ":material/delete:",
            help="Delete image",
            width="stretch",
            key=f"favorite_delete_{generation}_{page}_{image_path.name}",
        ):
            st.session_state.pending_favorite_delete = image_path.name

    def _delete_favorite(self, name: str) -> None:
        """Delete a favorite through the normal visible-image lifecycle."""
        response = httpx.delete(
            f"{self.config.api_url}/api/images/{name}",
            headers=self.config.api_headers,
            timeout=30.0,
        )
        response.raise_for_status()

        retained_uploads = []
        for image in st.session_state.uploaded_images:
            if image["name"] == name:
                st.session_state.saved_uploads.discard(image["upload_id"])
            else:
                retained_uploads.append(image)

        st.session_state.uploaded_images = retained_uploads
        st.session_state.favorite_selection.discard(name)
        st.session_state.pending_favorite_delete = None
        st.session_state.favorite_generation += 1
        st.session_state.view_generation += 1

    def _set_favorites(self, selection_key: str, favorite: bool) -> None:
        """Persist the selected images as favorites or remove them from Favorites."""
        names = sorted(st.session_state[selection_key])

        response = httpx.post(
            f"{self.config.api_url}/api/favorites",
            json={"names": names, "favorite": favorite},
            headers=self.config.api_headers,
            timeout=30.0,
        )
        response.raise_for_status()

        st.session_state[selection_key] = set()
        st.session_state.favorite_generation += 1
        st.session_state.add_favorite_generation += 1
        st.session_state.view_generation += 1
        st.rerun()

    def _render_collection(
        self,
        images: list[Path],
        empty_message: str,
        page_key: str,
        selection_key: str,
        generation_key: str,
        key_prefix: str,
        action_label: str,
        favorite: bool,
    ) -> None:
        """Render one selectable collection and its bulk action."""
        valid_names = {path.name for path in images}

        if st.session_state.pending_favorite_delete not in valid_names:
            st.session_state.pending_favorite_delete = None

        rendered = self.render_selectable_collection(
            images,
            empty_message,
            page_key,
            selection_key,
            generation_key,
            key_prefix,
            self._render_favorite_actions if not favorite else None,
        )

        if not rendered:
            return

        pending_name = st.session_state.pending_favorite_delete

        if not favorite and pending_name:
            st.warning(
                f"Delete {self.display_name(pending_name)}? This cannot be undone."
            )

            confirm_column, cancel_column = st.columns(2)

            if confirm_column.button(
                "Confirm deletion",
                type="primary",
                width="stretch",
                key="confirm_favorite_delete",
            ):
                try:
                    self._delete_favorite(pending_name)
                    st.rerun()
                except httpx.HTTPStatusError as error:
                    st.error(error.response.json().get("error", "Deletion failed."))

            if cancel_column.button(
                "Cancel",
                width="stretch",
                key="cancel_favorite_delete",
            ):
                st.session_state.pending_favorite_delete = None
                st.rerun()

            return

        if st.button(
            action_label,
            icon=":material/star:" if favorite else ":material/star_border:",
            disabled=not st.session_state[selection_key],
            type="secondary",
            width="stretch",
            key=f"{key_prefix}_action",
        ):
            try:
                self._set_favorites(selection_key, favorite)
            except httpx.HTTPStatusError as error:
                st.error(
                    error.response.json().get("error", "Could not update Favorites.")
                )

    def render(self, visible_images: list[Path]) -> None:
        """Render the favorites page interface."""
        response = httpx.get(
            f"{self.config.api_url}/api/favorites",
            headers=self.config.api_headers,
            timeout=10.0,
        )
        response.raise_for_status()

        favorite_names = {item["name"] for item in response.json()["images"]}

        favorite_images = [
            path for path in visible_images if path.name in favorite_names
        ]

        available_images = [
            path for path in visible_images if path.name not in favorite_names
        ]

        favorites_tab, add_tab = st.tabs(
            [":material/star: Favorite Images", ":material/add: Add images"]
        )

        with favorites_tab:
            query = self.render_collection_search(
                "Search Favorites by image name",
                "favorite_name_search",
            )

            filtered_images = [
                path
                for path in favorite_images
                if query in self.display_name(path.name).casefold()
            ]

            self._render_collection(
                filtered_images,
                (
                    "No favorite images match this search."
                    if query
                    else "No favorite images yet."
                ),
                "favorite_page",
                "favorite_selection",
                "favorite_generation",
                "favorite",
                "Remove selected",
                False,
            )

        with add_tab:
            query = self.render_collection_search(
                "Search images to add by name",
                "add_favorite_name_search",
            )

            filtered_images = [
                path
                for path in available_images
                if query in self.display_name(path.name).casefold()
            ]

            self._render_collection(
                filtered_images,
                (
                    "No available images match this search."
                    if query
                    else "Every visible image is already a favorite."
                ),
                "add_favorite_page",
                "add_favorite_selection",
                "add_favorite_generation",
                "add_favorite",
                "Add selected",
                True,
            )
