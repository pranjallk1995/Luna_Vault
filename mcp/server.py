"""FastMCP tools and HTTP routes for Luna Vault."""

import base64
import ipaddress
import socket
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

import httpx
import uvicorn

from mcp.server.fastmcp import FastMCP, Image as MCPImage
from mcp.types import BlobResourceContents, EmbeddedResource
from PIL import Image as PillowImage
from PIL import ImageDraw, ImageOps
from starlette.requests import Request
from starlette.responses import JSONResponse

from config import AppConfig
from database import MetadataRepository
from security import HiddenVaultAuth
from vault import ImageVaultService
from vision import OllamaVisionAnalyzer

MAX_FETCH_IMAGES = 20
MAX_FETCH_BYTES = 50 * 1024 * 1024
DISPLAY_MAX_EDGE = 768
MAX_UPLOAD_REDIRECTS = 3


def _validate_public_https_url(url: str) -> None:
    """Reject non-HTTPS and private-network upload sources."""
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("image_url must be a public HTTPS URL or image data URL.")
    try:
        addresses = {
            entry[4][0]
            for entry in socket.getaddrinfo(parsed.hostname, parsed.port or 443)
        }
    except socket.gaierror as error:
        raise ValueError("image_url hostname could not be resolved.") from error
    if not addresses or any(
        not ipaddress.ip_address(value).is_global for value in addresses
    ):
        raise ValueError("image_url must resolve only to public internet addresses.")


def _image_source_base64(content_base64: str | None, image_url: str | None) -> str:
    """Return Base64 image bytes from exactly one supported chat source."""
    supplied = sum(
        value is not None and bool(value.strip())
        for value in (content_base64, image_url)
    )
    if supplied != 1:
        raise ValueError(
            "Provide exactly one of content_base64, image_url, or file_path."
        )
    if content_base64 and content_base64.strip():
        return content_base64.strip()

    source = image_url.strip()
    if source.startswith("data:image/"):
        header, separator, payload = source.partition(",")
        if not separator or not header.casefold().endswith(";base64"):
            raise ValueError("Image data URLs must contain Base64-encoded data.")
        return payload

    current = source
    with httpx.Client(timeout=30.0, follow_redirects=False) as client:
        for redirect_count in range(MAX_UPLOAD_REDIRECTS + 1):
            _validate_public_https_url(current)
            with client.stream("GET", current) as response:
                if response.is_redirect:
                    if redirect_count == MAX_UPLOAD_REDIRECTS:
                        raise ValueError("image_url redirected too many times.")
                    location = response.headers.get("location")
                    if not location:
                        raise ValueError("image_url returned an invalid redirect.")
                    current = str(response.url.join(location))
                    continue
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").casefold()
                if not content_type.startswith("image/"):
                    raise ValueError("image_url did not return image content.")
                data = bytearray()
                for chunk in response.iter_bytes():
                    data.extend(chunk)
                    if len(data) > MAX_FETCH_BYTES:
                        raise ValueError("Image content exceeds the 50 MiB limit.")
                if not data:
                    raise ValueError("image_url returned an empty image.")
                return base64.b64encode(data).decode("ascii")
    raise ValueError("image_url could not be downloaded.")


def _selected_visible_paths(vault: ImageVaultService, names: list[str]) -> list[Path]:
    """Resolve a bounded, deduplicated batch of visible image paths."""
    if not isinstance(names, list) or not names:
        raise ValueError("Provide at least one image name.")
    if any(not isinstance(name, str) for name in names):
        raise ValueError("Every image name must be a string.")
    unique_names = list(dict.fromkeys(names))
    if len(unique_names) > MAX_FETCH_IMAGES:
        raise ValueError(f"Fetch at most {MAX_FETCH_IMAGES} images at a time.")
    paths = [vault.visible_path(name) for name in unique_names]
    if sum(path.stat().st_size for path in paths) > MAX_FETCH_BYTES:
        raise ValueError("Selected images exceed the 50 MiB fetch limit.")
    return paths


def _preview_image(path: Path, max_size: tuple[int, int]) -> PillowImage.Image:
    """Load one image with corrected orientation and a bounded RGB canvas."""
    with PillowImage.open(path) as source:
        image = ImageOps.exif_transpose(source)
        image.thumbnail(max_size, PillowImage.Resampling.LANCZOS)
        if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
            rgba = image.convert("RGBA")
            flattened = PillowImage.new("RGB", rgba.size, "white")
            flattened.paste(rgba, mask=rgba.getchannel("A"))
            return flattened
        return image.convert("RGB")


