import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

IMAGE_DIR = Path(os.getenv("IMAGE_DIR", "/data/images"))
IMAGE_DIR.mkdir(parents=True, exist_ok=True)

mcp = FastMCP("Luna Vault", host="0.0.0.0", port=8000)


@mcp.tool()
def list_images() -> list[dict[str, int | str]]:
    """List image files currently stored in the shared Luna Vault volume."""
    return [
        {"name": path.name, "size_bytes": path.stat().st_size}
        for path in sorted(IMAGE_DIR.iterdir())
        if path.is_file()
    ]


@mcp.tool()
def view_image(name: str) -> dict[str, str | int]:
    """View metadata for a specific image file by name."""
    path = IMAGE_DIR / name
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Image {name} not found")
    return {
        "name": path.name,
        "size_bytes": path.stat().st_size,
        "absolute_path": str(path.resolve()),
    }


@mcp.tool()
def add_image(name: str, content: bytes) -> dict[str, str]:
    """Add a new image file to the vault."""
    path = IMAGE_DIR / name
    with path.open("wb") as f:
        f.write(content)
    return {"status": "success", "stored_name": path.name}


@mcp.tool()
def remove_image(name: str) -> dict[str, str]:
    """Remove an image file from the vault by name."""
    path = IMAGE_DIR / name
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Image {name} not found")
    path.unlink()
    return {"status": "deleted", "removed_name": name}


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
