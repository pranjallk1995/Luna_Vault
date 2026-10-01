import base64
import binascii
import hashlib
import re
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import uuid4

from PIL import Image as PillowImage
from PIL import UnidentifiedImageError

from config import AppConfig
from database import MetadataRepository
from vision import OllamaVisionAnalyzer


class ImageVaultService:
    def __init__(
        self,
        config: AppConfig,
        repository: MetadataRepository,
        analyzer: OllamaVisionAnalyzer,
    ) -> None:
        self.config = config
        self.image_dir = config.image_dir
        self.repository = repository
        self.analyzer = analyzer
        self.image_dir.mkdir(parents=True, exist_ok=True)

    def safe_path(self, name: str) -> Path:
        if not name or Path(name).name != name or name in {".", ".."}:
            raise ValueError("Image name must be a plain filename without directories.")
        if Path(name).suffix.lower() not in self.config.allowed_formats:
            raise ValueError("Unsupported image extension.")
        root = self.image_dir.resolve()
        path = (self.image_dir / name).resolve()
        if path.parent != root:
            raise ValueError("Image path must remain inside the vault directory.")
        return path

    def decode_and_validate(self, name: str, content_base64: str) -> bytes:
        if len(content_base64) > self.config.max_base64_chars:
            raise ValueError("Image content exceeds the 50 MiB limit.")
        try:
            data = base64.b64decode(content_base64, validate=True)
        except (binascii.Error, ValueError) as error:
            raise ValueError("content_base64 must be valid base64 data.") from error
        if not data or len(data) > self.config.max_image_bytes:
            raise ValueError("Image content is empty or exceeds the 50 MiB limit.")
        try:
            with PillowImage.open(BytesIO(data)) as image:
                detected = image.format
                image.verify()
        except (UnidentifiedImageError, OSError) as error:
            raise ValueError("Decoded content is not a valid image.") from error
        expected = self.config.allowed_formats[Path(name).suffix.lower()]
        if detected != expected:
            raise ValueError(
                f"Image content is {detected}, filename expects {expected}."
            )
        return data

    @staticmethod
    def _atomic_write(path: Path, data: bytes) -> None:
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            temporary.write_bytes(data)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    def _persist_analysis(self, name: str, data: bytes) -> dict[str, Any]:
        analysis = self.analyzer.analyze(data)
        return self.repository.upsert(
            name=name,
            size_bytes=len(data),
            content_sha256=hashlib.sha256(data).hexdigest(),
            caption=analysis.caption,
            tags=analysis.tags,
            analysis_model=self.analyzer.model,
        )

    def ingest_base64(
        self, name: str, content_base64: str, replace: bool = False
    ) -> dict[str, Any]:
        data = self.decode_and_validate(name, content_base64)
        path = self.safe_path(name)
        exists = path.is_file()
        if replace and not exists:
            raise FileNotFoundError(f"Image {name!r} was not found.")
        if replace and self.repository.is_hidden(name):
            raise PermissionError("Hidden images require authentication.")
        if not replace and exists:
            raise FileExistsError(f"Image {name!r} already exists; use modify_image.")
        analysis = self.analyzer.analyze(data)
        tags = list(analysis.tags)
        if replace and "ai modified" not in tags:
            tags.append("ai modified")
        previous = path.read_bytes() if exists else None
        try:
            self._atomic_write(path, data)
            metadata = self.repository.upsert(
                name,
                len(data),
                hashlib.sha256(data).hexdigest(),
                analysis.caption,
                tags,
                self.analyzer.model,
            )
        except Exception:
            if previous is None:
                path.unlink(missing_ok=True)
            else:
                self._atomic_write(path, previous)
            raise
        return metadata

    def visible_path(self, name: str) -> Path:
        path = self.safe_path(name)
        if not path.is_file():
            raise FileNotFoundError(f"Image {name!r} was not found.")
        if self.repository.is_hidden(name):
            raise PermissionError("Hidden images require authentication.")
        return path

    def remove(self, name: str) -> dict[str, str]:
        path = self.visible_path(name)
        if not path.is_file():
            raise FileNotFoundError(f"Image {name!r} was not found.")
        tombstone = path.with_name(f".{path.name}.{uuid4().hex}.deleting")
        path.replace(tombstone)
        try:
            self.repository.delete(name)
        except Exception:
            tombstone.replace(path)
            raise
        tombstone.unlink(missing_ok=True)
        return {"status": "deleted", "removed_name": name}

    def metadata(self) -> list[dict[str, Any]]:
        return self.repository.list_all(hidden=False)

    def hidden_metadata(self) -> list[dict[str, Any]]:
        return self.repository.list_all(hidden=True)

    def set_hidden(self, names: list[str], hidden: bool) -> dict[str, Any]:
        if not isinstance(names, list) or not names:
            raise ValueError("Select at least one image.")
        clean_names = []
        for name in dict.fromkeys(names):
            path = self.safe_path(name)
            if not path.is_file():
                raise FileNotFoundError(f"Image {name!r} was not found.")
            clean_names.append(name)
        changed = self.repository.set_hidden(clean_names, hidden)
        return {
            "status": "hidden" if hidden else "restored",
            "names": changed,
            "count": len(changed),
        }

    def normalize_search_query(self, query: str) -> str:
        words = re.findall(r"[a-z0-9]+", query.lower())
        return " ".join(
            word for word in words if word not in self.config.search_stop_words
        )

    def search(
        self,
        query: str,
        tags: list[str] | None,
        match_all_tags: bool,
        limit: int,
        offset: int,
    ) -> dict[str, Any]:
        normalized_query = self.normalize_search_query(query)
        normalized_tags = self.analyzer.normalize_tags(tags) if tags else []
        if not normalized_query and not normalized_tags:
            raise ValueError("Provide a meaningful query or at least one tag.")
        limit = min(max(limit, 1), self.config.search_limit_max)
        offset = max(offset, 0)
        count, results = self.repository.search(
            normalized_query, normalized_tags, match_all_tags, limit, offset
        )
        return {
            "query": query,
            "normalized_query": normalized_query,
            "count": count,
            "results": results,
        }

    def backfill(self) -> dict[str, Any]:
        indexed = {item["name"]: item for item in self.repository.list_all(hidden=None)}
        analyzed, skipped = [], []
        for path in sorted(self.image_dir.iterdir()):
            if (
                not path.is_file()
                or path.is_symlink()
                or path.suffix.lower() not in self.config.allowed_formats
            ):
                continue
            data = path.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            existing = indexed.get(path.name)
            if (
                existing
                and existing["content_sha256"] == digest
                and existing["analysis_model"] == self.analyzer.model
            ):
                skipped.append(path.name)
                continue
            self._persist_analysis(path.name, data)
            analyzed.append(path.name)
        return {
            "analyzed_count": len(analyzed),
            "skipped_count": len(skipped),
            "analyzed": analyzed,
        }
