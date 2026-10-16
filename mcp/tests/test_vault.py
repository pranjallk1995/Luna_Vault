"""Tests for test vault behavior."""

import base64
import sys
import tempfile
import unittest
from io import BytesIO
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).parents[1]))

from app.config import AppConfig
from app.vault import ImageVaultService
from app.vision import ImageAnalysis, OllamaVisionAnalyzer


class FakeRepository:
    """Provide an in-memory repository test double."""
    def __init__(self) -> None:
        """Initialize this component and its required dependencies."""
        self.rows = {}
        self.configured_base_url = ""

    def upsert(
        self,
        name,
        size_bytes,
        content_sha256,
        caption,
        tags,
        analysis_model,
        public_url=None,
    ):
        """Insert or replace one record in the test repository."""
        row = {
            "name": name,
            "size_bytes": size_bytes,
            "content_sha256": content_sha256,
            "caption": caption,
            "tags": tags,
            "analysis_model": analysis_model,
            "updated_at": "test",
            "hidden": self.rows.get(name, {}).get("hidden", False),
            "favorite": self.rows.get(name, {}).get("favorite", False),
            "public_url": public_url,
        }
        self.rows[name] = row
        return row

    def delete(self, name):
        """Delete one metadata record by filename."""
        self.rows.pop(name, None)

    def rename(self, name, new_name, public_url=None):
        """Rename one visible record while preserving its metadata."""
        if new_name in self.rows:
            raise FileExistsError(new_name)
        row = self.rows.get(name)
        if row is None or row.get("hidden", False):
            raise FileNotFoundError(name)
        row = {
            **self.rows.pop(name),
            "name": new_name,
            "public_url": public_url,
        }
        self.rows[new_name] = row
        return row

    def update_metadata(self, name, caption, tags, hidden=False):
        """Update caption and tags in the requested test collection."""
        if (
            name not in self.rows
            or self.rows[name].get("hidden", False) != hidden
        ):
            raise FileNotFoundError(name)
        self.rows[name]["caption"] = caption
        self.rows[name]["tags"] = tags
        return self.rows[name]

    def list_all(self, hidden=False):
        """Return test metadata filtered by hidden state."""
        if hidden is None:
            return list(self.rows.values())
        return [row for row in self.rows.values() if row.get("hidden", False) == hidden]

    def is_hidden(self, name):
        """Return whether the named image belongs to the Hidden Vault."""
        if name not in self.rows:
            raise FileNotFoundError(name)
        return self.rows[name].get("hidden", False)

    def set_hidden(self, names, hidden):
        """Persist hidden state for the supplied image names."""
        changed = []
        for name in names:
            if name in self.rows and self.rows[name].get("hidden", False) != hidden:
                self.rows[name]["hidden"] = hidden
                changed.append(name)
        return changed

    def list_favorites(self):
        """Return visible favorite records from the test repository."""
        return [
            row for row in self.rows.values()
            if row.get("favorite", False) and not row.get("hidden", False)
        ]

    def set_favorite(self, names, favorite):
        """Update favorite state in the test repository."""
        changed = []
        for name in names:
            row = self.rows.get(name)
            if row and not row.get("hidden", False) and row.get("favorite") != favorite:
                row["favorite"] = favorite
                changed.append(name)
        return changed

    def initialize_public_base_url(self, public_base_url):
        """Seed the in-memory public URL configuration once."""
        if not self.configured_base_url:
            self.configured_base_url = public_base_url
        for name, row in self.rows.items():
            row["public_url"] = (
                f"{self.configured_base_url}/api/public/images/{name}"
            )
        return self.configured_base_url

    def public_base_url(self):
        """Return the in-memory public URL configuration."""
        return self.configured_base_url

    def set_public_base_url(self, public_base_url):
        """Replace the in-memory public origin and refresh image URLs."""
        self.configured_base_url = public_base_url
        for name, row in self.rows.items():
            row["public_url"] = f"{public_base_url}/api/public/images/{name}"
        return len(self.rows)

    def search(self, query, tags, match_all, limit, offset):
        """Return matching visible metadata from the test repository."""
        matches = [
            {
                "name": row["name"],
                "caption": row["caption"],
                "tags": row["tags"],
                "updated_at": row["updated_at"],
            }
            for row in self.rows.values()
            if not row.get("hidden", False)
            and (
                query.rstrip("s") in row["caption"].lower()
                or any(query.rstrip("s") in tag for tag in row["tags"])
            )
        ]
        return len(matches), matches[offset : offset + limit]


