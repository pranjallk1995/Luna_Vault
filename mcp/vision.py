import base64
import re
from io import BytesIO

import httpx
from PIL import Image, ImageOps
from pydantic import BaseModel, Field

from config import AppConfig


class ImageAnalysis(BaseModel):
    caption: str = Field(min_length=3, max_length=500)
    tags: list[str] = Field(min_length=1, max_length=16)


class OllamaVisionAnalyzer:
    def __init__(self, config: AppConfig) -> None:
        self.base_url = config.ollama_url
        self.model = config.vision_model
        self.max_tags = config.max_tags

    def normalize_tags(self, tags: list[str]) -> list[str]:
        normalized = []
        for tag in tags:
            clean = re.sub(r"[^a-z0-9 -]+", "", tag.lower()).strip()
            clean = re.sub(r"\s+", " ", clean)
            if clean and clean not in normalized:
                normalized.append(clean[:60])
        if not normalized:
            raise ValueError("Vision analysis returned no usable tags.")
        return normalized[:self.max_tags]

    @staticmethod
    def prepare_image(image_data: bytes) -> bytes:
        """Bound vision input cost without changing the stored original."""
        with Image.open(BytesIO(image_data)) as source:
            frame = ImageOps.exif_transpose(source).convert("RGB")
            frame.thumbnail((1024, 1024))
            output = BytesIO()
            frame.save(output, format="JPEG", quality=88, optimize=True)
        return output.getvalue()

    def analyze(self, image_data: bytes) -> ImageAnalysis:
        image_data = self.prepare_image(image_data)
        schema = ImageAnalysis.model_json_schema()
        payload = {
            "model": self.model,
            "stream": False,
            "format": schema,
            "options": {"temperature": 0, "num_ctx": 8192},
            "messages": [{
                "role": "user",
                "content": (
                    "Analyze only the supplied image. Return a concise factual caption "
                    "and 5-12 lowercase searchable tags covering subjects, objects, "
                    "setting, colors, and style. Do not infer from a filename."
                ),
                "images": [base64.b64encode(image_data).decode("ascii")],
            }],
        }
        with httpx.Client(timeout=httpx.Timeout(300.0, connect=10.0)) as client:
            response = client.post(f"{self.base_url}/api/chat", json=payload)
            response.raise_for_status()
        analysis = ImageAnalysis.model_validate_json(
            response.json()["message"]["content"]
        )
        analysis.caption = analysis.caption.strip()
        analysis.tags = self.normalize_tags(analysis.tags)
        return analysis

