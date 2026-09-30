import os
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import streamlit as st


class LunaVaultUI:
    CHUNK_SIZE = 1024 * 1024
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
        if "delete_index" not in st.session_state:
            st.session_state.delete_index = 0

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
                        "Status": "\u2705 Uploaded",
                        "upload_id": upload_id,
                        "stored_name": destination.name,
                    }
                )
        finally:
            progress.empty()

    def delete_selected_image(self, stored_name: str) -> None:
        image_root = self.image_dir.resolve()
        image_path = (self.image_dir / stored_name).resolve()

        if image_path.parent != image_root:
            raise ValueError("Refusing to delete an image outside the vault directory.")

        image_path.unlink(missing_ok=True)

        retained_uploads = []
        for image in st.session_state.uploaded_images:
            if image["stored_name"] == stored_name:
                st.session_state.saved_uploads.discard(image["upload_id"])
            else:
                retained_uploads.append(image)
        st.session_state.uploaded_images = retained_uploads

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
                "Status": image["Status"],
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

        st.session_state.delete_index = min(
            max(st.session_state.delete_index, 0),
            len(vault_images) - 1,
        )
        current_index = st.session_state.delete_index
        current_image = vault_images[current_index]

        st.caption(
            f"Image {current_index + 1} of {len(vault_images)} — "
            f"{self.display_name(current_image.name)}"
        )
        st.image(
            current_image,
            caption=self.display_name(current_image.name),
            width="stretch",
        )

        previous_column, next_column = st.columns(2)
        if previous_column.button(
            "Previous",
            disabled=current_index == 0,
            width="stretch",
        ):
            st.session_state.delete_index = current_index - 1
            st.rerun()
        if next_column.button(
            "Next",
            disabled=current_index == len(vault_images) - 1,
            width="stretch",
        ):
            st.session_state.delete_index = current_index + 1
            st.rerun()

        if st.button(
            "Delete selected image",
            icon=":material/delete:",
            width="stretch",
        ):
            self.delete_selected_image(current_image.name)
            remaining_count = len(vault_images) - 1
            st.session_state.delete_index = min(
                current_index,
                max(remaining_count - 1, 0),
            )
            st.rerun()

    def render(self) -> None:
        st.set_page_config(page_title="Luna Vault")
        st.title(":material/photo_library: Luna Vault")
        st.caption("Upload images to the shared vault.")
        self.initialize_state()

        active_page = st.radio(
            "View",
            options=["Upload Images", "Delete Images"],
            horizontal=True,
            label_visibility="collapsed",
        )
        if active_page == "Upload Images":
            self.render_upload_page()
        else:
            self.render_delete_page()


def main() -> None:
    image_dir = Path(os.getenv("IMAGE_DIR", "/data/images"))
    LunaVaultUI(image_dir).render()


if __name__ == "__main__":
    main()
