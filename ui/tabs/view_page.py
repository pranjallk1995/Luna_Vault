"""Visible-image gallery page for Luna Vault."""

import html
from pathlib import Path

import httpx
import streamlit as st
from PIL import Image
from st_img_selector import st_img_selector

from tabs.shared import LunaVaultUI


@st.cache_data(show_spinner=False, max_entries=256)
def image_file_facts(image_path: str, modified_ns: int) -> tuple[int, int, int]:
    """Return cached byte size and pixel dimensions for an image."""
    del modified_ns
    path = Path(image_path)
    with Image.open(path) as source:
        width, height = source.size
    return path.stat().st_size, width, height


class ViewPage(LunaVaultUI):
    """Render the searchable visible-image gallery and item actions."""

    def delete_image(self, image_path: Path) -> None:
        """Delete one visible image through the normal vault lifecycle."""
        response = httpx.delete(
            f"{self.config.api_url}/api/images/{image_path.name}", timeout=30.0
        )
        response.raise_for_status()
        retained_uploads = []
        for image in st.session_state.uploaded_images:
            if image["name"] == image_path.name:
                st.session_state.saved_uploads.discard(image["upload_id"])
            else:
                retained_uploads.append(image)
        st.session_state.uploaded_images = retained_uploads
        st.session_state.pending_view_delete = None
        st.session_state.view_delete_notice = (
            "success",
            f"Deleted {self.display_name(image_path.name)}.",
        )
        st.session_state.view_generation += 1
        st.session_state.download_generation += 1

    def set_favorite(self, image_path: Path, favorite: bool) -> None:
        """Persist one image's favorite state."""
        response = httpx.post(
            f"{self.config.api_url}/api/favorites",
            json={"names": [image_path.name], "favorite": favorite},
            headers=self.config.api_headers,
            timeout=30.0,
        )
        response.raise_for_status()
        st.session_state.favorite_generation += 1
        st.session_state.add_favorite_generation += 1
        st.session_state.view_generation += 1

    @st.fragment
    def render_favorite_overlay(
        self,
        image_path: Path,
        favorite_names: set[str],
        generation: int,
        key_prefix: str,
    ) -> None:
        """Overlay the Favorite toggle at the thumbnail's top-right corner."""
        st.markdown(
            '<span class="lv-thumbnail-shell"></span>', unsafe_allow_html=True
        )
        spacer_column, favorite_column = st.columns([6, 1])
        del spacer_column
        state_key = f"{key_prefix}_favorite_state_{image_path.name}"
        state_generation_key = f"{state_key}_generation"
        if st.session_state.get(state_generation_key) != generation:
            st.session_state[state_key] = image_path.name in favorite_names
            st.session_state[state_generation_key] = generation
        is_favorite = st.session_state[state_key]
        marker_class = (
            "lv-favorite-overlay lv-favorite-active"
            if is_favorite
            else "lv-favorite-overlay"
        )
        favorite_column.markdown(
            f'<span class="{marker_class}"></span>', unsafe_allow_html=True
        )
        if favorite_column.button(
            ":material/favorite_border:",
            type="primary" if is_favorite else "secondary",
            key=f"{key_prefix}_favorite_{generation}_{image_path.name}",
            width="stretch",
        ):
            try:
                new_state = not is_favorite
                self.set_favorite(image_path, new_state)
                st.session_state[state_key] = new_state
                st.rerun(scope="fragment")
            except httpx.HTTPError as error:
                st.error(f"Could not update Favorite status: {error}")

    def render_image_menu(
        self,
        container,
        image_path: Path,
        generation: int,
        key_prefix: str,
    ) -> None:
        """Render download, delete, and hide actions in a compact menu."""
        with container.popover(
            ":material/more_vert:",
            use_container_width=True,
        ):
            download_column, delete_column, hide_column = st.columns(3, gap="small")
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
            if hide_column.button(
                ":material/visibility_off:",
                width="stretch",
                key=f"{key_prefix}_hide_{generation}_{image_path.name}",
            ):
                st.session_state.pending_view_delete = None
                st.session_state.pending_view_hide = image_path.name
                st.rerun()
    def render_image_details(
        self, container, image_path: Path, metadata: dict | None
    ) -> None:
        """Render one clipped tag row followed by size and resolution."""
        tags = (metadata or {}).get("tags", [])
        tag_html = "".join(
            f'<span class="lv-tag lv-tag-{index % 6}">'
            f"{html.escape(str(tag))}</span>"
            for index, tag in enumerate(tags)
        )
        size, width, height = image_file_facts(
            str(image_path), image_path.stat().st_mtime_ns
        )
        if size >= 1024 * 1024:
            size_label = f"{size / (1024 * 1024):.1f} MB"
        elif size >= 1024:
            size_label = f"{size / 1024:.0f} KB"
        else:
            size_label = f"{size} B"
        container.markdown(
            f'<div class="lv-card-tags">{tag_html}</div>'
            f'<div class="lv-card-facts"><span>{size_label}</span>'
            f'<span>·</span><span>{width} × {height}</span></div>',
            unsafe_allow_html=True,
        )
    def render_list(
        self,
        images: list[Path],
        metadata_by_name: dict[str, dict],
        favorite_names: set[str],
        generation: int,
        current_page: int,
    ) -> Path | None:
        """Render compact image rows and return an image opened by the user."""
        opened_image = None
        for image_path in images:
            with st.container(border=True):
                thumbnail_column, detail_column = st.columns(
                    [1, 3], vertical_alignment="center"
                )
                with thumbnail_column:
                    clicked_indices = (
                        st_img_selector(
                            images=[self.create_gallery_thumbnail(image_path)],
                            value=[],
                            corner_radius=self.config.gallery_corner_radius,
                            selection_color=self.config.gallery_selection_color,
                            img_per_row=1,
                            border_thickness=self.config.gallery_border_thickness,
                            max_row_height=self.config.gallery_max_row_height,
                            key=(
                                f"view_list_selector_{generation}_{current_page}_"
                                f"{image_path.name}"
                            ),
                        )
                        or []
                    )
                with thumbnail_column:
                    self.render_favorite_overlay(
                        image_path,
                        favorite_names,
                        generation,
                        "view_list_thumb",
                    )

                name_column, menu_column = detail_column.columns(
                    [8, 1], vertical_alignment="center"
                )
                self.render_image_name(name_column, image_path.name)
                self.render_image_menu(
                    menu_column, image_path, generation, "view_list"
                )
                metadata = metadata_by_name.get(image_path.name)
                self.render_image_details(detail_column, image_path, metadata)
                if clicked_indices:
                    opened_image = image_path
        return opened_image
    def render(
        self, vault_images: list[Path], metadata_by_name: dict[str, dict]
    ) -> None:
        """Render the view page interface."""
        notice = st.session_state.view_delete_notice
        if notice:
            st.session_state.view_delete_notice = None
            level, message = notice
            getattr(st, level)(message)

        if not vault_images:
            st.session_state.view_page = 0
            st.session_state.pending_view_delete = None
            st.info("No images are currently stored in Luna Vault.")
            return

        vault_names = {path.name for path in vault_images}
        if st.session_state.pending_view_delete not in vault_names:
            st.session_state.pending_view_delete = None
        if st.session_state.pending_view_hide not in vault_names:
            st.session_state.pending_view_hide = None
        favorite_response = httpx.get(
            f"{self.config.api_url}/api/favorites",
            headers=self.config.api_headers,
            timeout=10.0,
        )
        favorite_response.raise_for_status()
        favorite_names = {
            item["name"] for item in favorite_response.json()["images"]
        }
        generation = st.session_state.view_generation
        columns_per_row = self.gallery_column_count()
        current_page, page_images = self.paginated_images(
            vault_images, "view_page", f"view_{generation}"
        )
        clicked_image = None
        self.render_gallery_transition_marker("view_page")
        if st.session_state.gallery_view_mode == "list":
            clicked_image = self.render_list(
                page_images, metadata_by_name, favorite_names, generation, current_page
            )
        for row_start in (
            []
            if st.session_state.gallery_view_mode == "list"
            else range(0, len(page_images), columns_per_row)
        ):
            row_images = page_images[row_start : row_start + columns_per_row]
            columns = st.columns(columns_per_row)
            for item_index, (column, image_path) in enumerate(
                zip(columns, row_images)
            ):
                with column:
                    clicked_indices = (
                        st_img_selector(
                            images=[self.create_gallery_thumbnail(image_path)],
                            value=[],
                            corner_radius=self.config.gallery_corner_radius,
                            selection_color=self.config.gallery_selection_color,
                            img_per_row=1,
                            border_thickness=self.config.gallery_border_thickness,
                            max_row_height=self.config.gallery_max_row_height,
                            key=(
                                f"view_selector_{generation}_{current_page}_"
                                f"{row_start}_{item_index}"
                            ),
                        )
                        or []
                    )

                with column:
                    self.render_favorite_overlay(
                        image_path,
                        favorite_names,
                        generation,
                        "view_grid_thumb",
                    )
                name_column, menu_column = column.columns(
                    [8, 1], vertical_alignment="center"
                )
                self.render_image_name(name_column, image_path.name)
                self.render_image_menu(
                    menu_column, image_path, generation, "view_grid"
                )
                metadata = metadata_by_name.get(image_path.name)
                self.render_image_details(column, image_path, metadata)
                if clicked_indices and clicked_image is None:
                    clicked_image = image_path
        self.render_gallery_footer(vault_images, "view_page", f"view_{generation}")
        self.finish_gallery_transition("view_page")

        pending_name = st.session_state.pending_view_delete
        if pending_name:

            @st.dialog("Delete image?", width="small")
            def confirm_view_deletion(name: str = pending_name) -> None:
                """Confirm destructive deletion in an immediately visible dialog."""
                st.write(f"Permanently delete **{self.display_name(name)}**? ")
                cancel_column, delete_column = st.columns(2)
                if cancel_column.button(
                    "Cancel", width="stretch", key="cancel_view_delete"
                ):
                    st.session_state.pending_view_delete = None
                    st.rerun()
                if delete_column.button(
                    "Delete",
                    icon=":material/delete:",
                    type="primary",
                    width="stretch",
                    key="confirm_view_delete",
                ):
                    try:
                        self.delete_image(self.image_dir / name)
                        st.rerun()
                    except httpx.HTTPError as error:
                        st.error(f"Could not delete the image: {error}")

            confirm_view_deletion()

        pending_hide_name = st.session_state.pending_view_hide
        if pending_hide_name:

            @st.dialog("Hide image?", width="small")
            def confirm_view_hide(name: str = pending_hide_name) -> None:
                """Confirm moving one visible image into the Hidden Vault."""
                st.write(f"Move **{self.display_name(name)}** to Hidden Images?")
                cancel_column, hide_column = st.columns(2)
                if cancel_column.button(
                    "Cancel", width="stretch", key="cancel_view_hide"
                ):
                    st.session_state.pending_view_hide = None
                    st.rerun()
                if hide_column.button(
                    "Hide",
                    icon=":material/visibility_off:",
                    type="primary",
                    width="stretch",
                    key="confirm_view_hide",
                ):
                    if not st.session_state.hidden_auth_token:
                        st.error("Unlock Hidden Images before hiding an image.")
                        return
                    try:
                        response = httpx.post(
                            f"{self.config.api_url}/api/hidden/hide",
                            json={"names": [name]},
                            headers={
                                **self.config.api_headers,
                                "X-Hidden-Vault-Token": (
                                    st.session_state.hidden_auth_token
                                ),
                            },
                            timeout=30.0,
                        )
                        response.raise_for_status()
                        st.session_state.pending_view_hide = None
                        st.session_state.view_generation += 1
                        st.session_state.hidden_generation += 1
                        st.rerun()
                    except httpx.HTTPError as error:
                        st.error(f"Could not hide the image: {error}")

            confirm_view_hide()
        if clicked_image is not None:
            st.session_state.view_generation += 1

            @st.dialog(self.display_name(clicked_image.name), width="large")
            def show_full_size_image() -> None:
                """Render the selected image at full size."""
                st.image(clicked_image, width="stretch")

            show_full_size_image()


# ---------------- View Images Page ----------------
class ViewImagesPage(LunaVaultUI):
    """Coordinate metadata search with the visible gallery."""

    def render(
        self, vault_images: list[Path], metadata_by_name: dict[str, dict]
    ) -> None:
        """Render the view page interface."""
        query = (
            st.text_input(
                "Search by image name",
                placeholder=self.gallery_search_placeholder(),
                key="view_name_search",
                icon=":material/search:",
                label_visibility="collapsed",
            )
            .strip()
            .casefold()
        )
        filtered = [
            path
            for path in vault_images
            if query in self.display_name(path.name).casefold()
        ]
        if query and not filtered:
            st.info("No image names match your search.")
            return
        ViewPage(self.config).render(filtered, metadata_by_name)
