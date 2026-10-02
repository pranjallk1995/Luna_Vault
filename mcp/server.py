"""FastMCP tools and HTTP routes for Luna Vault."""

from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP, Image as MCPImage
from starlette.requests import Request
from starlette.responses import JSONResponse

from config import AppConfig
from database import MetadataRepository
from security import HiddenVaultAuth
from vault import ImageVaultService
from vision import OllamaVisionAnalyzer


class LunaVaultMCP:
    """Register MCP tools and authenticated UI-facing HTTP routes."""

    def __init__(self, vault: ImageVaultService, auth: HiddenVaultAuth) -> None:
        self.vault = vault
        self.auth = auth
        self.mcp = FastMCP("Luna Vault", host="0.0.0.0", port=8000)
        self._register_tools()
        self._register_routes()

    def _register_tools(self) -> None:
        vault = self.vault

        @self.mcp.tool()
        def list_images() -> list[dict[str, Any]]:
            """List non-hidden stored images with persisted captions and tags."""
            return vault.metadata()

        @self.mcp.tool()
        def view_image(name: str) -> MCPImage:
            """Return a non-hidden stored image as MCP image content."""
            path = vault.visible_path(name)
            return MCPImage(path=path)

        @self.mcp.tool()
        def add_image(name: str, content_base64: str) -> dict[str, Any]:
            """Analyze and add an image, persisting its caption and tags."""
            return {"status": "created", **vault.ingest_base64(name, content_base64, replace=False)}

        @self.mcp.tool()
        def modify_image(name: str, content_base64: str) -> dict[str, Any]:
            """Analyze and atomically replace a non-hidden image and its metadata."""
            return {"status": "modified", **vault.ingest_base64(name, content_base64, replace=True)}

        @self.mcp.tool()
        def update_image_metadata(
            name: str,
            caption: str | None = None,
            add_tags: list[str] | None = None,
            remove_tags: list[str] | None = None,
        ) -> dict[str, Any]:
            """Edit a visible image caption and add or remove searchable tags."""
            return {
                "status": "metadata_updated",
                **vault.update_metadata(name, caption, add_tags, remove_tags),
            }

        @self.mcp.tool()
        def remove_image(name: str) -> dict[str, str]:
            """Remove a non-hidden image and its persisted metadata consistently."""
            return vault.remove(name)

        @self.mcp.tool()
        def search_images(query: str = "", tags: list[str] | None = None,
                          match_all_tags: bool = False, limit: int = 50,
                          offset: int = 0) -> dict[str, Any]:
            """Search non-hidden persisted captions/tags without opening image files."""
            return vault.search(query, tags, match_all_tags, limit, offset)

        @self.mcp.tool()
        def backfill_metadata() -> dict[str, Any]:
            """Analyze files missing current metadata; idempotent by hash/model."""
            return vault.backfill()

    @staticmethod
    def _token(request: Request) -> str | None:
        header = request.headers.get("authorization", "")
        return header[7:] if header.lower().startswith("bearer ") else None

    @staticmethod
    async def _payload(request: Request) -> dict[str, Any]:
        value = await request.json()
        if not isinstance(value, dict):
            raise ValueError("Request body must be a JSON object.")
        return value

    @staticmethod
    def _error(error: Exception) -> JSONResponse:
        status = 401 if isinstance(error, PermissionError) else 400
        return JSONResponse({"error": str(error)}, status_code=status)

    def _register_routes(self) -> None:
        vault, auth = self.vault, self.auth

        @self.mcp.custom_route("/api/metadata", methods=["GET"])
        async def metadata_route(request: Request) -> JSONResponse:
            del request
            return JSONResponse({"images": vault.metadata()})

        @self.mcp.custom_route("/api/images", methods=["POST"])
        async def upload_route(request: Request) -> JSONResponse:
            try:
                payload = await self._payload(request)
                result = vault.ingest_base64(payload["name"], payload["content_base64"], replace=False)
                return JSONResponse({"status": "created", **result}, status_code=201)
            except Exception as error:
                return self._error(error)

        @self.mcp.custom_route("/api/images/{name}", methods=["DELETE"])
        async def delete_route(request: Request) -> JSONResponse:
            try:
                return JSONResponse(vault.remove(request.path_params["name"]))
            except Exception as error:
                return self._error(error)

        @self.mcp.custom_route("/api/hidden/status", methods=["GET"])
        async def hidden_status_route(request: Request) -> JSONResponse:
            del request
            return JSONResponse({"configured": auth.configured()})

        @self.mcp.custom_route("/api/hidden/setup", methods=["POST"])
        async def hidden_setup_route(request: Request) -> JSONResponse:
            try:
                payload = await self._payload(request)
                token = auth.setup(payload.get("password", ""), str(payload.get("pin", "")))
                return JSONResponse({"token": token}, status_code=201)
            except Exception as error:
                return self._error(error)

        @self.mcp.custom_route("/api/hidden/login", methods=["POST"])
        async def hidden_login_route(request: Request) -> JSONResponse:
            try:
                payload = await self._payload(request)
                return JSONResponse({"token": auth.login(payload.get("password", ""))})
            except Exception as error:
                return self._error(error)

        @self.mcp.custom_route("/api/hidden/reset", methods=["POST"])
        async def hidden_reset_route(request: Request) -> JSONResponse:
            try:
                payload = await self._payload(request)
                token = auth.reset(str(payload.get("pin", "")), payload.get("new_password", ""))
                return JSONResponse({"token": token})
            except Exception as error:
                return self._error(error)

        @self.mcp.custom_route("/api/hidden/logout", methods=["POST"])
        async def hidden_logout_route(request: Request) -> JSONResponse:
            auth.logout(self._token(request))
            return JSONResponse({"status": "logged_out"})

        @self.mcp.custom_route("/api/hidden/images", methods=["GET"])
        async def hidden_images_route(request: Request) -> JSONResponse:
            try:
                auth.require(self._token(request))
                return JSONResponse({"images": vault.hidden_metadata()})
            except Exception as error:
                return self._error(error)

        @self.mcp.custom_route("/api/hidden/hide", methods=["POST"])
        async def hide_images_route(request: Request) -> JSONResponse:
            try:
                auth.require(self._token(request))
                payload = await self._payload(request)
                return JSONResponse(vault.set_hidden(payload.get("names", []), True))
            except Exception as error:
                return self._error(error)

        @self.mcp.custom_route("/api/hidden/delete", methods=["POST"])
        async def delete_hidden_images_route(request: Request) -> JSONResponse:
            try:
                auth.require(self._token(request))
                payload = await self._payload(request)
                names = payload.get("names", [])
                if not isinstance(names, list) or not names:
                    raise ValueError("Select at least one hidden image.")
                deleted = [vault.remove_hidden(name) for name in dict.fromkeys(names)]
                return JSONResponse({"status": "deleted", "count": len(deleted)})
            except Exception as error:
                return self._error(error)

        @self.mcp.custom_route("/api/hidden/restore", methods=["POST"])
        async def restore_images_route(request: Request) -> JSONResponse:
            try:
                auth.require(self._token(request))
                payload = await self._payload(request)
                return JSONResponse(vault.set_hidden(payload.get("names", []), False))
            except Exception as error:
                return self._error(error)

    def run(self) -> None:
        """Serve Luna Vault over the streamable HTTP transport."""
        self.mcp.run(transport="streamable-http")


def build_server() -> LunaVaultMCP:
    """Compose validated configuration and concrete service dependencies."""
    config = AppConfig.from_env()
    repository = MetadataRepository(config)
    repository.initialize()
    analyzer = OllamaVisionAnalyzer(config)
    vault = ImageVaultService(config, repository, analyzer)
    return LunaVaultMCP(vault, HiddenVaultAuth(repository, config))


server = build_server()
mcp = server.mcp

if __name__ == "__main__":
    server.run()