def _jpeg_content(image: PillowImage.Image) -> MCPImage:
    """Encode one prepared preview as compact MCP JPEG image content."""
    preview = BytesIO()
    image.save(preview, format="JPEG", quality=82, optimize=True)
    return MCPImage(data=preview.getvalue(), format="jpeg")


def _display_images(paths: list[Path]) -> list[MCPImage]:
    """Return one preview or one labeled contact sheet for reliable chat display."""
    if len(paths) == 1:
        image = _preview_image(paths[0], (DISPLAY_MAX_EDGE, DISPLAY_MAX_EDGE))
        return [_jpeg_content(image)]

    columns = 2
    tile_width, image_height, label_height = 512, 384, 40
    rows = (len(paths) + columns - 1) // columns
    sheet = PillowImage.new(
        "RGB", (columns * tile_width, rows * (image_height + label_height)), "#111827"
    )
    draw = ImageDraw.Draw(sheet)
    for index, path in enumerate(paths):
        image = _preview_image(path, (tile_width - 24, image_height - 24))
        column, row = index % columns, index // columns
        left = column * tile_width + (tile_width - image.width) // 2
        top = row * (image_height + label_height) + (image_height - image.height) // 2
        sheet.paste(image, (left, top))
        label = path.name if len(path.name) <= 58 else f"{path.name[:55]}..."
        draw.text(
            (
                column * tile_width + 12,
                row * (image_height + label_height) + image_height + 10,
            ),
            label,
            fill="white",
        )
    return [_jpeg_content(sheet)]


def _zip_resource(paths: list[Path]) -> EmbeddedResource:
    """Package selected images as an in-memory downloadable MCP resource."""
    archive = BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in paths:
            bundle.write(path, arcname=path.name)
    return EmbeddedResource(
        type="resource",
        resource=BlobResourceContents(
            uri="file:///luna-vault/luna-vault-images.zip",
            mimeType="application/zip",
            blob=base64.b64encode(archive.getvalue()).decode("ascii"),
        ),
    )


