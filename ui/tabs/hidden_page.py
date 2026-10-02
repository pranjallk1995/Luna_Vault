"""Hidden-vault page for Luna Vault."""

from pathlib import Path

import httpx
import streamlit as st
from st_img_selector import st_img_selector

from tabs.shared import LunaVaultUI


class GallerySelectionControls(LunaVaultUI):
    """Provide reusable image-selection controls for active pages."""

    def _selection_gallery(
        self,
        images: list[Path],
        page: int,
        generation: int,
        state_key: str,
        key_prefix: str,
        allow_hidden_actions: bool = False,
    ) -> None:
        for row_start in range(0, len(images), self.config.gallery_columns):
            row_images = images[row_start : row_start + self.config.gallery_columns]
            row_names = {path.name for path in row_images}
            selected_indices = [
                index
                for index, path in enumerate(row_images)
                if path.name in st.session_state[state_key]
            ]
            values = (
                st_img_selector(
                    images=[self.create_gallery_thumbnail(path) for path in row_images],
                    value=selected_indices,
                    corner_radius=self.config.gallery_corner_radius,
                    selection_color=self.config.gallery_selection_color,
                    img_per_row=self.config.gallery_columns,
                    border_thickness=self.config.gallery_border_thickness,
                    max_row_height=self.config.gallery_max_row_height,
                    key=f"{key_prefix}_{generation}_{page}_{row_start}",
                )
                or []
            )
            st.session_state[state_key].difference_update(row_names)
            st.session_state[state_key].update(
                row_images[index].name
                for index in values
                if 0 <= index < len(row_images)
            )
            self.render_filename_row(row_images)

            if allow_hidden_actions:
                action_columns = st.columns(self.config.gallery_columns)
                for column, image_path in zip(action_columns, row_images):
                    view_column, download_column, delete_column = column.columns(3)
                    if view_column.button(
                        ":material/fullscreen:",
                        help="View full image",
                        width="stretch",
                        key=f"hidden_full_{generation}_{page}_{image_path.name}",
                    ):

                        @st.dialog(self.display_name(image_path.name), width="large")
                        def show_hidden_full_image(path: Path = image_path) -> None:
                            st.image(path, width="stretch")

                        show_hidden_full_image()
                    download_column.download_button(
                        ":material/download:",
                        data=image_path.read_bytes(),
                        file_name=self.display_name(image_path.name),
                        mime=f"image/{image_path.suffix.lower().lstrip('.')}",
                        help="Download image",
                        width="stretch",
                        key=f"hidden_download_{generation}_{page}_{image_path.name}",
                    )
                    if delete_column.button(
                        ":material/delete:",
                        help="Delete hidden image",
                        width="stretch",
                        key=f"hidden_delete_{generation}_{page}_{image_path.name}",
                    ):
                        st.session_state.pending_hidden_delete = image_path.name
                        st.rerun()


