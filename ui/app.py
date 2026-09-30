import os
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import streamlit as st


class LunaVaultUI:
    CHUNK_SIZE = 1024 * 1024

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

    def delete_selected_image(self, selected_index: int) -> None:
        selected = st.session_state.uploaded_images[selected_index - 1]
        image_root = self.image_dir.resolve()
        image_path = (self.image_dir / selected["stored_name"]).resolve()

        if image_path.parent != image_root:
            raise ValueError("Refusing to delete an image outside the vault directory.")

        image_path.unlink(missing_ok=True)
        st.session_state.saved_uploads.discard(selected["upload_id"])
        del st.session_state.uploaded_images[selected_index - 1]

    @staticmethod
    def clear_ui_state() -> None:
        st.session_state.uploaded_images = []
        st.session_state.saved_uploads = set()
        st.session_state.uploader_key += 1

    def render_uploaded_images(self) -> None:
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

        image_count = len(st.session_state.uploaded_images)
        selected_index = st.select_slider(
            "Browse uploaded images",
            options=list(range(1, image_count + 1)),
            value=1,
            key=f"image_browser_{image_count}_{st.session_state.uploader_key}",
            help="Move the slider to preview an uploaded image.",
        )
        selected = st.session_state.uploaded_images[selected_index - 1]
        selected_path = self.image_dir / selected["stored_name"]

        if selected_path.is_file():
            st.image(
                selected_path,
                caption=selected["File"],
                width="stretch",
            )

        if st.button(
            "Delete selected image",
            icon=":material/delete:",
            width="stretch",
        ):
            self.delete_selected_image(selected_index)
            st.rerun()

        if st.button(
            "Clear",
            icon=":material/refresh:",
            width="stretch",
        ):
            self.clear_ui_state()
            st.rerun()

    def render(self) -> None:
        st.set_page_config(page_title="Luna Vault")
        st.title(":material/photo_library: Luna Vault")
        st.caption("Upload images to the shared vault.")
        self.initialize_state()

        uploads = st.file_uploader(
            ":material/upload_file: Drag and drop image files",
            type=["png", "jpg", "jpeg", "gif", "webp"],
            accept_multiple_files=True,
            key=f"image_uploader_{st.session_state.uploader_key}",
        )
        if uploads:
            self.upload_images(uploads)

        self.render_uploaded_images()


def main() -> None:
    image_dir = Path(os.getenv("IMAGE_DIR", "/data/images"))
    LunaVaultUI(image_dir).render()


if __name__ == "__main__":
    main()
