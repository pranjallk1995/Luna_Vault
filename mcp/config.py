import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse


@dataclass(frozen=True)
class AppConfig:
    image_dir: Path
    database_url: str
    ollama_url: str
    vision_model: str
    allowed_formats: dict[str, str] = field(
        default_factory=lambda: {
            ".gif": "GIF",
            ".jpeg": "JPEG",
            ".jpg": "JPEG",
            ".png": "PNG",
            ".webp": "WEBP",
        }
    )
    max_image_bytes: int = 50 * 1024 * 1024
    max_tags: int = 16
    search_limit_max: int = 100
    search_stop_words: frozenset[str] = frozenset(
        {
            "about",
            "all",
            "are",
            "count",
            "depict",
            "depicting",
            "do",
            "find",
            "how",
            "image",
            "images",
            "many",
            "of",
            "photo",
            "photos",
            "picture",
            "pictures",
            "show",
            "showing",
            "that",
            "the",
            "there",
            "what",
            "with",
        }
    )

    @property
    def max_base64_chars(self) -> int:
        return 4 * ((self.max_image_bytes + 2) // 3)

    @classmethod
    def from_env(cls) -> "AppConfig":
        database_url = os.getenv("DATABASE_URL", "").strip()
        if not database_url:
            raise RuntimeError("DATABASE_URL is required.")
        ollama_url = os.getenv("OLLAMA_URL", "http://ollama:11434").rstrip("/")
        parsed = urlparse(ollama_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise RuntimeError("OLLAMA_URL must be a valid HTTP(S) URL.")
        vision_model = os.getenv("VISION_MODEL", "qwen2.5vl:7b").strip()
        if not vision_model:
            raise RuntimeError("VISION_MODEL cannot be blank.")
        image_dir = Path(os.getenv("IMAGE_DIR", "/data/images"))
        return cls(
            image_dir=image_dir,
            database_url=database_url,
            ollama_url=ollama_url,
            vision_model=vision_model,
        )
