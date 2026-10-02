"""Upload page for Luna Vault."""

import base64
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import httpx
import streamlit as st

from tabs.shared import LunaVaultUI


class UploadPage(LunaVaultUI):
    """Render uploads and persist AI-generated metadata results."""

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
                try:
                    response = httpx.post(
                        f"{self.config.api_url}/api/images",
                        json={
                            "name": stored_name,
                            "content_base64": base64.b64encode(content).decode("ascii"),
                        },
                        timeout=360.0,
                    )
                    response.raise_for_status()
                except httpx.HTTPError as error:
                    st.session_state.setdefault("failed_uploads", {})[upload_id] = {"name": safe_name, "content": bytes(content)}
                    st.error(f"Could not upload {safe_name}: {error}")
                    written_bytes += len(content)
                    continue

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

    def retry_upload(self, upload_id: str) -> None:
        failed = st.session_state.failed_uploads[upload_id]
        response = httpx.post(
            f"{self.config.api_url}/api/images",
            json={
                "name": f"{uuid4().hex}_{failed['name']}",
                "content_base64": base64.b64encode(failed["content"]).decode("ascii"),
            },
            timeout=360.0,
        )
        response.raise_for_status()
        st.session_state.saved_uploads.add(upload_id)
        st.session_state.uploaded_images.append(
            {"upload_id": upload_id, **response.json()}
        )
        del st.session_state.failed_uploads[upload_id]
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

        for upload_id, failed in (
            st.session_state.get("failed_uploads", {}).copy().items()
        ):
            if st.button(f"Retry {failed['name']}", key=f"retry_{upload_id}"):
                try:
                    self.retry_upload(upload_id)
                    st.rerun()
                except httpx.HTTPError as error:
                    st.error(f"Could not upload {failed['name']}: {error}")
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
