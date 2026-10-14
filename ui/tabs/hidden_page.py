"""Authenticated Hidden Vault using the same gallery experience as View Images."""

from pathlib import Path

import httpx
import streamlit as st

from tabs.shared import LunaVaultUI
from tabs.view_page import ViewPage


class HiddenGallery(ViewPage):
    """View-style gallery with secure hidden-image actions."""

    def render_favorite_overlay(
        self,
        image_path: Path,
        favorite_names: set[str],
        generation: int,
        key_prefix: str,
    ) -> None:
        """Hidden images do not expose Favorite state."""
        del image_path, favorite_names, generation, key_prefix

    def render_image_menu(
        self, container, image_path: Path, generation: int, key_prefix: str
    ) -> None:
        """Render download, delete, and unhide inside the Hidden item menu."""
        with container.popover(":material/more_vert:", use_container_width=True):
            download_column, delete_column, unhide_column = st.columns(3, gap="small")
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
                st.session_state.pending_view_delete = image_path.name
                st.rerun()
            if unhide_column.button(
                ":material/visibility:",
                width="stretch",
                key=f"{key_prefix}_unhide_{generation}_{image_path.name}",
            ):
                response = httpx.post(
                    f"{self.config.api_url}/api/hidden/restore",
                    json={"names": [image_path.name]},
                    headers={
                        **self.config.api_headers,
                        "X-Hidden-Vault-Token": st.session_state.hidden_auth_token,
                    },
                    timeout=30.0,
                )
                response.raise_for_status()
                st.session_state.hidden_generation += 1
                st.session_state.view_generation += 1
                st.rerun()

    def delete_image(self, image_path: Path) -> None:
        """Permanently delete one authenticated hidden image."""
        response = httpx.post(
            f"{self.config.api_url}/api/hidden/delete",
            json={"names": [image_path.name]},
            headers={
                **self.config.api_headers,
                "X-Hidden-Vault-Token": st.session_state.hidden_auth_token,
            },
            timeout=30.0,
        )
        response.raise_for_status()
        st.session_state.pending_view_delete = None
        st.session_state.hidden_generation += 1
        st.session_state.view_generation += 1

    def update_image_metadata(
        self,
        image_path: Path,
        caption: str | None = None,
        add_tags: list[str] | None = None,
        remove_tags: list[str] | None = None,
    ) -> dict:
        """Persist authenticated hidden-image caption and tag changes."""
        payload = {}
        if caption is not None:
            payload["caption"] = caption
        if add_tags is not None:
            payload["add_tags"] = add_tags
        if remove_tags is not None:
            payload["remove_tags"] = remove_tags
        response = httpx.post(
            f"{self.config.api_url}/api/hidden/images/{image_path.name}/metadata",
            json=payload,
            headers={
                **self.config.api_headers,
                "X-Hidden-Vault-Token": st.session_state.hidden_auth_token,
            },
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()


class HiddenPage(LunaVaultUI):
    """Render authenticated hidden-image management without an Add Images tab."""

    def _post(self, route: str, payload: dict, authenticated: bool = False) -> dict:
        headers = self.config.api_headers.copy()
        if authenticated:
            headers["X-Hidden-Vault-Token"] = st.session_state.hidden_auth_token
        response = httpx.post(
            f"{self.config.api_url}{route}", json=payload, headers=headers, timeout=30.0
        )
        if response.status_code == 401 and authenticated:
            st.session_state.hidden_auth_token = None
        response.raise_for_status()
        return response.json()

    def _authenticate(self) -> bool:
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
            st.caption("Choose a password and an 8-digit reset PIN. Store the PIN safely.")
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
                        result = self._post("/api/hidden/setup", {"password": password, "pin": pin})
                        st.session_state.hidden_auth_token = result["token"]
                        st.rerun()
                    except httpx.HTTPStatusError as error:
                        st.error(error.response.json().get("error", "Could not create access."))
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
                        result = self._post("/api/hidden/reset", {"pin": pin, "new_password": new_password})
                        st.session_state.hidden_auth_token = result["token"]
                        st.rerun()
                    except httpx.HTTPStatusError as error:
                        st.error(error.response.json().get("error", "Password reset failed."))
        return False

    def render(
        self, visible_images: list[Path], metadata_by_name: dict[str, dict]
    ) -> None:
        """Render the secure Hidden gallery with View Images interactions."""
        del visible_images, metadata_by_name
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
        metadata = response.json()["images"]
        hidden_metadata = {item["name"]: item for item in metadata}
        hidden_images = [
            path for path in self.list_vault_images() if path.name in hidden_metadata
        ]
        query = (
            st.text_input(
                "Search hidden vault by image name",
                placeholder=self.gallery_search_placeholder(),
                key="hidden_name_search",
                icon=":material/search:",
                label_visibility="collapsed",
            )
            .strip()
            .casefold()
        )
        filtered = [
            path
            for path in hidden_images
            if query in self.display_name(path.name).casefold()
        ]
        if query and not filtered:
            st.info("No hidden image names match your search.")
            return
        HiddenGallery(self.config).render(filtered, hidden_metadata)