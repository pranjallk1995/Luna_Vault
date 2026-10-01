import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


@dataclass(frozen=True)
class UIConfig:
    image_dir: Path
    api_url: str
    card_size: tuple[int, int] = (420, 248)
    thumbnail_background_color: str = "#171D33"
    thumbnail_padding: int = 20
    chunk_size: int = 1024 * 1024
    gallery_columns: int = 3
    images_per_page: int = 9
    image_extensions: frozenset[str] = frozenset(
        {".gif", ".jpeg", ".jpg", ".png", ".webp"}
    )

    @classmethod
    def from_env(cls) -> "UIConfig":
        api_url = os.getenv("LUNAVAULT_API_URL", "http://mcp:8000").rstrip("/")
        parsed = urlparse(api_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise RuntimeError("LUNAVAULT_API_URL must be a valid HTTP(S) URL.")
        return cls(
            image_dir=Path(os.getenv("IMAGE_DIR", "/data/images")),
            api_url=api_url,
        )
