"""Visible-image gallery page for Luna Vault."""

from pathlib import Path

import httpx
import streamlit as st
from st_img_selector import st_img_selector

from tabs.shared import LunaVaultUI


class ViewPage(LunaVaultUI):
    """Render the searchable visible-image gallery and item actions."""

    def delete_image(self, image_path: Path) -> None:
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
        st.session_state.view_generation += 1
        st.session_state.download_generation += 1

    def render(
        self, vault_images: list[Path], metadata_by_name: dict[str, dict]
    ) -> None:
        if not vault_images:
            st.session_state.view_page = 0
            st.session_state.pending_view_delete = None
            st.info("No images are currently stored in Luna Vault.")
            return

        vault_names = {path.name for path in vault_images}
        if st.session_state.pending_view_delete not in vault_names:
            st.session_state.pending_view_delete = None
        generation = st.session_state.view_generation
        current_page, page_images = self.paginated_images(
            vault_images, "view_page", f"view_{generation}"
        )
        clicked_image = None

        for row_start in range(0, len(page_images), self.config.gallery_columns):
            row_images = page_images[
                row_start : row_start + self.config.gallery_columns
            ]
            thumbnails = [self.create_gallery_thumbnail(path) for path in row_images]
            clicked_indices = (
                st_img_selector(
                    images=thumbnails,
                    value=[],
                    corner_radius=self.config.gallery_corner_radius,
                    selection_color=self.config.gallery_selection_color,
                    img_per_row=self.config.gallery_columns,
                    border_thickness=self.config.gallery_border_thickness,
                    max_row_height=self.config.gallery_max_row_height,
                    key=f"view_selector_{generation}_{current_page}_{row_start}",
                )
                or []
            )

            columns = st.columns(self.config.gallery_columns)
            for column, image_path in zip(columns, row_images):
                self.render_image_name(column, image_path.name)
                metadata = metadata_by_name.get(image_path.name)
                if metadata:
                    with column.expander("Caption & tags", expanded=False):
                        st.write(metadata["caption"])
                        st.caption("  ".join(f"#{tag}" for tag in metadata["tags"]))
                download_column, delete_column = column.columns(2)
                download_column.download_button(
                    ":material/download:",
                    data=image_path.read_bytes(),
                    file_name=self.display_name(image_path.name),
                    mime=f"image/{image_path.suffix.lower().lstrip('.')}",
                    help="Download image",
                    width="stretch",
                    key=f"view_download_{generation}_{image_path.name}",
                )
                if delete_column.button(
                    ":material/delete:",
                    help="Delete image",
                    width="stretch",
                    key=f"view_delete_{generation}_{image_path.name}",
                ):
                    st.session_state.pending_view_delete = image_path.name
                    st.rerun()

            if clicked_indices and clicked_image is None:
                index = clicked_indices[-1]
                if 0 <= index < len(row_images):
                    clicked_image = row_images[index]

        pending_name = st.session_state.pending_view_delete
        if pending_name:
            st.warning(
                f"Delete {self.display_name(pending_name)}? This cannot be undone."
            )
            confirm_column, cancel_column = st.columns(2)
            if confirm_column.button(
                "Confirm deletion",
                type="primary",
                width="stretch",
                key="confirm_view_delete",
            ):
                self.delete_image(self.image_dir / pending_name)
                st.rerun()
            if cancel_column.button(
                "Cancel", width="stretch", key="cancel_view_delete"
            ):
                st.session_state.pending_view_delete = None
                st.rerun()

        if clicked_image is not None:
            st.session_state.view_generation += 1

            @st.dialog(self.display_name(clicked_image.name), width="large")
            def show_full_size_image() -> None:
                st.image(clicked_image, width="stretch")

            show_full_size_image()


# ---------------- View Images Page ----------------
class ViewImagesPage(LunaVaultUI):
    """Coordinate metadata search with the visible gallery."""

    def render(
        self, vault_images: list[Path], metadata_by_name: dict[str, dict]
    ) -> None:
        search_column, clear_column = st.columns([6, 1], vertical_alignment="bottom")
        query = (
            search_column.text_input(
                "Search by image name",
                placeholder="Type part of a filename",
                key="view_name_search",
                icon=":material/search:",
            )
            .strip()
            .casefold()
        )
        clear_column.button(
            ":material/close:",
            key="clear_view_name_search",
            help="Clear search",
            on_click=self.clear_search,
            args=("view_name_search",),
            width="stretch",
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
