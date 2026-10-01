from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP, Image as MCPImage
from starlette.requests import Request
from starlette.responses import JSONResponse

from config import AppConfig
from database import MetadataRepository
from vault import ImageVaultService
from vision import OllamaVisionAnalyzer


class LunaVaultMCP:
    def __init__(self, vault: ImageVaultService) -> None:
        self.vault = vault
        self.mcp = FastMCP("Luna Vault", host="0.0.0.0", port=8000)
        self._register_tools()
        self._register_routes()

    def _register_tools(self) -> None:
        vault = self.vault

        @self.mcp.tool()
        def list_images() -> list[dict[str, Any]]:
            """List stored images with persisted captions and tags."""
            return vault.metadata()

        @self.mcp.tool()
        def view_image(name: str) -> MCPImage:
            """Return a stored image as MCP image content."""
            path = vault.safe_path(name)
            if not path.is_file():
                raise FileNotFoundError(f"Image {name!r} was not found.")
            return MCPImage(path=path)

        @self.mcp.tool()
        def add_image(name: str, content_base64: str) -> dict[str, Any]:
            """Analyze and add an image, persisting its caption and tags."""
            return {
                "status": "created",
                **vault.ingest_base64(name, content_base64, replace=False),
            }

        @self.mcp.tool()
        def modify_image(name: str, content_base64: str) -> dict[str, Any]:
            """Analyze and atomically replace an image and its metadata."""
            return {
                "status": "modified",
                **vault.ingest_base64(name, content_base64, replace=True),
            }

        @self.mcp.tool()
        def remove_image(name: str) -> dict[str, str]:
            """Remove an image and its persisted metadata consistently."""
            return vault.remove(name)

        @self.mcp.tool()
        def search_images(
            query: str = "",
            tags: list[str] | None = None,
            match_all_tags: bool = False,
            limit: int = 50,
            offset: int = 0,
        ) -> dict[str, Any]:
            """Search persisted captions/tags without opening image files."""
            return vault.search(query, tags, match_all_tags, limit, offset)

        @self.mcp.tool()
        def backfill_metadata() -> dict[str, Any]:
            """Analyze files missing current metadata; idempotent by hash/model."""
            return vault.backfill()

    def _register_routes(self) -> None:
        vault = self.vault

        @self.mcp.custom_route("/api/metadata", methods=["GET"])
        async def metadata_route(request: Request) -> JSONResponse:
            del request
            return JSONResponse({"images": vault.metadata()})

        @self.mcp.custom_route("/api/images", methods=["POST"])
        async def upload_route(request: Request) -> JSONResponse:
            try:
                payload = await request.json()
                result = vault.ingest_base64(
                    payload["name"], payload["content_base64"], replace=False
                )
                return JSONResponse({"status": "created", **result}, status_code=201)
            except Exception as error:
                return JSONResponse({"error": str(error)}, status_code=400)

        @self.mcp.custom_route("/api/images/{name}", methods=["DELETE"])
        async def delete_route(request: Request) -> JSONResponse:
            try:
                return JSONResponse(vault.remove(request.path_params["name"]))
            except Exception as error:
                return JSONResponse({"error": str(error)}, status_code=400)

    def run(self) -> None:
        self.mcp.run(transport="streamable-http")


def build_server() -> LunaVaultMCP:
    config = AppConfig.from_env()
    repository = MetadataRepository(config)
    repository.initialize()
    analyzer = OllamaVisionAnalyzer(config)
    vault = ImageVaultService(
        config,
        repository,
        analyzer,
    )
    return LunaVaultMCP(vault)


server = build_server()
mcp = server.mcp

if __name__ == "__main__":
    server.run()
