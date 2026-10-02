"""Luna Vault Streamlit application entry point."""

import httpx
import streamlit as st

from config import UIConfig
from styles import apply_app_styles, render_app_header, render_section_intro
from tabs.hidden_page import HiddenPage
from tabs.shared import LunaVaultUI
from tabs.upload_page import UploadPage
from tabs.view_page import ViewImagesPage


def main() -> None:
    """Configure Streamlit and render the active Luna Vault page."""
    st.set_page_config(
        page_title="Luna Vault",
        page_icon=":material/bedtime:",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    config = UIConfig.from_env()
    LunaVaultUI(config).initialize_state()
    apply_app_styles()
    render_app_header()

    upload_tab, view_tab, hidden_tab = st.tabs(
        [
            ":material/upload: Upload Images",
            ":material/visibility: View Images",
            ":material/lock: Hidden Images",
        ]
    )

    metadata_response = httpx.get(f"{config.api_url}/api/metadata", timeout=10.0)
    metadata_response.raise_for_status()
    metadata = metadata_response.json()["images"]
    metadata_by_name = {item["name"]: item for item in metadata}
    vault_images = [
        path
        for path in LunaVaultUI(config).list_vault_images()
        if path.name in metadata_by_name
    ]

    with upload_tab:
        render_section_intro(
            "Ingest",
            "Add images",
            "Upload one or many images and let Luna Vault generate searchable details.",
        )
        UploadPage(config).render()
    with view_tab:
        render_section_intro(
            "Library",
            "Browse your vault",
            "Find, inspect, download, or remove images from your private collection.",
        )
        ViewImagesPage(config).render(vault_images, metadata_by_name)
    with hidden_tab:
        render_section_intro(
            "Protected space",
            "Hidden vault",
            "Keep sensitive images behind a separate password-protected view.",
        )
        HiddenPage(config).render(vault_images)


if __name__ == "__main__":
    main()
