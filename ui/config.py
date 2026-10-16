"""Validated presentation and service settings for the Streamlit UI."""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar
from urllib.parse import urlparse

import streamlit as st
from PIL import Image, ImageOps


@dataclass(frozen=True)
class UIConfig:
    """Immutable UI layout and backend-connection settings."""

    UI_ROOT: ClassVar[Path] = Path(__file__).resolve().parent
    LOGO_PATH: ClassVar[Path] = UI_ROOT / "assets" / "lunavisia_logo.png"

    image_dir: Path
    api_url: str
    card_size: tuple[int, int] = (420, 248)
    gallery_corner_radius: int = 10
    gallery_selection_color: str = "#D4D4D4"
    gallery_border_thickness: int = 4
    gallery_max_row_height: int = 240
    chunk_size: int = 1024 * 1024
    gallery_columns: int = 3
    images_per_page: int = 12
    image_extensions: frozenset[str] = frozenset(
        {".gif", ".jpeg", ".jpg", ".png", ".webp"}
    )

    @staticmethod
    @st.cache_data(show_spinner=False, max_entries=256)
    def gallery_thumbnail(
        image_path: str,
        modified_ns: int,
        max_size: tuple[int, int],
    ) -> Image.Image:
        """Build a cached natural-aspect thumbnail for a gallery card."""
        del modified_ns
        with Image.open(image_path) as source:
            source.draft("RGB", max_size)
            preview = ImageOps.exif_transpose(source).convert("RGB")
            return ImageOps.fit(
                preview,
                max_size,
                method=Image.Resampling.LANCZOS,
                centering=(0.5, 0.5),
            )

    @staticmethod
    @st.cache_data(show_spinner=False, max_entries=64)
    def full_preview(image_path: str, modified_ns: int) -> Image.Image:
        """Decode and cache a stored image for full-size display."""
        del modified_ns
        with Image.open(image_path) as source:
            preview = ImageOps.exif_transpose(source)
            preview.load()
            return preview.copy()

    @staticmethod
    @st.cache_data(show_spinner=False, max_entries=256)
    def image_file_facts(
        image_path: str, modified_ns: int
    ) -> tuple[int, int, int]:
        """Return cached byte size and pixel dimensions for an image."""
        del modified_ns
        path = Path(image_path)
        with Image.open(path) as source:
            width, height = source.size
        return path.stat().st_size, width, height

    @classmethod
    def from_env(cls) -> "UIConfig":
        """Build and validate UI configuration from environment variables."""
        api_url = (
            os.getenv("LUNAVISIA_API_URL")
            or os.getenv("LUNAVAULT_API_URL")
            or "http://luna-visia-mcp:8000"
        ).rstrip("/")
        parsed = urlparse(api_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise RuntimeError("LUNAVISIA_API_URL must be a valid HTTP(S) URL.")
        return cls(
            image_dir=Path(os.getenv("IMAGE_DIR", "/data/images")),
            api_url=api_url,
        )

    @property
    def api_headers(self) -> dict[str, str]:
        return {}
