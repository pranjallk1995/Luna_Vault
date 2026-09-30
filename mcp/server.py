import base64
import binascii
import os
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from mcp.server.fastmcp import FastMCP, Image as MCPImage
from PIL import Image as PillowImage
from PIL import UnidentifiedImageError


IMAGE_DIR = Path(os.getenv("IMAGE_DIR", "/data/images"))
IMAGE_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_FORMATS = {
    ".gif": "GIF",
    ".jpeg": "JPEG",
    ".jpg": "JPEG",
    ".png": "PNG",
    ".webp": "WEBP",
}
MAX_IMAGE_BYTES = 50 * 1024 * 1024
MAX_BASE64_CHARS = 4 * ((MAX_IMAGE_BYTES + 2) // 3)

mcp = FastMCP("Luna Vault", host="0.0.0.0", port=8000)


def _safe_image_path(name: str) -> Path:
    """Return a vault-local image path or reject unsafe/unsupported names."""
    if not name or Path(name).name != name or name in {".", ".."}:
        raise ValueError("Image name must be a plain filename without directories.")

    suffix = Path(name).suffix.lower()
    if suffix not in ALLOWED_FORMATS:
        allowed = ", ".join(sorted(ALLOWED_FORMATS))
        raise ValueError(f"Unsupported image extension. Allowed: {allowed}")

    image_root = IMAGE_DIR.resolve()
    image_path = (IMAGE_DIR / name).resolve()
    if image_path.parent != image_root:
        raise ValueError("Image path must remain inside the vault directory.")
    return image_path


def _decode_and_validate_image(name: str, content_base64: str) -> bytes:
    """Decode a bounded base64 payload and verify its image format."""
    if len(content_base64) > MAX_BASE64_CHARS:
        raise ValueError("Image content exceeds the 50 MiB limit.")

    try:
        image_data = base64.b64decode(content_base64, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError("content_base64 must be valid base64 data.") from error

    if not image_data:
        raise ValueError("Image content cannot be empty.")
    if len(image_data) > MAX_IMAGE_BYTES:
        raise ValueError("Image content exceeds the 50 MiB limit.")

    try:
        with PillowImage.open(BytesIO(image_data)) as image:
            detected_format = image.format
            image.verify()
    except (UnidentifiedImageError, OSError) as error:
        raise ValueError("Decoded content is not a valid supported image.") from error

    expected_format = ALLOWED_FORMATS[Path(name).suffix.lower()]
    if detected_format != expected_format:
        raise ValueError(
            f"Image content is {detected_format}, but the filename expects "
            f"{expected_format}."
        )
    return image_data


def _write_image_atomically(image_path: Path, image_data: bytes) -> None:
    temporary_path = image_path.with_name(
        f".{image_path.name}.{uuid4().hex}.tmp"
    )
    try:
        temporary_path.write_bytes(image_data)
        temporary_path.replace(image_path)
    finally:
        temporary_path.unlink(missing_ok=True)


@mcp.tool()
def list_images() -> list[dict[str, int | str]]:
    """List supported image files currently stored in Luna Vault."""
    return [
        {
            "name": path.name,
            "size_bytes": path.stat().st_size,
            "format": ALLOWED_FORMATS[path.suffix.lower()],
        }
        for path in sorted(IMAGE_DIR.iterdir())
        if (
            path.is_file()
            and not path.is_symlink()
            and path.suffix.lower() in ALLOWED_FORMATS
        )
    ]


@mcp.tool()
def view_image(name: str) -> MCPImage:
    """Return a stored image as MCP image content."""
    image_path = _safe_image_path(name)
    if not image_path.is_file():
        raise FileNotFoundError(f"Image {name!r} was not found.")
    return MCPImage(path=image_path)


@mcp.tool()
def add_image(name: str, content_base64: str) -> dict[str, str | int]:
    """Add a new base64-encoded image; fail if the name already exists."""
    image_path = _safe_image_path(name)
    if image_path.exists():
        raise FileExistsError(
            f"Image {name!r} already exists; use modify_image to replace it."
        )

    image_data = _decode_and_validate_image(name, content_base64)
    _write_image_atomically(image_path, image_data)
    return {
        "status": "created",
        "stored_name": image_path.name,
        "size_bytes": len(image_data),
    }


@mcp.tool()
def modify_image(name: str, content_base64: str) -> dict[str, str | int]:
    """Replace an existing image with validated base64-encoded content."""
    image_path = _safe_image_path(name)
    if not image_path.is_file():
        raise FileNotFoundError(f"Image {name!r} was not found.")

    image_data = _decode_and_validate_image(name, content_base64)
    _write_image_atomically(image_path, image_data)
    return {
        "status": "modified",
        "stored_name": image_path.name,
        "size_bytes": len(image_data),
    }


@mcp.tool()
def remove_image(name: str) -> dict[str, str]:
    """Remove one stored image by its exact vault filename."""
    image_path = _safe_image_path(name)
    if not image_path.is_file():
        raise FileNotFoundError(f"Image {name!r} was not found.")

    image_path.unlink()
    return {"status": "deleted", "removed_name": image_path.name}


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