# ---------------- Hidden Page ----------------
class HiddenPage(GallerySelectionControls):
    """Render authenticated hidden-image management workflows."""

    def _post(self, route: str, payload: dict, authenticated: bool = False) -> dict:
        headers = {}
        if authenticated:
            headers["Authorization"] = f"Bearer {st.session_state.hidden_auth_token}"
        response = httpx.post(
            f"{self.config.api_url}{route}", json=payload, headers=headers, timeout=30.0
        )
        if response.status_code == 401:
            st.session_state.hidden_auth_token = None
        response.raise_for_status()
        return response.json()

    def _authenticate(self) -> bool:
        status = httpx.get(f"{self.config.api_url}/api/hidden/status", timeout=10.0)
        status.raise_for_status()
        configured = status.json()["configured"]
        if st.session_state.hidden_auth_token:
            return True

        if not configured:
            st.subheader("Create hidden-vault access")
            st.caption(
                "Choose a password and an 8-digit reset PIN. Store the PIN safely."
            )
            with st.form("hidden_setup"):
                password = st.text_input("Create password", type="password")
                confirm = st.text_input("Confirm password", type="password")
                pin = st.text_input("Create reset PIN", type="password", max_chars=8)
                submitted = st.form_submit_button("Create and unlock", width="stretch")
            if submitted:
                if password != confirm:
                    st.error("Passwords do not match.")
                else:
                    try:
                        result = self._post(
                            "/api/hidden/setup", {"password": password, "pin": pin}
                        )
                        st.session_state.hidden_auth_token = result["token"]
                        st.rerun()
                    except httpx.HTTPStatusError as error:
                        st.error(
                            error.response.json().get(
                                "error", "Could not create access."
                            )
                        )
            return False

        st.subheader("Unlock hidden images")
        with st.form("hidden_login"):
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Unlock", width="stretch")
        if submitted:
            try:
                result = self._post("/api/hidden/login", {"password": password})
                st.session_state.hidden_auth_token = result["token"]
                st.rerun()
            except httpx.HTTPStatusError:
                st.error("Incorrect password.")

        with st.expander("Reset password"):
            with st.form("hidden_reset"):
                pin = st.text_input("8-digit reset PIN", type="password", max_chars=8)
                new_password = st.text_input("New password", type="password")
                confirm = st.text_input("Confirm new password", type="password")
                reset = st.form_submit_button("Reset and unlock", width="stretch")
            if reset:
                if new_password != confirm:
                    st.error("Passwords do not match.")
                else:
                    try:
                        result = self._post(
                            "/api/hidden/reset",
                            {"pin": pin, "new_password": new_password},
                        )
                        st.session_state.hidden_auth_token = result["token"]
                        st.rerun()
                    except httpx.HTTPStatusError as error:
                        st.error(
                            error.response.json().get("error", "Password reset failed.")
                        )
        return False

    def _move_selected(self, route: str, state_key: str) -> None:
        names = sorted(st.session_state[state_key])
        self._post(route, {"names": names}, authenticated=True)
        st.session_state[state_key] = set()
        st.session_state.hidden_generation += 1
        st.session_state.hide_generation += 1
        st.session_state.view_generation += 1
        st.session_state.gallery_generation += 1
        st.rerun()

    def _render_collection(
        self,
        images: list[Path],
        empty_message: str,
        page_key: str,
        selection_key: str,
        generation_key: str,
        prefix: str,
        action_label: str,
        route: str,
        allow_hidden_actions: bool = False,
    ) -> None:
        valid_names = {path.name for path in images}
        st.session_state[selection_key].intersection_update(valid_names)
        if st.session_state.pending_hidden_delete not in valid_names:
            st.session_state.pending_hidden_delete = None
        if not images:
            st.session_state[page_key] = 0
            st.info(empty_message)
            return
        generation = st.session_state[generation_key]
        page, page_images = self.paginated_images(
            images, page_key, f"{prefix}_{generation}"
        )
        self._selection_gallery(
            page_images,
            page,
            generation,
            selection_key,
            prefix,
            allow_hidden_actions,
        )

        pending_name = st.session_state.pending_hidden_delete
        if allow_hidden_actions and pending_name:
            st.warning(
                f"Delete {self.display_name(pending_name)}? This cannot be undone."
            )
            confirm_column, cancel_column = st.columns(2)
            if confirm_column.button(
                "Confirm deletion",
                type="primary",
                width="stretch",
                key="confirm_hidden_delete",
            ):
                try:
                    self._post(
                        "/api/hidden/delete",
                        {"names": [pending_name]},
                        authenticated=True,
                    )
                    st.session_state.pending_hidden_delete = None
                    st.session_state[selection_key].discard(pending_name)
                    st.session_state.hidden_generation += 1
                    st.rerun()
                except httpx.HTTPStatusError as error:
                    st.error(error.response.json().get("error", "Deletion failed."))
            if cancel_column.button(
                "Cancel", width="stretch", key="cancel_hidden_delete"
            ):
                st.session_state.pending_hidden_delete = None
                st.rerun()
        elif st.button(
            action_label,
            disabled=not st.session_state[selection_key],
            width="stretch",
            key=f"{prefix}_action",
        ):
            try:
                self._move_selected(route, selection_key)
            except httpx.HTTPStatusError as error:
                st.error(error.response.json().get("error", "The action failed."))

    def render(self, visible_images: list[Path]) -> None:
        if not self._authenticate():
            return
        header, logout_column = st.columns([3, 1])
        header.success("Hidden vault unlocked")
        if logout_column.button("Lock", icon=":material/lock:", width="stretch"):
            try:
                self._post("/api/hidden/logout", {}, authenticated=True)
            finally:
                st.session_state.hidden_auth_token = None
                st.rerun()

        try:
            response = httpx.get(
                f"{self.config.api_url}/api/hidden/images",
                headers={
                    "Authorization": f"Bearer {st.session_state.hidden_auth_token}"
                },
                timeout=10.0,
            )
            if response.status_code == 401:
                st.session_state.hidden_auth_token = None
                st.rerun()
            response.raise_for_status()
        except httpx.HTTPStatusError:
            st.error("Hidden-vault session expired. Please unlock it again.")
            return

        hidden_names = {item["name"] for item in response.json()["images"]}
        hidden_images = [
            path for path in self.list_vault_images() if path.name in hidden_names
        ]
        mode = st.segmented_control(
            "Hidden image action",
            ["Hidden images", "Add images"],
            default="Hidden images",
            label_visibility="collapsed",
            key="hidden_action_mode",
            width="stretch",
        )
        search_column, clear_column = st.columns([6, 1], vertical_alignment="bottom")
        query = (
            search_column.text_input(
                "Search hidden vault by image name",
                placeholder="Type part of a filename",
                key="hidden_name_search",
                icon=":material/search:",
            )
            .strip()
            .casefold()
        )
        clear_column.button(
            ":material/close:",
            key="clear_hidden_name_search",
            help="Clear search",
            on_click=self.clear_search,
            args=("hidden_name_search",),
            width="stretch",
        )
        hidden_images = [
            path
            for path in hidden_images
            if query in self.display_name(path.name).casefold()
        ]
        visible_images = [
            path
            for path in visible_images
            if query in self.display_name(path.name).casefold()
        ]
        if mode == "Hidden images":
            self._render_collection(
                hidden_images,
                "No images are hidden.",
                "hidden_page",
                "hidden_selection",
                "hidden_generation",
                "hidden",
                "Restore selected",
                "/api/hidden/restore",
                True,
            )
        else:
            self._render_collection(
                visible_images,
                "No visible images are available.",
                "hide_page",
                "hide_selection",
                "hide_generation",
                "hide",
                "Hide selected",
                "/api/hidden/hide",
            )
