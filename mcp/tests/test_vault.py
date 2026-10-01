import base64
import sys
import tempfile
import unittest
from io import BytesIO
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).parents[1]))

from config import AppConfig
from vault import ImageVaultService
from vision import ImageAnalysis, OllamaVisionAnalyzer


class FakeRepository:
    def __init__(self) -> None:
        self.rows = {}

    def upsert(self, name, size_bytes, content_sha256, caption, tags, analysis_model):
        row = {
            "name": name,
            "size_bytes": size_bytes,
            "content_sha256": content_sha256,
            "caption": caption,
            "tags": tags,
            "analysis_model": analysis_model,
            "updated_at": "test",
            "hidden": self.rows.get(name, {}).get("hidden", False),
        }
        self.rows[name] = row
        return row

    def delete(self, name):
        self.rows.pop(name, None)

    def list_all(self, hidden=False):
        if hidden is None:
            return list(self.rows.values())
        return [row for row in self.rows.values() if row.get("hidden", False) == hidden]

    def is_hidden(self, name):
        if name not in self.rows:
            raise FileNotFoundError(name)
        return self.rows[name].get("hidden", False)

    def set_hidden(self, names, hidden):
        changed = []
        for name in names:
            if name in self.rows and self.rows[name].get("hidden", False) != hidden:
                self.rows[name]["hidden"] = hidden
                changed.append(name)
        return changed

    def search(self, query, tags, match_all, limit, offset):
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
    model = "test-vision"

    def analyze(self, data):
        del data
        return ImageAnalysis(caption="A tabby cat on a sofa.", tags=["cat", "sofa"])

    @staticmethod
    def normalize_tags(tags):
        return [tag.lower() for tag in tags]


def png_payload(color="red"):
    buffer = BytesIO()
    Image.new("RGB", (4, 3), color).save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


class ImageVaultServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repository = FakeRepository()
        self.config = AppConfig(
            image_dir=Path(self.temp.name),
            database_url="postgresql://test",
            ollama_url="http://ollama:11434",
            vision_model="test-vision",
        )
        self.service = ImageVaultService(self.config, self.repository, FakeAnalyzer())

    def tearDown(self):
        self.temp.cleanup()

    def test_vision_preprocessing_bounds_dimensions(self):
        raw = BytesIO()
        Image.new("RGB", (2400, 1600), "blue").save(raw, format="PNG")
        prepared = OllamaVisionAnalyzer.prepare_image(raw.getvalue())
        with Image.open(BytesIO(prepared)) as image:
            self.assertLessEqual(max(image.size), 1024)
            self.assertEqual(image.format, "JPEG")

    def test_ingest_persists_generated_metadata(self):
        result = self.service.ingest_base64("cat.png", png_payload())
        self.assertEqual(result["caption"], "A tabby cat on a sofa.")
        self.assertEqual(result["tags"], ["cat", "sofa"])
        self.assertTrue((Path(self.temp.name) / "cat.png").is_file())

    def test_replacing_image_adds_ai_modified_tag(self):
        self.service.ingest_base64("cat.png", png_payload())
        result = self.service.ingest_base64(
            "cat.png", png_payload("blue"), replace=True
        )
        self.assertEqual(result["tags"], ["cat", "sofa", "ai modified"])
        self.assertEqual(result["tags"].count("ai modified"), 1)

    def test_remove_deletes_file_and_metadata(self):
        self.service.ingest_base64("cat.png", png_payload())
        self.service.remove("cat.png")
        self.assertFalse((Path(self.temp.name) / "cat.png").exists())
        self.assertNotIn("cat.png", self.repository.rows)

    def test_natural_count_query_uses_metadata(self):
        self.service.ingest_base64("cat.png", png_payload())
        result = self.service.search(
            "how many images are about cats?", None, False, 50, 0
        )
        self.assertEqual(result["normalized_query"], "cats")
        self.assertEqual(result["count"], 1)

    def test_hidden_images_are_excluded_and_protected(self):
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


if __name__ == "__main__":
    unittest.main()
