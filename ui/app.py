"""Luna Vault Streamlit application entry point."""

import httpx
import streamlit as st

from config import UIConfig
from pages.hidden_page import HiddenPage
from pages.shared import LunaVaultUI
from pages.upload_page import UploadPage
from pages.view_page import ViewImagesPage


def main() -> None:
    """Configure Streamlit and render the active Luna Vault page."""
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