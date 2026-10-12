"""Hidden-vault page for Luna Vault."""

from pathlib import Path

import httpx
import streamlit as st
from tabs.gallery import SelectableGallery


class HiddenPage(SelectableGallery):
    """Render authenticated hidden-image management workflows."""

    def _render_hidden_actions(
        self, column, image_path: Path, generation: int, page: int
    ) -> None:
        """Render item actions available inside the authenticated vault."""
        view_column, download_column, delete_column = column.columns(3)
        if view_column.button(
            ":material/fullscreen:",
            help="View full image",
            width="stretch",
            key=f"hidden_full_{generation}_{page}_{image_path.name}",
        ):

            @st.dialog(self.display_name(image_path.name), width="large")
            def show_hidden_full_image(path: Path = image_path) -> None:
                """Render the selected image at full size."""
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

    def _post(self, route: str, payload: dict, authenticated: bool = False) -> dict:
        headers = self.config.api_headers.copy()

        if authenticated:
            headers["X-Hidden-Vault-Token"] = st.session_state.hidden_auth_token

        response = httpx.post(
            f"{self.config.api_url}{route}",
            json=payload,
            headers=headers,
            timeout=30.0,
        )

        if response.status_code == 401 and authenticated:
            st.session_state.hidden_auth_token = None

        response.raise_for_status()
        return response.json()

    def _authenticate(self) -> bool:
        """Render setup or login controls and report whether the vault is unlocked."""
        status = httpx.get(
            f"{self.config.api_url}/api/hidden/status",
            headers=self.config.api_headers,
            timeout=10.0,
        )
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
        """Move the selected images into or out of the Hidden Vault."""
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
        """Render one selectable collection and its bulk action."""
        valid_names = {path.name for path in images}
        if st.session_state.pending_hidden_delete not in valid_names:
            st.session_state.pending_hidden_delete = None
        rendered = self.render_selectable_collection(
            images,
            empty_message,
            page_key,
            selection_key,
            generation_key,
            prefix,
            self._render_hidden_actions if allow_hidden_actions else None,
        )
        if not rendered:
            return

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
        """Render the hidden page interface."""
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
                    **self.config.api_headers,
                    "X-Hidden-Vault-Token": st.session_state.hidden_auth_token,
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
        hidden_tab, add_tab = st.tabs(
            [":material/lock: Hidden images", ":material/add: Add images"]
        )
        with hidden_tab:
            query = self.render_collection_search(
                "Search hidden vault by image name", "hidden_name_search"
            )
            filtered_hidden = [
                path
                for path in hidden_images
                if query in self.display_name(path.name).casefold()
            ]
            self._render_collection(
                filtered_hidden,
                (
                    "No hidden images match this search."
                    if query
                    else "No images are hidden."
                ),
                "hidden_page",
                "hidden_selection",
                "hidden_generation",
                "hidden",
                "Restore selected",
                "/api/hidden/restore",
                True,
            )

        with add_tab:
            query = self.render_collection_search(
                "Search images to hide by name", "hide_name_search"
            )
            filtered_visible = [
                path
                for path in visible_images
                if query in self.display_name(path.name).casefold()
            ]
            self._render_collection(
                filtered_visible,
                (
                    "No visible images match this search."
                    if query
                    else "No visible images are available."
                ),
                "hide_page",
                "hide_selection",
                "hide_generation",
                "hide",
                "Hide selected",
                "/api/hidden/hide",
            )
