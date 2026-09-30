import os
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import streamlit as st
from PIL import Image, ImageDraw, ImageOps
from st_img_selector import st_img_selector


class LunaVaultUI:
    CARD_SIZE = (420, 300)
    CHUNK_SIZE = 1024 * 1024
    GALLERY_COLUMNS = 3
    IMAGES_PER_PAGE = 6
    IMAGE_EXTENSIONS = {".gif", ".jpeg", ".jpg", ".png", ".webp"}

    def __init__(self, image_dir: Path) -> None:
        self.image_dir = image_dir
        self.image_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def initialize_state() -> None:
        if "saved_uploads" not in st.session_state:
            st.session_state.saved_uploads = set()
        if "uploaded_images" not in st.session_state:
            st.session_state.uploaded_images = []
        if "uploader_key" not in st.session_state:
            st.session_state.uploader_key = 0
        if "gallery_generation" not in st.session_state:
            st.session_state.gallery_generation = 0
        if "gallery_page" not in st.session_state:
            st.session_state.gallery_page = 0
        if "gallery_selection" not in st.session_state:
            st.session_state.gallery_selection = set()
        if "pending_delete" not in st.session_state:
            st.session_state.pending_delete = []

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
                destination = self.image_dir / f"{uuid4().hex}_{safe_name}"
                with destination.open("wb") as image_file:
                    for offset in range(0, len(content), self.CHUNK_SIZE):
                        chunk = content[offset : offset + self.CHUNK_SIZE]
                        image_file.write(chunk)
                        written_bytes += len(chunk)
                        progress.progress(
                            written_bytes / total_bytes if total_bytes else 1.0,
                            text=f"Uploading {safe_name}",
                        )

                st.session_state.saved_uploads.add(upload_id)
                st.session_state.uploaded_images.append(
                    {
                        "upload_id": upload_id,
                        "stored_name": destination.name,
                    }
                )
        finally:
            progress.empty()

    def delete_selected_images(self, stored_names: list[str]) -> None:
        image_root = self.image_dir.resolve()
        image_paths = []

        for stored_name in stored_names:
            image_path = (self.image_dir / stored_name).resolve()
            if image_path.parent != image_root:
                raise ValueError("Refusing to delete an image outside the vault directory.")
            image_paths.append(image_path)

        for image_path in image_paths:
            image_path.unlink(missing_ok=True)

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

        remaining_pages = max(
            1,
            (len(self.list_vault_images()) + self.IMAGES_PER_PAGE - 1)
            // self.IMAGES_PER_PAGE,
        )
        st.session_state.gallery_page = min(
            st.session_state.gallery_page,
            remaining_pages - 1,
        )

    @staticmethod
    def clear_ui_state() -> None:
        st.session_state.uploaded_images = []
        st.session_state.saved_uploads = set()
        st.session_state.uploader_key += 1

    def list_vault_images(self) -> list[Path]:
        return sorted(
            (
                path
                for path in self.image_dir.iterdir()
                if path.is_file() and path.suffix.lower() in self.IMAGE_EXTENSIONS
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

    def create_gallery_card(self, image_path: Path) -> Image.Image:
        card_width, card_height = self.CARD_SIZE
        image_area_height = card_height - 52
        card = Image.new("RGB", self.CARD_SIZE, "#171D33")

        with Image.open(image_path) as source:
            preview = ImageOps.exif_transpose(source).convert("RGB")
            preview.thumbnail((card_width - 20, image_area_height - 20))

        left = (card_width - preview.width) // 2
        top = (image_area_height - preview.height) // 2
        card.paste(preview, (left, top))

        display_name = self.display_name(image_path.name)
        if len(display_name) > 48:
            display_name = f"{display_name[:45]}..."
        ImageDraw.Draw(card).text(
            (12, image_area_height + 16),
            display_name,
            fill="#E8EAF3",
        )
        return card

    def render_upload_page(self) -> None:
        uploads = st.file_uploader(
            ":material/upload_file: Drag and drop image files",
            type=["png", "jpg", "jpeg", "gif", "webp"],
            accept_multiple_files=True,
            key=f"image_uploader_{st.session_state.uploader_key}",
        )
        if uploads:
            self.upload_images(uploads)

        if st.session_state.uploaded_images and st.button(
            "Clear",
            icon=":material/refresh:",
            width="stretch",
        ):
            self.clear_ui_state()
            st.rerun()

    def render_gallery_navigation(self, page_count: int) -> None:
        current_page = min(
            max(st.session_state.gallery_page, 0),
            page_count - 1,
        )
        st.session_state.gallery_page = current_page

        previous_column, page_column, next_column = st.columns([1, 2, 1])
        if previous_column.button(
            "← Previous",
            disabled=current_page == 0,
            width="stretch",
        ):
            st.session_state.gallery_page = current_page - 1
            st.rerun()

        selected_page = page_column.selectbox(
            "Page",
            options=list(range(1, page_count + 1)),
            index=current_page,
            label_visibility="collapsed",
            key=(
                f"gallery_page_{st.session_state.gallery_generation}_"
                f"{page_count}"
            ),
        )
        if selected_page - 1 != current_page:
            st.session_state.gallery_page = selected_page - 1
            st.rerun()

        if next_column.button(
            "Next →",
            disabled=current_page == page_count - 1,
            width="stretch",
        ):
            st.session_state.gallery_page = current_page + 1
            st.rerun()

    def render_delete_page(self) -> None:
        vault_images = self.list_vault_images()
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

        page_count = (
            len(vault_images) + self.IMAGES_PER_PAGE - 1
        ) // self.IMAGES_PER_PAGE
        self.render_gallery_navigation(page_count)

        current_page = st.session_state.gallery_page
        page_start = current_page * self.IMAGES_PER_PAGE
        page_images = vault_images[
            page_start : page_start + self.IMAGES_PER_PAGE
        ]
        page_names = {image_path.name for image_path in page_images}
        selected_indices = [
            index
            for index, image_path in enumerate(page_images)
            if image_path.name in st.session_state.gallery_selection
        ]
        cards = [
            self.create_gallery_card(image_path)
            for image_path in page_images
        ]

        selected_indices = st_img_selector(
            images=cards,
            value=selected_indices,
            corner_radius=10,
            selection_color="#A78BFA",
            img_per_row=self.GALLERY_COLUMNS,
            border_thickness=4,
            max_row_height=240,
            key=(
                f"gallery_selector_{st.session_state.gallery_generation}_"
                f"{current_page}"
            ),
        ) or []

        st.session_state.gallery_selection.difference_update(page_names)
        st.session_state.gallery_selection.update(
            page_images[index].name
            for index in selected_indices
            if 0 <= index < len(page_images)
        )

        if st.session_state.pending_delete:
            pending_count = len(st.session_state.pending_delete)
            st.warning(
                f"Delete {pending_count} selected "
                f"{'image' if pending_count == 1 else 'images'}? "
                "This cannot be undone."
            )
            confirm_column, cancel_column = st.columns(2)
            if confirm_column.button(
                "Confirm deletion",
                type="primary",
                width="stretch",
            ):
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
            st.session_state.pending_delete = sorted(
                st.session_state.gallery_selection
            )
            st.rerun()

    def render(self) -> None:
        st.set_page_config(page_title="Luna Vault")
        st.title(":material/photo_library: Luna Vault")
        st.caption("Upload images to the shared vault.")
        self.initialize_state()

        upload_tab, delete_tab = st.tabs(["Upload Images", "Delete Images"])
        with upload_tab:
            self.render_upload_page()
        with delete_tab:
            self.render_delete_page()


def main() -> None:
    image_dir = Path(os.getenv("IMAGE_DIR", "/data/images"))
    LunaVaultUI(image_dir).render()


if __name__ == "__main__":
    main()
