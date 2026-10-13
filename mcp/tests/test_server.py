"""Tests for MCP image delivery helpers."""

import base64
import sys
import tempfile
import unittest
import zipfile
from io import BytesIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from server import MAX_FETCH_IMAGES, _selected_visible_paths, _zip_resource


class FakeVault:
    """Resolve test images while preserving visible-path errors."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.hidden = set()

    def visible_path(self, name: str) -> Path:
        if name in self.hidden:
            raise PermissionError("Hidden images require authentication.")
        path = self.root / name
        if not path.is_file():
            raise FileNotFoundError(name)
        return path


class ImageDeliveryTests(unittest.TestCase):
    """Verify bounded selection and downloadable ZIP construction."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "one.png").write_bytes(b"first-image")
        (self.root / "two.jpg").write_bytes(b"second-image")
        self.vault = FakeVault(self.root)

    def tearDown(self) -> None:
        self.temp.cleanup()

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

    def test_zip_resource_contains_selected_images(self) -> None:
        resource = _zip_resource(
            [self.root / "one.png", self.root / "two.jpg"]
        ).resource
        self.assertEqual(resource.mimeType, "application/zip")
        with zipfile.ZipFile(BytesIO(base64.b64decode(resource.blob))) as bundle:
            self.assertEqual(bundle.namelist(), ["one.png", "two.jpg"])
            self.assertEqual(bundle.read("one.png"), b"first-image")
            self.assertEqual(bundle.read("two.jpg"), b"second-image")


if __name__ == "__main__":
    unittest.main()