class LunaVaultMCP:
    """Register MCP tools and authenticated UI-facing HTTP routes."""

    def __init__(self, vault: ImageVaultService, auth: HiddenVaultAuth) -> None:
        """Initialize this component and its required dependencies."""
        self.vault = vault
        self.auth = auth
        self.mcp = FastMCP("Luna Vault", host="0.0.0.0", port=8000)
        self._register_tools()
        self._register_routes()

    def _register_tools(self) -> None:
        """Register the public MCP image-management tools."""
        vault = self.vault

        @self.mcp.tool()
        def list_images() -> list[dict[str, Any]]:
            """List non-hidden stored images with persisted captions and tags."""
            return vault.metadata()

        @self.mcp.tool()
        def view_image(name: str) -> MCPImage:
            """Return a displayable preview of one non-hidden stored image."""
            path = vault.visible_path(name)
            return _display_images([path])[0]

        @self.mcp.tool()
        def fetch_images(
            names: list[str], delivery: Literal["display", "zip"] = "display"
        ):
            """Fetch visible images for chat display or as a downloadable ZIP.

            Use exact filenames returned by list_images or search_images. The display
            mode returns one preview or a labeled contact sheet; zip returns the
            original files in one embedded ZIP resource.
            Hidden images are never available through this public tool.
            """
            paths = _selected_visible_paths(vault, names)
            if delivery == "display":
                return _display_images(paths)
            return _zip_resource(paths)

        @self.mcp.tool()
        def add_image(name: str, content_base64: str) -> dict[str, Any]:
            """Analyze and add an image, persisting its caption and tags."""
            return {
                "status": "created",
                **vault.ingest_base64(name, content_base64, replace=False),
            }

        @self.mcp.tool()
        def upload_image(
            name: str,
            content_base64: str | None = None,
            image_url: str | None = None,
        ) -> dict[str, Any]:
            """Upload an image from a ChatGPT attachment, Base64, or HTTPS URL.

            Provide exactly one of:
            - content_base64: Base64-encoded image data
            - image_url: Public HTTPS image URL or data URL

            ChatGPT attachment paths may be converted to temporary
            HTTPS URLs by the tool infrastructure.

            Maximum image size: 50 MiB.
            """
            return {
                "status": "created",
                **vault.ingest_base64(
                    name,
                    _image_source_base64(
                        content_base64,
                        image_url,
                    ),
                    replace=False,
                ),
            }

        @self.mcp.tool()
        def modify_image(name: str, content_base64: str) -> dict[str, Any]:
            """Analyze and atomically replace a non-hidden image and its metadata."""
            return {
                "status": "modified",
                **vault.ingest_base64(name, content_base64, replace=True),
            }

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
        def rename_image(name: str, new_name: str) -> dict[str, Any]:
            """Rename a visible image file and its persisted metadata identifier."""
            return vault.rename(name, new_name)

        @self.mcp.tool()
        def set_favorite_images(names: list[str], favorite: bool) -> dict[str, Any]:
            """Add or remove visible images from Favorites.

            Use exact filenames returned by list_images or search_images. Set
            favorite to true to add the images or false to remove them.
            """
            return vault.set_favorite(names, favorite)

        @self.mcp.tool()
        def remove_image(name: str) -> dict[str, str]:
            """Remove a non-hidden image and its persisted metadata consistently."""
            return vault.remove(name)

        @self.mcp.tool()
        def search_images(
            query: str = "",
            tags: list[str] | None = None,
            match_all_tags: bool = False,
            limit: int = 50,
            offset: int = 0,
        ) -> dict[str, Any]:
            """Search non-hidden persisted captions/tags without opening image files."""
            return vault.search(query, tags, match_all_tags, limit, offset)

        @self.mcp.tool()
        def backfill_metadata() -> dict[str, Any]:
            """Analyze files missing current metadata; idempotent by hash/model."""
            return vault.backfill()

    @staticmethod
    def _token(request: Request) -> str | None:
        """Extract the separate Hidden Vault session token."""
        return request.headers.get("X-Hidden-Vault-Token")

    @staticmethod
    async def _payload(request: Request) -> dict[str, Any]:
        """Parse and validate a JSON object request body."""
        value = await request.json()
        if not isinstance(value, dict):
            raise ValueError("Request body must be a JSON object.")
        return value

    @staticmethod
    def _error(error: Exception) -> JSONResponse:
        """Translate an application exception into a JSON error response."""
        status = 401 if isinstance(error, PermissionError) else 400
        return JSONResponse({"error": str(error)}, status_code=status)

    def _register_routes(self) -> None:
        """Register HTTP routes used by the Streamlit interface."""
        vault, auth = self.vault, self.auth

        @self.mcp.custom_route("/api/metadata", methods=["GET"])
        async def metadata_route(request: Request) -> JSONResponse:
            """Return visible image metadata to the UI."""
            del request
            return JSONResponse({"images": vault.metadata()})

        @self.mcp.custom_route("/api/images", methods=["POST"])
        async def upload_route(request: Request) -> JSONResponse:
            """Ingest an uploaded image and return its generated metadata."""
            try:
                payload = await self._payload(request)
                result = vault.ingest_base64(
                    payload["name"], payload["content_base64"], replace=False
                )
                return JSONResponse({"status": "created", **result}, status_code=201)
            except Exception as error:
                return self._error(error)

        @self.mcp.custom_route("/api/images/{name}", methods=["DELETE"])
        async def delete_route(request: Request) -> JSONResponse:
            """Delete one visible image requested by the UI."""
            try:
                return JSONResponse(vault.remove(request.path_params["name"]))
            except Exception as error:
                return self._error(error)

        @self.mcp.custom_route("/api/images/{name}/rename", methods=["POST"])
        async def rename_route(request: Request) -> JSONResponse:
            """Rename one visible image requested by the UI."""
            try:
                payload = await self._payload(request)
                return JSONResponse(
                    vault.rename(
                        request.path_params["name"], payload.get("new_name", "")
                    )
                )
            except Exception as error:
                return self._error(error)

        @self.mcp.custom_route("/api/images/{name}/metadata", methods=["POST"])
        async def update_metadata_route(request: Request) -> JSONResponse:
            """Edit one visible image caption and searchable tags from the UI."""
            try:
                payload = await self._payload(request)
                return JSONResponse(
                    {
                        "status": "metadata_updated",
                        **vault.update_metadata(
                            request.path_params["name"],
                            payload.get("caption"),
                            payload.get("add_tags"),
                            payload.get("remove_tags"),
                        ),
                    }
                )
            except Exception as error:
                return self._error(error)

        @self.mcp.custom_route("/api/favorites", methods=["GET"])
        async def favorites_route(request: Request) -> JSONResponse:
            """Return persisted visible favorites to the UI."""
            del request
            return JSONResponse({"images": vault.favorite_metadata()})

        @self.mcp.custom_route("/api/favorites", methods=["POST"])
        async def update_favorites_route(request: Request) -> JSONResponse:
            """Add or remove selected visible images from Favorites."""
            try:
                payload = await self._payload(request)
                favorite = payload.get("favorite")
                if not isinstance(favorite, bool):
                    raise ValueError("favorite must be true or false.")
                return JSONResponse(
                    vault.set_favorite(payload.get("names", []), favorite)
                )
            except Exception as error:
                return self._error(error)

        @self.mcp.custom_route("/api/hidden/status", methods=["GET"])
        async def hidden_status_route(request: Request) -> JSONResponse:
            """Report whether Hidden Vault access has been configured."""
            del request
            return JSONResponse({"configured": auth.configured()})

        @self.mcp.custom_route("/api/hidden/setup", methods=["POST"])
        async def hidden_setup_route(request: Request) -> JSONResponse:
            """Create Hidden Vault credentials and an authenticated session."""
            try:
                payload = await self._payload(request)
                token = auth.setup(
                    payload.get("password", ""), str(payload.get("pin", ""))
                )
                return JSONResponse({"token": token}, status_code=201)
            except Exception as error:
                return self._error(error)

        @self.mcp.custom_route("/api/hidden/login", methods=["POST"])
        async def hidden_login_route(request: Request) -> JSONResponse:
            """Authenticate a Hidden Vault password."""
            try:
                payload = await self._payload(request)
                return JSONResponse({"token": auth.login(payload.get("password", ""))})
            except Exception as error:
                return self._error(error)

        @self.mcp.custom_route("/api/hidden/reset", methods=["POST"])
        async def hidden_reset_route(request: Request) -> JSONResponse:
            """Reset the Hidden Vault password using the reset PIN."""
            try:
                payload = await self._payload(request)
                token = auth.reset(
                    str(payload.get("pin", "")), payload.get("new_password", "")
                )
                return JSONResponse({"token": token})
            except Exception as error:
                return self._error(error)

        @self.mcp.custom_route("/api/hidden/logout", methods=["POST"])
        async def hidden_logout_route(request: Request) -> JSONResponse:
            """Invalidate the current Hidden Vault session."""
            auth.logout(self._token(request))
            return JSONResponse({"status": "logged_out"})

        @self.mcp.custom_route("/api/hidden/images", methods=["GET"])
        async def hidden_images_route(request: Request) -> JSONResponse:
            """Return hidden image metadata to an authenticated UI."""
            try:
                auth.require(self._token(request))
                return JSONResponse({"images": vault.hidden_metadata()})
            except Exception as error:
                return self._error(error)

        @self.mcp.custom_route("/api/hidden/hide", methods=["POST"])
        async def hide_images_route(request: Request) -> JSONResponse:
            """Move selected visible images into the Hidden Vault."""
            try:
                auth.require(self._token(request))
                payload = await self._payload(request)
                return JSONResponse(vault.set_hidden(payload.get("names", []), True))
            except Exception as error:
                return self._error(error)

        @self.mcp.custom_route("/api/hidden/delete", methods=["POST"])
        async def delete_hidden_images_route(request: Request) -> JSONResponse:
            """Delete selected authenticated hidden images."""
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
            """Restore selected hidden images to the visible vault."""
            try:
                auth.require(self._token(request))
                payload = await self._payload(request)
                return JSONResponse(vault.set_hidden(payload.get("names", []), False))
            except Exception as error:
                return self._error(error)

    def run(self) -> None:
        """Serve Luna Vault over the streamable HTTP transport."""
        app = self.mcp.streamable_http_app()
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=8000,
        )


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