class FakeAnalyzer:
    """Provide an in-memory analyzer test double."""
    model = "test-vision"

    def analyze(self, data):
        """Return deterministic image analysis for tests."""
        del data
        return ImageAnalysis(caption="A tabby cat on a sofa.", tags=["cat", "sofa"])

    @staticmethod
    def normalize_tags(tags):
        """Normalize tags deterministically for tests."""
        return [tag.lower() for tag in tags]


def png_payload(color="red"):
    """Create a small valid PNG payload for vault tests."""
    buffer = BytesIO()
    Image.new("RGB", (4, 3), color).save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


class ImageVaultServiceTests(unittest.TestCase):
    """Exercise ImageVaultService behavior."""
    def setUp(self):
        """Create isolated dependencies for each test case."""
        self.temp = tempfile.TemporaryDirectory()
        self.repository = FakeRepository()
        self.config = AppConfig(
            image_dir=Path(self.temp.name),
            database_url="postgresql://test",
            ollama_url="http://ollama:11434",
            vision_model="test-vision",
            public_base_url="https://vault.example.test/vault",
        )
        self.service = ImageVaultService(self.config, self.repository, FakeAnalyzer())

    def tearDown(self):
        """Release temporary resources created for a test case."""
        self.temp.cleanup()

    def test_vision_preprocessing_bounds_dimensions(self):
        """Verify vision preprocessing bounds dimensions."""
        raw = BytesIO()
        Image.new("RGB", (2400, 1600), "blue").save(raw, format="PNG")
        prepared = OllamaVisionAnalyzer.prepare_image(raw.getvalue())
        with Image.open(BytesIO(prepared)) as image:
            self.assertLessEqual(max(image.size), 1024)
            self.assertEqual(image.format, "JPEG")

    def test_ingest_persists_generated_metadata(self):
        """Verify ingest persists generated metadata."""
        result = self.service.ingest_base64("cat.png", png_payload())
        self.assertEqual(result["caption"], "A tabby cat on a sofa.")
        self.assertEqual(result["tags"], ["cat", "sofa"])
        self.assertTrue((Path(self.temp.name) / "cat.png").is_file())
        self.assertEqual(
            result["public_url"],
            "https://vault.example.test/vault/api/public/images/cat.png",
        )

    def test_public_url_rejects_hidden_images(self):
        """Ensure public URLs never bypass Hidden Vault access control."""
        self.service.ingest_base64("cat.png", png_payload())
        self.repository.rows["cat.png"]["hidden"] = True

        with self.assertRaises(PermissionError):
            self.service.public_url("cat.png")

    def test_public_base_url_update_regenerates_stored_urls(self):
        """Allow chat configuration changes without restarting the service."""
        self.service.ingest_base64("cat.png", png_payload())

        result = self.service.update_public_base_url(
            "https://new-device.example.test/vault/"
        )

        self.assertEqual(
            result,
            {
                "status": "public_base_url_updated",
                "public_base_url": "https://new-device.example.test/vault",
                "updated_image_count": 1,
            },
        )
        self.assertEqual(
            self.repository.rows["cat.png"]["public_url"],
            "https://new-device.example.test/vault/api/public/images/cat.png",
        )

    def test_public_base_url_rejects_non_https_values(self):
        """Reject origins that cannot safely expose images to ChatGPT."""
        with self.assertRaises(ValueError):
            self.service.update_public_base_url("http://localhost:18000/vault")

    def test_replacing_image_adds_ai_modified_tag(self):
        """Verify replacing image adds ai modified tag."""
        self.service.ingest_base64("cat.png", png_payload())
        result = self.service.ingest_base64(
            "cat.png", png_payload("blue"), replace=True
        )
        self.assertEqual(result["tags"], ["cat", "sofa", "ai modified"])
        self.assertEqual(result["tags"].count("ai modified"), 1)

    def test_remove_deletes_file_and_metadata(self):
        """Verify remove deletes file and metadata."""
        self.service.ingest_base64("cat.png", png_payload())
        self.service.remove("cat.png")
        self.assertFalse((Path(self.temp.name) / "cat.png").exists())
        self.assertNotIn("cat.png", self.repository.rows)

    def test_rename_preserves_file_and_metadata(self):
        """Verify rename moves the file and preserves generated metadata."""
        original = self.service.ingest_base64("cat.png", png_payload())
        self.service.set_favorite(["cat.png"], True)
        result = self.service.rename("cat.png", "favorite cat.png")
        self.assertEqual(result["status"], "renamed")
        self.assertEqual(result["old_name"], "cat.png")
        self.assertEqual(result["name"], "favorite cat.png")
        self.assertEqual(result["caption"], original["caption"])
        self.assertEqual(result["tags"], original["tags"])
        self.assertTrue(result["favorite"])
        self.assertFalse((Path(self.temp.name) / "cat.png").exists())
        self.assertTrue((Path(self.temp.name) / "favorite cat.png").is_file())

    def test_rename_rejects_collision_without_changing_source(self):
        """Verify rename never overwrites an existing vault image."""
        self.service.ingest_base64("cat.png", png_payload())
        self.service.ingest_base64("dog.png", png_payload("blue"))
        with self.assertRaises(FileExistsError):
            self.service.rename("cat.png", "dog.png")
        self.assertTrue((Path(self.temp.name) / "cat.png").is_file())
        self.assertIn("cat.png", self.repository.rows)

    def test_rename_rejects_extension_change(self):
        """Verify rename cannot make the filename disagree with image bytes."""
        self.service.ingest_base64("cat.png", png_payload())
        with self.assertRaises(ValueError):
            self.service.rename("cat.png", "cat.jpg")
        self.assertTrue((Path(self.temp.name) / "cat.png").is_file())

    def test_rename_rejects_unsafe_destination_name(self):
        """Verify rename rejects paths that could escape the vault directory."""
        self.service.ingest_base64("cat.png", png_payload())
        with self.assertRaises(ValueError):
            self.service.rename("cat.png", "../cat.png")
        self.assertTrue((Path(self.temp.name) / "cat.png").is_file())

    def test_rename_rejects_hidden_image(self):
        """Verify the visible rename operation cannot expose a hidden image."""
        self.service.ingest_base64("cat.png", png_payload())
        self.service.set_hidden(["cat.png"], True)
        with self.assertRaises(PermissionError):
            self.service.rename("cat.png", "renamed.png")
        self.assertTrue((Path(self.temp.name) / "cat.png").is_file())

    def test_rename_rolls_file_back_when_metadata_update_fails(self):
        """Verify a repository failure cannot leave a half-renamed file."""
        self.service.ingest_base64("cat.png", png_payload())
        original_rename = self.repository.rename
        self.repository.rename = lambda name, new_name, public_url=None: (
            _ for _ in ()
        ).throw(
            RuntimeError("database unavailable")
        )
        try:
            with self.assertRaises(RuntimeError):
                self.service.rename("cat.png", "renamed.png")
        finally:
            self.repository.rename = original_rename
        self.assertTrue((Path(self.temp.name) / "cat.png").is_file())
        self.assertFalse((Path(self.temp.name) / "renamed.png").exists())
        self.assertIn("cat.png", self.repository.rows)

    def test_natural_count_query_uses_metadata(self):
        """Verify natural count query uses metadata."""
        self.service.ingest_base64("cat.png", png_payload())
        result = self.service.search(
            "how many images are about cats?", None, False, 50, 0
        )
        self.assertEqual(result["normalized_query"], "cats")
        self.assertEqual(result["count"], 1)

    def test_update_metadata_adds_tag_without_reanalysis(self):
        """Verify update metadata adds tag without reanalysis."""
        self.service.ingest_base64("cat.png", png_payload())
        result = self.service.update_metadata("cat.png", add_tags=["Pet Portrait"])
        self.assertEqual(result["caption"], "A tabby cat on a sofa.")
        self.assertEqual(result["tags"], ["cat", "sofa", "pet portrait"])

    def test_update_metadata_allows_manual_tag_after_sixteen_model_tags(self):
        """Verify users can extend metadata that already has 16 generated tags."""
        self.service.ingest_base64("cat.png", png_payload())
        self.repository.rows["cat.png"]["tags"] = [
            f"generated tag {index}" for index in range(16)
        ]
        result = self.service.update_metadata("cat.png", add_tags=["favorite"])
        self.assertEqual(len(result["tags"]), 17)
        self.assertEqual(result["tags"][-1], "favorite")

    def test_update_metadata_changes_caption_and_removes_tag(self):
        """Verify update metadata changes caption and removes tag."""
        self.service.ingest_base64("cat.png", png_payload())
        result = self.service.update_metadata(
            "cat.png", caption="A relaxed indoor cat.", remove_tags=["sofa"]
        )
        self.assertEqual(result["caption"], "A relaxed indoor cat.")
        self.assertEqual(result["tags"], ["cat"])

    def test_update_metadata_rejects_hidden_images(self):
        """Verify update metadata rejects hidden images."""
        self.service.ingest_base64("cat.png", png_payload())
        self.service.set_hidden(["cat.png"], True)
        with self.assertRaises(PermissionError):
            self.service.update_metadata("cat.png", add_tags=["private"])

    def test_update_hidden_metadata_changes_caption_and_tags(self):
        """Verify authenticated hidden metadata can be edited explicitly."""
        self.service.ingest_base64("cat.png", png_payload())
        self.service.set_hidden(["cat.png"], True)
        result = self.service.update_hidden_metadata(
            "cat.png", caption="A private indoor cat.", add_tags=["Private"]
        )
        self.assertEqual(result["caption"], "A private indoor cat.")
        self.assertEqual(result["tags"], ["cat", "sofa", "private"])
        self.assertTrue(result["hidden"])

    def test_authenticated_hidden_remove_deletes_file_and_metadata(self):
        """Verify authenticated hidden remove deletes file and metadata."""
        self.service.ingest_base64("cat.png", png_payload())
        self.service.set_hidden(["cat.png"], True)
        result = self.service.remove_hidden("cat.png")
        self.assertEqual(result["status"], "deleted")
        self.assertFalse((Path(self.temp.name) / "cat.png").exists())
        self.assertNotIn("cat.png", self.repository.rows)

    def test_hidden_images_are_excluded_and_protected(self):
        """Verify hidden images are excluded and protected."""
        self.service.ingest_base64("cat.png", png_payload())
        self.service.set_hidden(["cat.png"], True)
        self.assertEqual(self.service.metadata(), [])
        self.assertEqual(len(self.service.hidden_metadata()), 1)
        with self.assertRaises(PermissionError):
            self.service.visible_path("cat.png")
        with self.assertRaises(PermissionError):
            self.service.remove("cat.png")
        result = self.service.search("cats", None, False, 50, 0)
        self.assertEqual(result["count"], 0)


    def test_favorites_are_persisted_and_hidden_images_are_excluded(self):
        """Verify favorites are persisted and hidden images are excluded."""
        self.service.ingest_base64("cat.png", png_payload())
        result = self.service.set_favorite(["cat.png"], True)
        self.assertEqual(result["status"], "favorited")
        self.assertEqual(result["names"], ["cat.png"])
        self.assertEqual(
            [item["name"] for item in self.service.favorite_metadata()],
            ["cat.png"],
        )
        self.service.set_hidden(["cat.png"], True)
        self.assertEqual(self.service.favorite_metadata(), [])

if __name__ == "__main__":
    unittest.main()
