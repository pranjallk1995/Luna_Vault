import base64
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
) -> Image.Image:
    """Build and cache a gallery thumbnail until its source file changes."""
    del modified_ns  # Included in the cache key to invalidate modified images.
    card_width, card_height = card_size
    card = Image.new("RGB", card_size, "#171D33")

    with Image.open(image_path) as source:
        source.draft("RGB", (card_width - 20, card_height - 20))
        preview = ImageOps.exif_transpose(source).convert("RGB")
        preview.thumbnail((card_width - 20, card_height - 20))

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
        }
        for key, value in defaults.items():
            if key not in st.session_state:
                st.session_state[key] = value

    def list_vault_images(self) -> list[Path]:
        return sorted(
            (
                path
                for path in self.image_dir.iterdir()
                if path.is_file() and path.suffix.lower() in self.config.image_extensions
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

    def create_gallery_thumbnail(self, image_path: Path) -> Image.Image:
        return cached_gallery_thumbnail(
            str(image_path),
            image_path.stat().st_mtime_ns,
            self.config.card_size,
        )

    def render_gallery_navigation(self, page_count: int, state_key: str, key_prefix: str) -> int:
        current_page = min(max(st.session_state[state_key], 0), page_count - 1)
        st.session_state[state_key] = current_page
        selector_key = f"{key_prefix}_page"

        previous_column, page_column, next_column = st.columns([1, 2, 1])
        if previous_column.button(":material/arrow_back:", disabled=current_page == 0,
                                  width="stretch", key=f"{key_prefix}_previous"):
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

        if next_column.button(":material/arrow_forward:", disabled=current_page == page_count - 1,
                              width="stretch", key=f"{key_prefix}_next"):
            st.session_state[state_key] = current_page + 1
            st.session_state[selector_key] = current_page + 2
            st.rerun()

        return current_page

    def paginated_images(self, vault_images: list[Path], page_state_key: str, key_prefix: str) -> tuple[int, list[Path]]:
        page_count = (len(vault_images) + self.config.images_per_page - 1) // self.config.images_per_page
        current_page = self.render_gallery_navigation(page_count, page_state_key, f"{key_prefix}_{page_count}")
        page_start = current_page * self.config.images_per_page
        return current_page, vault_images[page_start: page_start + self.config.images_per_page]

    def render_filename_row(
        self,
        row_images: list[Path],
        metadata_by_name: dict[str, dict] | None = None,
    ) -> None:
        filename_columns = st.columns(self.config.gallery_columns)
        for column, image_path in zip(filename_columns, row_images):
            column.caption(self.display_name(image_path.name))
            metadata = (metadata_by_name or {}).get(image_path.name)
            if metadata:
                column.write(metadata["caption"])
                column.caption(" Â· ".join(f"#{tag}" for tag in metadata["tags"]))


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
                st.caption(self.display_name(image["name"]))
                st.write(image["caption"])
                st.caption(" Â· ".join(f"#{tag}" for tag in image["tags"]))
        if st.session_state.uploaded_images and st.button("Clear", icon=":material/refresh:", width="stretch"):
            self.clear_ui_state()
            st.rerun()


# ---------------- View Page ----------------
class ViewPage(LunaVaultUI):
    def render(self, vault_images: list[Path], metadata_by_name: dict[str, dict]) -> None:
        if not vault_images:
            st.session_state.view_page = 0
            st.info("No images are currently stored in Luna Vault.")
            return

        generation = st.session_state.view_generation
        current_page, page_images = self.paginated_images(vault_images, "view_page", f"view_{generation}")
        clicked_image = None

        for row_start in range(0, len(page_images), self.config.gallery_columns):
            row_images = page_images[row_start: row_start + self.config.gallery_columns]
            thumbnails = [self.create_gallery_thumbnail(image_path) for image_path in row_images]
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
            self.render_filename_row(row_images, metadata_by_name)

            if clicked_indices and clicked_image is None:
                clicked_index = clicked_indices[-1]
                if 0 <= clicked_index < len(row_images):
                    clicked_image = row_images[clicked_index]

        if clicked_image is not None:
            st.session_state.view_generation += 1

            @st.dialog(self.display_name(clicked_image.name), width="large")
            def show_full_size_image() -> None:
                st.image(clicked_image, width="stretch")

            show_full_size_image()


# ---------------- Delete Page ----------------
class DeletePage(LunaVaultUI):
    def delete_selected_images(self, stored_names: list[str]) -> None:
        image_root = self.image_dir.resolve()
        image_paths = []

        for stored_name in stored_names:
            image_path = (self.image_dir / stored_name).resolve()
            if image_path.parent != image_root:
                raise ValueError("Refusing to delete an image outside the vault directory.")
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
            if image["stored_name"] in deleted_names:
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
            (len(self.list_vault_images()) + self.config.images_per_page - 1) // self.config.images_per_page,
        )
        st.session_state.gallery_page = min(st.session_state.gallery_page, remaining_pages - 1)
        st.session_state.view_page = min(st.session_state.view_page, remaining_pages - 1)

    def render(self, vault_images: list[Path]) -> None:
        if not vault_images:
            st.session_state.gallery_page = 0
            st.session_state.gallery_selection = set()
            st.info("No images are currently stored in Luna Vault.")
            return

        vault_names = {image_path.name for image_path in vault_images}
        st.session_state.gallery_selection.intersection_update(vault_names)
        st.session_state.pending_delete = [
            stored_name for stored_name in st.session_state.pending_delete if stored_name in vault_names
        ]

        generation = st.session_state.gallery_generation
        current_page, page_images = self.paginated_images(vault_images, "gallery_page", f"delete_{generation}")

        for row_start in range(0, len(page_images), self.config.gallery_columns):
            row_images = page_images[row_start: row_start + self.config.gallery_columns]
            row_names = {image_path.name for image_path in row_images}
            selected_indices = [
                index for index, image_path in enumerate(row_images) if image_path.name in st.session_state.gallery_selection
            ]
            thumbnails = [self.create_gallery_thumbnail(image_path) for image_path in row_images]
            selected_indices = st_img_selector(
                images=thumbnails,
                value=selected_indices,
                corner_radius=10,
                selection_color="#A78BFA",
                img_per_row=self.config.gallery_columns,
                border_thickness=4,
                max_row_height=240,
                key=f"delete_selector_{generation}_{current_page}_{row_start}",
            ) or []

            st.session_state.gallery_selection.difference_update(row_names)
            st.session_state.gallery_selection.update(
                row_images[index].name for index in selected_indices if 0 <= index < len(row_images)
            )
            self.render_filename_row(row_images)

        if st.session_state.pending_delete:
            pending_count = len(st.session_state.pending_delete)
            st.warning(
                f"Delete {pending_count} selected "
                f"{'image' if pending_count == 1 else 'images'}? This cannot be undone."
            )
            confirm_column, cancel_column = st.columns(2)
            if confirm_column.button("Confirm deletion", type="primary", width="stretch"):
                self.delete_selected_images(st.session_state.pending_delete)
                st.rerun()
            if cancel_column.button("Cancel", width="stretch"):
                st.session_state.pending_delete = []
                st.session_state.gallery_selection = set()
                st.session_state.gallery_generation += 1
                st.rerun()
        elif st.button(
            "Delete selected",
            icon=":material/delete:",
            disabled=not st.session_state.gallery_selection,
            width="stretch",
        ):
            st.session_state.pending_delete = sorted(st.session_state.gallery_selection)


# ---------------- Main App ----------------
def main() -> None:
    config = UIConfig.from_env()
    LunaVaultUI(config).initialize_state()

    st.set_page_config(page_title="Luna Vault")
    st.title(":material/photo_library: Luna Vault")

    upload_tab, view_tab, delete_tab = st.tabs(
        [
            ":material/upload: Upload Images",
            ":material/visibility: View Images",
            ":material/delete: Delete Images"
        ]
    )
    with upload_tab:
        UploadPage(config).render()

    metadata_response = httpx.get(f"{config.api_url}/api/metadata", timeout=10.0)
    metadata_response.raise_for_status()
    metadata = metadata_response.json()["images"]
    metadata_by_name = {item["name"]: item for item in metadata}
    vault_images = [
        path for path in LunaVaultUI(config).list_vault_images()
        if path.name in metadata_by_name
    ]
    with view_tab:
        ViewPage(config).render(vault_images, metadata_by_name)
    with delete_tab:
        DeletePage(config).render(vault_images)


if __name__ == "__main__":
    main()

