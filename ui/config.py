"""Validated presentation and service settings for the Streamlit UI."""

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


@dataclass(frozen=True)
class UIConfig:
    """Immutable UI layout and backend-connection settings."""

    image_dir: Path
    api_url: str
    card_size: tuple[int, int] = (420, 248)
    thumbnail_background_color: str = "#171D33"
    thumbnail_padding: int = 20
    gallery_corner_radius: int = 10
    gallery_selection_color: str = "#A78BFA"
    gallery_border_thickness: int = 4
    gallery_max_row_height: int = 240
    chunk_size: int = 1024 * 1024
    gallery_columns: int = 3
    images_per_page: int = 6
    image_extensions: frozenset[str] = frozenset(
        {".gif", ".jpeg", ".jpg", ".png", ".webp"}
    )

    @classmethod
    def from_env(cls) -> "UIConfig":
        """Build and validate UI configuration from environment variables."""
        api_url = os.getenv("LUNAVAULT_API_URL", "http://mcp:8000").rstrip("/")
        parsed = urlparse(api_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise RuntimeError("LUNAVAULT_API_URL must be a valid HTTP(S) URL.")
        return cls(
            image_dir=Path(os.getenv("IMAGE_DIR", "/data/images")),
            api_url=api_url,
        )
