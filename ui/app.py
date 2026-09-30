import os
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

if uploads and st.button("Save to vault", type="primary"):
    for upload in uploads:
        safe_name = Path(upload.name).name
        destination = IMAGE_DIR / f"{uuid4().hex}_{safe_name}"
        destination.write_bytes(upload.getbuffer())
    st.success(f"Saved {len(uploads)} image(s).")
