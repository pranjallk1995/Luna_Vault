import os
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import streamlit as st


IMAGE_DIR = Path(os.getenv("IMAGE_DIR", "/data/images"))
IMAGE_DIR.mkdir(parents=True, exist_ok=True)

st.set_page_config(page_title="Luna Vault")
st.title("Luna Vault")
st.caption("Upload images to the shared vault.")

uploads = st.file_uploader(
    "Drag and drop image files",
    type=["png", "jpg", "jpeg", "gif", "webp"],
    accept_multiple_files=True,
)

if "saved_uploads" not in st.session_state:
    st.session_state.saved_uploads = set()

if uploads:
    file_info = [
        {
            "File": upload.name,
            "Type": upload.type or "Unknown",
            "Size": f"{upload.size / (1024 * 1024):.2f} MiB",
        }
        for upload in uploads
    ]
    st.dataframe(file_info, hide_index=True, use_container_width=True)

    pending = []
    for upload in uploads:
        content = upload.getbuffer()
        upload_id = sha256(content).hexdigest()
        if upload_id not in st.session_state.saved_uploads:
            pending.append((upload, upload_id, content))

    progress = st.progress(0.0, text="Preparing upload...")
    total_bytes = sum(len(content) for _, _, content in pending)
    written_bytes = 0

    for upload, upload_id, content in pending:
        safe_name = Path(upload.name).name
        destination = IMAGE_DIR / f"{uuid4().hex}_{safe_name}"
        with destination.open("wb") as image_file:
            for offset in range(0, len(content), 1024 * 1024):
                chunk = content[offset : offset + 1024 * 1024]
                image_file.write(chunk)
                written_bytes += len(chunk)
                progress.progress(
                    written_bytes / total_bytes if total_bytes else 1.0,
                    text=f"Uploading {safe_name}",
                )
        st.session_state.saved_uploads.add(upload_id)

    progress.progress(1.0, text="Upload complete")
