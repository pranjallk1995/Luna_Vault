import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP


IMAGE_DIR = Path(os.getenv("IMAGE_DIR", "/data/images"))
mcp = FastMCP("Luna Vault", host="0.0.0.0", port=8000)


@mcp.tool()
def list_images() -> list[dict[str, int | str]]:
    """List image files currently stored in the shared Luna Vault volume."""
    return [
        {"name": path.name, "size_bytes": path.stat().st_size}
        for path in sorted(IMAGE_DIR.iterdir())
        if path.is_file()
    ]


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
