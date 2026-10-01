import base64
import html
import io
import zipfile
from pathlib import Path
from hashlib import sha256
from uuid import uuid4
import httpx
import streamlit as st
from PIL import Image, ImageOps
from st_img_selector import st_img_selector

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

    def render_gallery_navigation(
        self, page_count: int, state_key: str, key_prefix: str
    ) -> int:
        current_page = min(max(st.session_state[state_key], 0), page_count - 1)
        st.session_state[state_key] = current_page
        selector_key = f"{key_prefix}_page"

        previous_column, page_column, next_column = st.columns([1, 2, 1])
        if previous_column.button(
            ":material/arrow_back:",
            disabled=current_page == 0,
            width="stretch",
            key=f"{key_prefix}_previous",
        ):
            st.session_state[state_key] = current_page - 1
            st.session_state[selector_key] = current_page
            st.rerun()

        selected_page = page_column.selectbox(
            "Page",
            options=list(range(1, page_count + 1)),
            index=current_page,
            label_visibility="collapsed",
            key=selector_key,
        )
        if selected_page - 1 != current_page:
            st.session_state[state_key] = selected_page - 1
            st.rerun()

        if next_column.button(
            ":material/arrow_forward:",
            disabled=current_page == page_count - 1,
            width="stretch",
            key=f"{key_prefix}_next",
        ):
            st.session_state[state_key] = current_page + 1
            st.session_state[selector_key] = current_page + 2
            st.rerun()

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


# ---------------- Upload Page ----------------
class UploadPage(LunaVaultUI):
    def upload_images(self, uploads: list) -> None:
        pending = []
        for upload in uploads:
            content = upload.getbuffer()
            upload_id = sha256(content).hexdigest()
            if upload_id not in st.session_state.saved_uploads:
                pending.append((upload, upload_id, content))

        if not pending:
            return

        progress = st.progress(0.0, text="Preparing upload...")
        total_bytes = sum(len(content) for _, _, content in pending)
        written_bytes = 0

        try:
            for upload, upload_id, content in pending:
                safe_name = Path(upload.name).name
                stored_name = f"{uuid4().hex}_{safe_name}"
                progress.progress(
                    written_bytes / total_bytes if total_bytes else 0.0,
                    text=f"Analyzing {safe_name}",
                )
                response = httpx.post(
                    f"{self.config.api_url}/api/images",
                    json={
                        "name": stored_name,
                        "content_base64": base64.b64encode(content).decode("ascii"),
                    },
                    timeout=360.0,
                )
                response.raise_for_status()
                metadata = response.json()
                written_bytes += len(content)
                progress.progress(
                    written_bytes / total_bytes if total_bytes else 1.0,
                    text=f"Saved {safe_name}",
                )
                st.session_state.saved_uploads.add(upload_id)
                st.session_state.uploaded_images.append(
                    {"upload_id": upload_id, **metadata}
                )
        finally:
            progress.empty()

    @staticmethod
    def clear_ui_state() -> None:
        st.session_state.uploaded_images = []
        st.session_state.saved_uploads = set()
        st.session_state.uploader_key += 1

    def render(self) -> None:
        uploads = st.file_uploader(
            ":material/upload_file: Drag and drop image files",
            type=["png", "jpg", "jpeg", "gif", "webp"],
            accept_multiple_files=True,
            key=f"image_uploader_{st.session_state.uploader_key}",
        )
        if uploads:
            self.upload_images(uploads)

        for image in st.session_state.uploaded_images:
            with st.container(border=True):
                self.render_image_name(st, image["name"])
                st.write(image["caption"])
                st.caption("  ".join(f"#{tag}" for tag in image["tags"]))
        if st.session_state.uploaded_images and st.button(
            "Clear", icon=":material/refresh:", width="stretch"
        ):
            self.clear_ui_state()
            st.rerun()


# ---------------- View Page ----------------
class ViewPage(LunaVaultUI):
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
            row_images = page_images[row_start : row_start + self.config.gallery_columns]
            thumbnails = [self.create_gallery_thumbnail(path) for path in row_images]
            clicked_indices = st_img_selector(
                images=thumbnails,
                value=[],
                corner_radius=10,
                selection_color="#A78BFA",
                img_per_row=self.config.gallery_columns,
                border_thickness=4,
                max_row_height=240,
                key=f"view_selector_{generation}_{current_page}_{row_start}",
            ) or []

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
                "Confirm deletion", type="primary", width="stretch",
                key="confirm_view_delete"
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
    def render(
        self, vault_images: list[Path], metadata_by_name: dict[str, dict]
    ) -> None:
        search_column, clear_column = st.columns([6, 1], vertical_alignment="bottom")
        query = search_column.text_input(
            "Search by image name",
            placeholder="Type part of a filename",
            key="view_name_search",
            icon=":material/search:",
        ).strip().casefold()
        clear_column.button(
            ":material/close:",
            key="clear_view_name_search",
            help="Clear search",
            on_click=self.clear_search,
            args=("view_name_search",),
            width="stretch",
        )
        filtered = [
            path for path in vault_images
            if query in self.display_name(path.name).casefold()
        ]
        if query and not filtered:
            st.info("No image names match your search.")
            return
        ViewPage(self.config).render(filtered, metadata_by_name)
