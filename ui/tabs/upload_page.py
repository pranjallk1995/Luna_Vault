"""Upload page for Luna Vault."""

import base64
import time
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import httpx
import streamlit as st

from tabs.shared import LunaVaultUI


class UploadPage(LunaVaultUI):
    """Render uploads and persist AI-generated metadata results."""

    @staticmethod
    def _post_with_progress(
        api_url: str,
        stored_name: str,
        display_name: str,
        content,
        progress,
        progress_value: float,
    ) -> httpx.Response:
        """Keep progress feedback alive during the blocking vision request."""
        payload = {
            "name": stored_name,
            "content_base64": base64.b64encode(content).decode("ascii"),
        }
        started_at = time.monotonic()
        tick = 0

        with ThreadPoolExecutor(max_workers=1) as executor:
            request = executor.submit(
                httpx.post,
                f"{api_url}/api/images",
                json=payload,
                timeout=360.0,
            )
            while not request.done():
                elapsed = int(time.monotonic() - started_at)
                dots = "." * ((tick % 3) + 1)
                progress.progress(
                    progress_value,
                    text=(
                        f"Analyzing {display_name} with the local vision model. "
                        f"Still working: {elapsed}s elapsed. The first request can "
                        f"take longer while the model becomes ready{dots}"
                    ),
                )
                tick += 1
                time.sleep(0.5)

            response = request.result()

        response.raise_for_status()
        return response

    def upload_images(self, uploads: list) -> None:
        """Upload new files and retain the metadata returned by ingestion."""
        pending = []
        for upload in uploads:
            content = upload.getbuffer()
            upload_id = sha256(content).hexdigest()
            if upload_id not in st.session_state.saved_uploads:
                pending.append((upload, upload_id, content))

        if not pending:
            return

        progress = st.progress(0.0, text="Preparing images for upload...")
        total_bytes = sum(len(content) for _, _, content in pending)
        written_bytes = 0

        try:
            for upload, upload_id, content in pending:
                safe_name = Path(upload.name).name
                stored_name = f"{uuid4().hex}_{safe_name}"
                progress.progress(
                    written_bytes / total_bytes if total_bytes else 0.0,
                    text=(
                        f"Analyzing {safe_name} with the local vision model. "
                        "The first request may include model initialization."
                    ),
                )
                try:
                    response = self._post_with_progress(
                        self.config.api_url,
                        stored_name,
                        safe_name,
                        content,
                        progress,
                        written_bytes / total_bytes if total_bytes else 0.0,
                    )
                except httpx.HTTPError as error:
                    st.session_state.setdefault("failed_uploads", {})[upload_id] = {
                        "name": safe_name,
                        "content": bytes(content),
                    }
                    st.error(f"Could not upload {safe_name}: {error}")
                    written_bytes += len(content)
                    continue

                metadata = response.json()
                written_bytes += len(content)
                progress.progress(
                    written_bytes / total_bytes if total_bytes else 1.0,
                    text=f"Analysis and upload complete for {safe_name}",
                )
                st.session_state.saved_uploads.add(upload_id)
                st.session_state.uploaded_images.append(
                    {"upload_id": upload_id, **metadata}
                )
        finally:
            progress.empty()

    def retry_upload(self, upload_id: str) -> None:
        """Retry one previously failed upload."""
        failed = st.session_state.failed_uploads[upload_id]
        stored_name = f"{uuid4().hex}_{failed['name']}"
        progress = st.progress(0.0, text="Preparing image for analysis...")
        try:
            response = self._post_with_progress(
                self.config.api_url,
                stored_name,
                failed["name"],
                failed["content"],
                progress,
                0.0,
            )
            progress.progress(1.0, text=f"Analysis complete for {failed['name']}.")
            st.session_state.saved_uploads.add(upload_id)
            st.session_state.uploaded_images.append(
                {"upload_id": upload_id, **response.json()}
            )
            del st.session_state.failed_uploads[upload_id]
        finally:
            progress.empty()

    @staticmethod
    def clear_ui_state() -> None:
        """Reset upload results and recreate the uploader widget."""
        st.session_state.uploaded_images = []
        st.session_state.saved_uploads = set()
        st.session_state.uploader_key += 1

    def render(self) -> None:
        """Render the upload page interface."""
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
