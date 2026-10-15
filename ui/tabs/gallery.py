"""Reusable selectable gallery structure for Luna Visia collection tabs."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import streamlit as st
from st_img_selector import st_img_selector

from tabs.shared import LunaVisiaUI

ItemActions = Callable[[Any, Path, int, int], None]


class SelectableGallery(LunaVisiaUI):
    """Render paginated image selection shared by collection workflows."""

    def render_collection_search(self, label: str, state_key: str) -> str:
        """Render a collection search field with a matching clear action."""
        search_column, clear_column = st.columns([33, 7], vertical_alignment="bottom")
        query = (
            search_column.text_input(
                label,
                placeholder=self.gallery_search_placeholder(),
                key=state_key,
                icon=":material/search:",
            )
            .strip()
            .casefold()
        )
        clear_column.button(
            ":material/close:",
            key=f"clear_{state_key}",
            help="Clear search",
            on_click=self.clear_search,
            args=(state_key,),
            width="stretch",
        )
        return query

    def render_selection_grid(
        self,
        images: list[Path],
        page: int,
        generation: int,
        selection_key: str,
        key_prefix: str,
        item_actions: ItemActions | None = None,
    ) -> None:
        """Render selectable thumbnails, filenames, and optional per-item actions."""
        if st.session_state.gallery_view_mode == "list":
            for image_path in images:
                with st.container(border=True):
                    thumbnail_column, detail_column = st.columns(
                        [1, 3], vertical_alignment="center"
                    )
                    thumbnail_column.image(
                        self.create_gallery_thumbnail(image_path), width="stretch"
                    )
                    selected = detail_column.checkbox(
                        self.display_name(image_path.name),
                        value=image_path.name in st.session_state[selection_key],
                        key=(
                            f"{key_prefix}_list_{generation}_{page}_"
                            f"{image_path.name}"
                        ),
                    )
                    if selected:
                        st.session_state[selection_key].add(image_path.name)
                    else:
                        st.session_state[selection_key].discard(image_path.name)
                    if item_actions:
                        item_actions(
                            detail_column, image_path, generation, page
                        )
            return

        columns = self.gallery_column_count()
        for row_start in range(0, len(images), columns):
            row_images = images[row_start : row_start + columns]
            row_names = {path.name for path in row_images}
            selected_indices = [
                index
                for index, path in enumerate(row_images)
                if path.name in st.session_state[selection_key]
            ]
            selected = (
                st_img_selector(
                    images=[self.create_gallery_thumbnail(path) for path in row_images],
                    value=selected_indices,
                    corner_radius=self.config.gallery_corner_radius,
                    selection_color=self.config.gallery_selection_color,
                    img_per_row=columns,
                    border_thickness=self.config.gallery_border_thickness,
                    max_row_height=self.config.gallery_max_row_height,
                    key=f"{key_prefix}_{generation}_{page}_{row_start}",
                )
                or []
            )
            st.session_state[selection_key].difference_update(row_names)
            st.session_state[selection_key].update(
                row_images[index].name
                for index in selected
                if 0 <= index < len(row_images)
            )
            self.render_filename_row(row_images, columns=columns)

            if item_actions:
                action_columns = st.columns(columns)
                for column, image_path in zip(action_columns, row_images):
                    item_actions(column, image_path, generation, page)

    def render_selectable_collection(
        self,
        images: list[Path],
        empty_message: str,
        page_key: str,
        selection_key: str,
        generation_key: str,
        key_prefix: str,
        item_actions: ItemActions | None = None,
    ) -> bool:
        """Render a complete selectable collection and return whether it has items."""
        valid_names = {path.name for path in images}
        st.session_state[selection_key].intersection_update(valid_names)
        if not images:
            st.session_state[page_key] = 0
            st.info(empty_message)
            return False
        generation = st.session_state[generation_key]
        page, page_images = self.paginated_images(
            images, page_key, f"{key_prefix}_{generation}"
        )
        self.render_gallery_transition_marker(page_key)
        self.render_selection_grid(
            page_images,
            page,
            generation,
            selection_key,
            key_prefix,
            item_actions,
        )
        self.render_gallery_footer(images, page_key, f"{key_prefix}_{generation}")
        self.finish_gallery_transition(page_key)
        return True
