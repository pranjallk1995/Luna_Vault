import os
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import streamlit as st


class LunaVaultUI:
    CHUNK_SIZE = 1024 * 1024
    GALLERY_COLUMNS = 3
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
                        "File": upload.name,
                        "Type": upload.type or "Unknown",
                        "Size": f"{upload.size / (1024 * 1024):.2f} MiB",
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
        st.session_state.gallery_generation += 1

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

    @staticmethod
    def gallery_key(stored_name: str, generation: int) -> str:
        name_hash = sha256(stored_name.encode("utf-8")).hexdigest()[:16]
        return f"gallery_{generation}_{name_hash}"

    def render_upload_page(self) -> None:
        uploads = st.file_uploader(
            ":material/upload_file: Drag and drop image files",
            type=["png", "jpg", "jpeg", "gif", "webp"],
            accept_multiple_files=True,
            key=f"image_uploader_{st.session_state.uploader_key}",
        )
        if uploads:
            self.upload_images(uploads)

        if not st.session_state.uploaded_images:
            return

        table_rows = [
            {
                "File": image["File"],
                "Type": image["Type"],
                "Size": image["Size"],
            }
            for image in st.session_state.uploaded_images
        ]
        st.dataframe(table_rows, hide_index=True, width="stretch")

        if st.button(
            "Clear",
            icon=":material/refresh:",
            width="stretch",
        ):
            self.clear_ui_state()
            st.rerun()

    def render_delete_page(self) -> None:
        vault_images = self.list_vault_images()
        if not vault_images:
            st.info("No images are currently stored in Luna Vault.")
            return

        selected_names = []
        generation = st.session_state.gallery_generation

        for row_start in range(0, len(vault_images), self.GALLERY_COLUMNS):
            columns = st.columns(self.GALLERY_COLUMNS)
            row_images = vault_images[
                row_start : row_start + self.GALLERY_COLUMNS
            ]
            for column, image_path in zip(columns, row_images):
                with column:
                    st.image(image_path, width="stretch")
                    st.caption(self.display_name(image_path.name))
                    if st.checkbox(
                        "Select",
                        key=self.gallery_key(image_path.name, generation),
                    ):
                        selected_names.append(image_path.name)

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
                st.session_state.gallery_generation += 1
                st.rerun()
        elif st.button(
            "Delete selected",
            icon=":material/delete:",
            disabled=not selected_names,
            width="stretch",
        ):
            st.session_state.pending_delete = selected_names
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