# ---------------- Delete Page ----------------
class DeletePage(LunaVaultUI):
    def delete_selected_images(self, stored_names: list[str]) -> None:
        image_root = self.image_dir.resolve()
        image_paths = []

        for stored_name in stored_names:
            image_path = (self.image_dir / stored_name).resolve()
            if image_path.parent != image_root:
                raise ValueError(
                    "Refusing to delete an image outside the vault directory."
                )
            image_paths.append(image_path)

        for image_path in image_paths:
            response = httpx.delete(
                f"{self.config.api_url}/api/images/{image_path.name}",
                timeout=30.0,
            )
            response.raise_for_status()

        deleted_names = set(stored_names)
        retained_uploads = []
        for image in st.session_state.uploaded_images:
            if image["name"] in deleted_names:
                st.session_state.saved_uploads.discard(image["upload_id"])
            else:
                retained_uploads.append(image)

        st.session_state.uploaded_images = retained_uploads
        st.session_state.pending_delete = []
        st.session_state.gallery_selection = set()
        st.session_state.gallery_generation += 1
        st.session_state.view_generation += 1

        remaining_pages = max(
            1,
            (len(self.list_vault_images()) + self.config.images_per_page - 1)
            // self.config.images_per_page,
        )
        st.session_state.gallery_page = min(
            st.session_state.gallery_page, remaining_pages - 1
        )
        st.session_state.view_page = min(
            st.session_state.view_page, remaining_pages - 1
        )

    def render(self, vault_images: list[Path]) -> None:
        if not vault_images:
            st.session_state.gallery_page = 0
            st.session_state.gallery_selection = set()
            st.info("No images are currently stored in Luna Vault.")
            return

        vault_names = {image_path.name for image_path in vault_images}
        st.session_state.gallery_selection.intersection_update(vault_names)
        st.session_state.pending_delete = [
            stored_name
            for stored_name in st.session_state.pending_delete
            if stored_name in vault_names
        ]

        generation = st.session_state.gallery_generation
        current_page, page_images = self.paginated_images(
            vault_images, "gallery_page", f"delete_{generation}"
        )

        for row_start in range(0, len(page_images), self.config.gallery_columns):
            row_images = page_images[
                row_start : row_start + self.config.gallery_columns
            ]
            row_names = {image_path.name for image_path in row_images}
            selected_indices = [
                index
                for index, image_path in enumerate(row_images)
                if image_path.name in st.session_state.gallery_selection
            ]
            thumbnails = [
                self.create_gallery_thumbnail(image_path) for image_path in row_images
            ]
            selected_indices = (
                st_img_selector(
                    images=thumbnails,
                    value=selected_indices,
                    corner_radius=10,
                    selection_color="#A78BFA",
                    img_per_row=self.config.gallery_columns,
                    border_thickness=4,
                    max_row_height=240,
                    key=f"delete_selector_{generation}_{current_page}_{row_start}",
                )
                or []
            )

            st.session_state.gallery_selection.difference_update(row_names)
            st.session_state.gallery_selection.update(
                row_images[index].name
                for index in selected_indices
                if 0 <= index < len(row_images)
            )
            self.render_filename_row(row_images)

        if st.session_state.pending_delete:
            pending_count = len(st.session_state.pending_delete)
            st.warning(
                f"Delete {pending_count} selected "
                f"{'image' if pending_count == 1 else 'images'}? This cannot be undone."
            )
            confirm_column, cancel_column = st.columns(2)
            if confirm_column.button(
                "Confirm deletion", type="primary", width="stretch"
            ):
                self.delete_selected_images(st.session_state.pending_delete)
                st.rerun()
            if cancel_column.button("Cancel", width="stretch"):
                st.session_state.pending_delete = []
                st.session_state.gallery_selection = set()
                st.session_state.gallery_generation += 1
                st.rerun()
        elif st.button(
            "Delete selected",            disabled=not st.session_state.gallery_selection,
            width="stretch",
        ):
            st.session_state.pending_delete = sorted(st.session_state.gallery_selection)
            st.rerun()

