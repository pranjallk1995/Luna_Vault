"""Tests for MCP image delivery helpers."""

import asyncio
import base64
import sys
import tempfile
import unittest
import zipfile
from io import BytesIO
from pathlib import Path

from PIL import Image as PillowImage

sys.path.insert(0, str(Path(__file__).parents[1]))

from app.main import (
    DISPLAY_MAX_EDGE,
    MAX_FETCH_IMAGES,
    LunaVaultMCP,
    _display_images,
    _image_source_base64,
    _selected_visible_paths,
    _zip_resource,
)


class FakeVault:
    """Resolve test images while preserving visible-path errors."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.hidden = set()
        self.uploads = []
        self.favorite_updates = []

    def ingest_base64(self, name: str, content_base64: str, replace: bool = False):
        self.uploads.append((name, content_base64, replace))
        return {"name": name, "caption": "Uploaded in chat.", "tags": ["chat"]}

    def visible_path(self, name: str) -> Path:
        if name in self.hidden:
            raise PermissionError("Hidden images require authentication.")
        path = self.root / name
        if not path.is_file():
            raise FileNotFoundError(name)
        return path

    def set_favorite(self, names: list[str], favorite: bool):
        self.favorite_updates.append((names, favorite))
        return {
            "status": "favorited" if favorite else "unfavorited",
            "names": names,
            "count": len(names),
        }


class ImageDeliveryTests(unittest.TestCase):
    """Verify bounded selection and downloadable ZIP construction."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        PillowImage.new("RGB", (1200, 800), "red").save(self.root / "one.png")
        PillowImage.new("RGB", (640, 480), "blue").save(self.root / "two.jpg")
        self.vault = FakeVault(self.root)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_upload_image_delegates_chat_payload_to_ingestion(self) -> None:
        server = LunaVaultMCP(self.vault, object())
        tool = server.mcp._tool_manager.get_tool("upload_image")
        result = asyncio.run(
            tool.run({"name": "chat.png", "content_base64": "aW1hZ2U="})
        )
        self.assertEqual(result["status"], "created")
        self.assertEqual(result["name"], "chat.png")
        self.assertEqual(self.vault.uploads, [("chat.png", "aW1hZ2U=", False)])

    def test_view_image_returns_displayable_image_data(self) -> None:
        server = LunaVaultMCP(self.vault, object())
        tool = server.mcp._tool_manager.get_tool("view_image")
        result = asyncio.run(tool.run({"name": "one.png"}))
        content = result.to_image_content()
        self.assertEqual(content.mimeType, "image/jpeg")
        self.assertTrue(base64.b64decode(content.data))

    def test_upload_image_accepts_image_data_url(self) -> None:
        server = LunaVaultMCP(self.vault, object())
        tool = server.mcp._tool_manager.get_tool("upload_image")
        result = asyncio.run(
            tool.run(
                {
                    "name": "chat.png",
                    "image_url": "data:image/png;base64,aW1hZ2U=",
                }
            )
        )
        self.assertEqual(result["status"], "created")
        self.assertEqual(self.vault.uploads, [("chat.png", "aW1hZ2U=", False)])

    def test_upload_source_requires_exactly_one_input(self) -> None:
        with self.assertRaisesRegex(ValueError, "exactly one"):
            _image_source_base64(None, None)
        with self.assertRaisesRegex(ValueError, "exactly one"):
            _image_source_base64(
                "aW1hZ2U=", "data:image/png;base64,aW1hZ2U="
            )

    def test_set_favorite_images_adds_and_removes_from_chat(self) -> None:
        server = LunaVaultMCP(self.vault, object())
        tool = server.mcp._tool_manager.get_tool("set_favorite_images")

        added = asyncio.run(
            tool.run({"names": ["one.png", "two.jpg"], "favorite": True})
        )
        removed = asyncio.run(
            tool.run({"names": ["one.png"], "favorite": False})
        )

        self.assertEqual(added["status"], "favorited")
        self.assertEqual(added["count"], 2)
        self.assertEqual(removed["status"], "unfavorited")
        self.assertEqual(
            self.vault.favorite_updates,
            [(["one.png", "two.jpg"], True), (["one.png"], False)],
        )

    def test_selection_deduplicates_in_requested_order(self) -> None:
        paths = _selected_visible_paths(
            self.vault, ["two.jpg", "one.png", "two.jpg"]
        )
        self.assertEqual([path.name for path in paths], ["two.jpg", "one.png"])

    def test_selection_rejects_hidden_images(self) -> None:
        self.vault.hidden.add("one.png")
        with self.assertRaises(PermissionError):
            _selected_visible_paths(self.vault, ["one.png"])

    def test_selection_rejects_oversized_batches(self) -> None:
        with self.assertRaisesRegex(ValueError, str(MAX_FETCH_IMAGES)):
            _selected_visible_paths(
                self.vault, [f"image-{index}.png" for index in range(21)]
            )

    def test_single_display_returns_one_bounded_jpeg_preview(self) -> None:
        previews = _display_images([self.root / "one.png"])
        self.assertEqual(len(previews), 1)
        content = previews[0].to_image_content()
        self.assertEqual(content.mimeType, "image/jpeg")
        with PillowImage.open(BytesIO(base64.b64decode(content.data))) as image:
            self.assertLessEqual(max(image.size), DISPLAY_MAX_EDGE)

    def test_multiple_display_returns_one_contact_sheet(self) -> None:
        previews = _display_images([self.root / "one.png", self.root / "two.jpg"])
        self.assertEqual(len(previews), 1)
        content = previews[0].to_image_content()
        self.assertEqual(content.mimeType, "image/jpeg")
        with PillowImage.open(BytesIO(base64.b64decode(content.data))) as image:
            self.assertEqual(image.size, (1024, 424))

    def test_zip_resource_contains_selected_originals(self) -> None:
        resource = _zip_resource(
            [self.root / "one.png", self.root / "two.jpg"]
        ).resource
        self.assertEqual(resource.mimeType, "application/zip")
        with zipfile.ZipFile(BytesIO(base64.b64decode(resource.blob))) as bundle:
            self.assertEqual(bundle.namelist(), ["one.png", "two.jpg"])
            self.assertEqual(bundle.read("one.png"), (self.root / "one.png").read_bytes())
            self.assertEqual(bundle.read("two.jpg"), (self.root / "two.jpg").read_bytes())


if __name__ == "__main__":
    unittest.main()
