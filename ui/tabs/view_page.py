"""Visible-image gallery page for Luna Visia."""

import html
from pathlib import Path

import httpx
import streamlit as st
from st_img_selector import st_img_selector

from config import UIConfig
from tabs.shared import LunaVisiaUI


class ViewPage(LunaVisiaUI):
    """Render the searchable visible-image gallery and item actions."""

    def delete_image(self, image_path: Path) -> None:
        """Delete one visible image through the normal vault lifecycle."""
        self.api.delete_image(image_path.name)
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

    def set_favorite(self, image_path: Path, favorite: bool) -> None:
        """Persist one image's favorite state."""
        self.api.set_favorites([image_path.name], favorite)
        st.session_state.favorite_generation += 1
        st.session_state.add_favorite_generation += 1
        st.session_state.view_generation += 1

    def update_image_metadata(
        self,
        image_path: Path,
        caption: str | None = None,
        add_tags: list[str] | None = None,
        remove_tags: list[str] | None = None,
    ) -> dict:
        """Persist an edited caption or tag changes for one visible image."""
        payload = {}
        if caption is not None:
            payload["caption"] = caption
        if add_tags is not None:
            payload["add_tags"] = add_tags
        if remove_tags is not None:
            payload["remove_tags"] = remove_tags
        return self.api.update_image_metadata(image_path.name, payload)

    @st.fragment
    def render_favorite_overlay(
        self,
        image_path: Path,
        favorite_names: set[str],
        generation: int,
        key_prefix: str,
    ) -> None:
        """Overlay the Favorite toggle at the thumbnail's top-right corner."""
        st.markdown('<span class="lv-thumbnail-shell"></span>', unsafe_allow_html=True)
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
        size, width, height = UIConfig.image_file_facts(
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
            f"<span>·</span><span>{width} × {height}</span></div>",
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
                                f"{image_path.name}_"
                                f"{st.session_state.view_selector_generations.get(image_path.name, 0)}"
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
                self.render_image_menu(menu_column, image_path, generation, "view_list")
                metadata = metadata_by_name.get(image_path.name)
                self.render_image_details(detail_column, image_path, metadata)
                if clicked_indices:
                    opened_image = image_path
        return opened_image

    def render(
        self, vault_images: list[Path], metadata_by_name: dict[str, dict]
    ) -> None:
        """Render the view page interface."""

        if not vault_images:
            st.session_state.view_page = 0
            st.session_state.pending_view_delete = None
            st.info("No images are currently stored in Luna Visia.")
            return

        vault_names = {path.name for path in vault_images}
        if st.session_state.pending_view_delete not in vault_names:
            st.session_state.pending_view_delete = None
        if st.session_state.pending_view_hide not in vault_names:
            st.session_state.pending_view_hide = None
        favorite_names = {item["name"] for item in self.api.favorites()}
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
            for item_index, (column, image_path) in enumerate(zip(columns, row_images)):
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
                                f"{row_start}_{item_index}_"
                                f"{st.session_state.view_selector_generations.get(image_path.name, 0)}"
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
                self.render_image_menu(menu_column, image_path, generation, "view_grid")
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
                        self.api.hide_images(
                            [name], st.session_state.hidden_auth_token
                        )
                        st.session_state.pending_view_hide = None
                        st.session_state.view_generation += 1
                        st.session_state.hidden_generation += 1
                        st.rerun()
                    except httpx.HTTPError as error:
                        st.error(f"Could not hide the image: {error}")

            confirm_view_hide()
        if clicked_image is not None:
            selector_generations = dict(st.session_state.view_selector_generations)
            selector_generations[clicked_image.name] = (
                selector_generations.get(clicked_image.name, 0) + 1
            )
            st.session_state.view_selector_generations = selector_generations

            @st.dialog(self.display_name(clicked_image.name), width="large")
            def show_full_size_image() -> None:
                """Render the selected image with its stored descriptive metadata."""
                st.image(self.create_full_preview(clicked_image), width="stretch")
                metadata = metadata_by_name.get(clicked_image.name) or {}
                caption_value = str(metadata.get("caption") or "")
                tags = list(metadata.get("tags") or [])
                caption_state = f"preview_caption_edit_{clicked_image.name}"
                tag_state = f"preview_tag_add_{clicked_image.name}"
                caption_error_state = f"{caption_state}_error"
                tag_error_state = f"{tag_state}_error"
                tag_pills_generation_state = (
                    f"preview_tag_pills_generation_{clicked_image.name}"
                )
                if tag_pills_generation_state not in st.session_state:
                    st.session_state[tag_pills_generation_state] = 0
                tag_selection_key = (
                    f"preview_tag_pills_{clicked_image.name}_"
                    f"{st.session_state[tag_pills_generation_state]}"
                )

                def save_caption_inline() -> None:
                    """Save the inline caption field from Enter or the checkmark."""
                    try:
                        updated = self.update_image_metadata(
                            clicked_image,
                            caption=st.session_state.get(f"{caption_state}_draft", ""),
                        )
                        metadata_by_name[clicked_image.name] = updated
                        st.session_state[caption_state] = False
                        st.session_state[caption_error_state] = None
                    except httpx.HTTPError as error:
                        st.session_state[caption_error_state] = (
                            f"Could not update description: {error}"
                        )

                def save_tag_inline() -> None:
                    """Save the inline tag field from Enter or the checkmark."""
                    new_tag = st.session_state.get(f"{tag_state}_draft", "").strip()
                    if not new_tag:
                        st.toast("Enter a tag name before adding it.", icon=":material/info:")
                        st.session_state[tag_error_state] = None
                        return
                    normalized_tag = " ".join(new_tag.casefold().split())
                    normalized_tags = {" ".join(tag.casefold().split()) for tag in tags}
                    if normalized_tag in normalized_tags:
                        st.toast("That tag is already on this image.", icon=":material/info:")
                        st.session_state[tag_error_state] = None
                        return
                    if len(tags) >= UIConfig.MAX_TAGS:
                        st.toast(
                            f"Maximum of {UIConfig.MAX_TAGS} tags reached. "
                            "Remove a tag before adding another.",
                            icon=":material/info:",
                        )
                        st.session_state[tag_error_state] = None
                        return
                    try:
                        updated = self.update_image_metadata(
                            clicked_image, add_tags=[new_tag]
                        )
                        metadata_by_name[clicked_image.name] = updated
                        st.session_state[tag_state] = False
                        st.session_state[tag_error_state] = None
                        st.session_state[tag_pills_generation_state] += 1
                    except httpx.HTTPError:
                        st.toast(
                            "The tag could not be saved. Please try again.",
                            icon=":material/info:",
                        )
                        st.session_state[tag_error_state] = None

                def remove_deselected_tags() -> None:
                    """Remove tags deselected from the interactive tag pills."""
                    selected_tags = st.session_state.get(tag_selection_key) or []
                    removed_tags = [tag for tag in tags if tag not in selected_tags]
                    if not removed_tags:
                        return
                    try:
                        updated = self.update_image_metadata(
                            clicked_image,
                            remove_tags=removed_tags,
                        )
                        metadata_by_name[clicked_image.name] = updated
                        st.session_state[tag_error_state] = None
                    except httpx.HTTPError as error:
                        st.session_state[tag_error_state] = (
                            f"Could not remove tag: {error}"
                        )
                    finally:
                        st.session_state[tag_pills_generation_state] += 1

                caption_box = st.container()
                caption_box.markdown(
                    '<span class="lv-preview-details"></span>',
                    unsafe_allow_html=True,
                )
                caption_icon, caption_column, edit_column = caption_box.columns(
                    [0.6, 18.4, 1], vertical_alignment="center"
                )
                caption_icon.markdown(
                    '<span class="lv-preview-static-icon"></span>',
                    unsafe_allow_html=True,
                )
                if st.session_state.get(caption_state, False):
                    caption_column.text_input(
                        "Description",
                        key=f"{caption_state}_draft",
                        max_chars=500,
                        label_visibility="collapsed",
                        on_change=save_caption_inline,
                    )
                    edit_column.button(
                        ":material/check:",
                        key=f"save_{caption_state}",
                        width="stretch",
                        on_click=save_caption_inline,
                    )
                    if st.session_state.get(caption_error_state):
                        caption_box.error(st.session_state[caption_error_state])
                else:
                    caption_column.markdown(
                        f'<div class="lv-preview-caption">{html.escape(caption_value)}</div>',
                        unsafe_allow_html=True,
                    )
                    if edit_column.button(
                        ":material/edit:",
                        key=f"open_{caption_state}",
                        width="stretch",
                    ):
                        st.session_state[caption_state] = True
                        st.session_state[f"{caption_state}_draft"] = caption_value
                        st.rerun(scope="fragment")

                tags_box = st.container()
                tags_box.markdown(
                    '<span class="lv-preview-details"></span>',
                    unsafe_allow_html=True,
                )
                tags_icon, tags_title = tags_box.columns(
                    [0.6, 20.4], vertical_alignment="center"
                )
                tags_icon.markdown(
                    '<span class="lv-preview-static-icon"></span>',
                    unsafe_allow_html=True,
                )
                tags_icon.button(
                    ":material/style:",
                    disabled=True,
                    key=f"tags_icon_{clicked_image.name}",
                    width="stretch",
                )

                if st.session_state.get(tag_state, False):
                    tags_column, input_column, add_tag_column = tags_box.columns(
                        [12, 7, 1], vertical_alignment="center"
                    )
                    if tags:
                        tags_column.markdown(
                            '<span class="lv-preview-removable-tags"></span>',
                            unsafe_allow_html=True,
                        )
                        tags_column.pills(
                            "Tags",
                            options=tags,
                            default=tags,
                            selection_mode="multi",
                            key=tag_selection_key,
                            on_change=remove_deselected_tags,
                            label_visibility="collapsed",
                            width="stretch",
                        )
                    input_column.text_input(
                        "New tag",
                        key=f"{tag_state}_draft",
                        placeholder="Tag name",
                        label_visibility="collapsed",
                        on_change=save_tag_inline,
                    )
                    add_tag_column.markdown(
                        '<span class="lv-preview-icon-action"></span>',
                        unsafe_allow_html=True,
                    )
                    add_tag_column.button(
                        ":material/check:",
                        key=f"save_{tag_state}",
                        width="stretch",
                        on_click=save_tag_inline,
                    )
                    if st.session_state.get(tag_error_state):
                        tags_box.error(st.session_state[tag_error_state])
                else:
                    tags_column, add_tag_column = tags_box.columns(
                        [20, 1], vertical_alignment="center"
                    )
                    if tags:
                        tags_column.markdown(
                            '<span class="lv-preview-removable-tags"></span>',
                            unsafe_allow_html=True,
                        )
                        tags_column.pills(
                            "Tags",
                            options=tags,
                            default=tags,
                            selection_mode="multi",
                            key=tag_selection_key,
                            on_change=remove_deselected_tags,
                            label_visibility="collapsed",
                            width="stretch",
                        )
                    add_tag_column.markdown(
                        '<span class="lv-preview-icon-action"></span>',
                        unsafe_allow_html=True,
                    )
                    if add_tag_column.button(
                        ":material/add:",
                        key=f"open_{tag_state}",
                        width="stretch",
                    ):
                        st.session_state[tag_state] = True
                        st.session_state[f"{tag_state}_draft"] = ""
                        st.rerun(scope="fragment")

            show_full_size_image()


# ---------------- View Images Page ----------------
class ViewImagesPage(LunaVisiaUI):
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
            if self.image_matches_search(path, metadata_by_name, query)
        ]
        if query and not filtered:
            st.info("No filenames or tags match your search.")
            return
        ViewPage(self.config).render(filtered, metadata_by_name)