# ---------------- Download Page ----------------
class DownloadPage(LunaVaultUI):
    def render(self, vault_images: list[Path]) -> None:
        if not vault_images:
            st.session_state.download_page = 0
            st.session_state.download_selection = set()
            st.info("No images are currently available to download.")
            return

        vault_names = {path.name for path in vault_images}
        st.session_state.download_selection.intersection_update(vault_names)
        generation = st.session_state.download_generation
        current_page, page_images = self.paginated_images(
            vault_images, "download_page", f"download_{generation}"
        )
        self._selection_gallery(
            page_images, current_page, generation,
            "download_selection", "download_selector"
        )

        selected = [path for path in vault_images if path.name in st.session_state.download_selection]
        if not selected:
            st.button("Download selected", icon=":material/download:", disabled=True, width="stretch")
            return

        archive = io.BytesIO()
        used_names: set[str] = set()
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            for path in selected:
                archive_name = self.display_name(path.name)
                if archive_name in used_names:
                    archive_name = path.name
                used_names.add(archive_name)
                bundle.write(path, archive_name)
        st.download_button(
            f"Download selected ({len(selected)})",
            data=archive.getvalue(),
            file_name="luna-vault-images.zip",
            mime="application/zip",            width="stretch",
        )

    def _selection_gallery(self, images: list[Path], page: int, generation: int,
                           state_key: str, key_prefix: str) -> None:
        for row_start in range(0, len(images), self.config.gallery_columns):
            row_images = images[row_start : row_start + self.config.gallery_columns]
            row_names = {path.name for path in row_images}
            selected_indices = [
                index for index, path in enumerate(row_images)
                if path.name in st.session_state[state_key]
            ]
            values = st_img_selector(
                images=[self.create_gallery_thumbnail(path) for path in row_images],
                value=selected_indices,
                corner_radius=10,
                selection_color="#A78BFA",
                img_per_row=self.config.gallery_columns,
                border_thickness=4,
                max_row_height=240,
                key=f"{key_prefix}_{generation}_{page}_{row_start}",
            ) or []
            st.session_state[state_key].difference_update(row_names)
            st.session_state[state_key].update(
                row_images[index].name for index in values if 0 <= index < len(row_images)
            )
            self.render_filename_row(row_images)


# ---------------- Hidden Page ----------------
class HiddenPage(DownloadPage):
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
                        result = self._post(
                            "/api/hidden/reset", {"pin": pin, "new_password": new_password}
                        )
                        st.session_state.hidden_auth_token = result["token"]
                        st.rerun()
                    except httpx.HTTPStatusError as error:
                        st.error(error.response.json().get("error", "Password reset failed."))
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

    def _render_collection(self, images: list[Path], empty_message: str,
                           page_key: str, selection_key: str, generation_key: str,
                           prefix: str, action_label: str, route: str) -> None:
        valid_names = {path.name for path in images}
        st.session_state[selection_key].intersection_update(valid_names)
        if not images:
            st.session_state[page_key] = 0
            st.info(empty_message)
            return
        generation = st.session_state[generation_key]
        page, page_images = self.paginated_images(images, page_key, f"{prefix}_{generation}")
        self._selection_gallery(page_images, page, generation, selection_key, prefix)
        if st.button(
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
                headers={"Authorization": f"Bearer {st.session_state.hidden_auth_token}"},
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
        hidden_images = [path for path in self.list_vault_images() if path.name in hidden_names]
        mode = st.segmented_control(
            "Hidden image action",
            ["Hidden images", "Add images"],
            default="Hidden images",
            label_visibility="collapsed",
            key="hidden_action_mode",
            width="stretch",
        )
        search_column, clear_column = st.columns([6, 1], vertical_alignment="bottom")
        query = search_column.text_input(
            "Search hidden vault by image name",
            placeholder="Type part of a filename",
            key="hidden_name_search",
            icon=":material/search:",
        ).strip().casefold()
        clear_column.button(
            ":material/close:",
            key="clear_hidden_name_search",
            help="Clear search",
            on_click=self.clear_search,
            args=("hidden_name_search",),
            width="stretch",
        )
        hidden_images = [
            path for path in hidden_images
            if query in self.display_name(path.name).casefold()
        ]
        visible_images = [
            path for path in visible_images
            if query in self.display_name(path.name).casefold()
        ]
        if mode == "Hidden images":
            self._render_collection(
                hidden_images, "No images are hidden.", "hidden_page",
                "hidden_selection", "hidden_generation", "hidden",
                "Restore selected", "/api/hidden/restore"
            )
        else:
            self._render_collection(
                visible_images, "No visible images are available.", "hide_page",
                "hide_selection", "hide_generation", "hide",
                "Hide selected", "/api/hidden/hide"
            )

# ---------------- Main App ----------------
def main() -> None:
    config = UIConfig.from_env()
    LunaVaultUI(config).initialize_state()

    st.set_page_config(page_title="Luna Vault")
    st.title(":material/photo_library: Luna Vault")

    upload_tab, view_tab, hidden_tab = st.tabs(
        [
            ":material/upload: Upload Images",
            ":material/visibility: View Images",
            ":material/lock: Hidden Images",
        ]
    )
    with upload_tab:
        UploadPage(config).render()

    metadata_response = httpx.get(f"{config.api_url}/api/metadata", timeout=10.0)
    metadata_response.raise_for_status()
    metadata = metadata_response.json()["images"]
    metadata_by_name = {item["name"]: item for item in metadata}
    vault_images = [
        path
        for path in LunaVaultUI(config).list_vault_images()
        if path.name in metadata_by_name
    ]
    with view_tab:
        ViewImagesPage(config).render(vault_images, metadata_by_name)
    with hidden_tab:
        HiddenPage(config).render(vault_images)


if __name__ == "__main__":
    main()
