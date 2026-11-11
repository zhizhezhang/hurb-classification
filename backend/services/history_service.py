"""SQLite persistence and constrained image storage for recognition history."""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from backend.api.predict import PredictionData, decode_image
from backend.schemas.history import HistoryPage, HistoryRecord


SCHEMA = """
CREATE TABLE IF NOT EXISTS recognition_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    image_path TEXT NOT NULL UNIQUE,
    predicted_class TEXT NOT NULL,
    confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    top3_json TEXT NOT NULL,
    inference_time_ms REAL NOT NULL CHECK (inference_time_ms >= 0),
    model_version TEXT NOT NULL
)
"""
LOGGER = logging.getLogger(__name__)
DELETE_MARKER = re.compile(r"\.([0-9a-f]{32}\.(?:jpg|png))\.[0-9a-f]{32}\.deleting")


class UnsafeImagePath(ValueError):
    """A stored image path could escape the configured upload directory."""


class ImageMissing(FileNotFoundError):
    """The database record exists but its image is absent."""


class HistoryStore:
    def __init__(self, db_path: Path, uploads_dir: Path, class_to_idx: dict[str, int]):
        self.db_path = db_path.resolve()
        self.uploads_dir = uploads_dir.resolve()
        self.class_names = frozenset(class_to_idx)
        if len(self.class_names) != 18:
            raise ValueError("History store requires the deployed 18-class mapping")

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        if not self.uploads_dir.is_dir():
            raise RuntimeError("Upload destination is not a directory")
        with closing(self._connect()) as connection, connection:
            connection.execute(SCHEMA)
        self._recover_deletions()

    def _recover_deletions(self) -> None:
        """Resolve interrupted image deletions according to the committed row state."""
        with closing(self._connect()) as connection:
            for temporary in self.uploads_dir.glob(".*.deleting"):
                match = DELETE_MARKER.fullmatch(temporary.name)
                if match is None or temporary.is_symlink():
                    continue
                image_path = match.group(1)
                image = self._image_file(image_path)
                exists = connection.execute(
                    "SELECT 1 FROM recognition_history WHERE image_path = ?", (image_path,)
                ).fetchone() is not None
                if exists and not image.exists():
                    os.replace(temporary, image)
                else:
                    temporary.unlink()

    def _image_file(self, image_path: str) -> Path:
        # The database stores only our generated filename, never a client path.
        filename = Path(image_path)
        if filename.name != image_path or filename.suffix.lower() not in {".jpg", ".png"}:
            raise UnsafeImagePath("Stored image path is invalid")
        stem = filename.stem
        if len(stem) != 32 or any(char not in "0123456789abcdef" for char in stem):
            raise UnsafeImagePath("Stored image filename is invalid")
        candidate = self.uploads_dir / image_path
        if candidate.is_symlink() or candidate.resolve().parent != self.uploads_dir:
            raise UnsafeImagePath("Stored image path leaves the upload directory")
        return candidate

    @staticmethod
    def _record(row: sqlite3.Row) -> HistoryRecord:
        record_id = row["id"]
        return HistoryRecord(
            id=record_id,
            created_at=row["created_at"],
            image_url=f"/api/history/{record_id}/image",
            predicted_class=row["predicted_class"],
            confidence=row["confidence"],
            top3=json.loads(row["top3_json"]),
            inference_time_ms=row["inference_time_ms"],
            model_version=row["model_version"],
        )

    def create(self, image_bytes: bytes, prediction: PredictionData) -> HistoryRecord:
        """Internal write operation; no public history creation endpoint exists."""
        if prediction.predicted_class not in self.class_names:
            raise ValueError("Predicted class is not in the deployed model mapping")
        if prediction.top3[0].class_name != prediction.predicted_class or any(
            item.class_name not in self.class_names for item in prediction.top3
        ):
            raise ValueError("Top-3 classes differ from the deployed model mapping")
        if prediction.confidence != prediction.top3[0].probability:
            raise ValueError("Top-1 confidence differs from Top-3")

        # Reuse exactly the upload validator used by POST /api/predict.
        decode_image(image_bytes)
        suffix = ".png" if image_bytes.startswith(b"\x89PNG\r\n\x1a\n") else ".jpg"
        image_path = f"{uuid.uuid4().hex}{suffix}"
        destination = self._image_file(image_path)
        created = False
        created_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        top3_json = json.dumps([item.model_dump() for item in prediction.top3], ensure_ascii=False)
        try:
            with destination.open("xb") as output:
                created = True
                output.write(image_bytes)
            with closing(self._connect()) as connection, connection:
                cursor = connection.execute(
                    """INSERT INTO recognition_history
                       (created_at, image_path, predicted_class, confidence, top3_json,
                        inference_time_ms, model_version) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (created_at, image_path, prediction.predicted_class, prediction.confidence, top3_json,
                     prediction.inference_time_ms, prediction.model_version),
                )
                record_id = cursor.lastrowid
        except Exception:
            if created:
                destination.unlink(missing_ok=True)
            raise
        if not destination.is_file():
            self.delete(record_id)
            raise ImageMissing("Saved history image is missing")
        return HistoryRecord(
            id=record_id, created_at=created_at,
            image_url=f"/api/history/{record_id}/image",
            predicted_class=prediction.predicted_class,
            confidence=prediction.confidence,
            top3=prediction.top3,
            inference_time_ms=prediction.inference_time_ms,
            model_version=prediction.model_version,
        )

    def get(self, record_id: int) -> HistoryRecord | None:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT * FROM recognition_history WHERE id = ?", (record_id,)).fetchone()
        return self._record(row) if row is not None else None

    def list_page(self, page: int, page_size: int) -> HistoryPage:
        with closing(self._connect()) as connection:
            total = connection.execute("SELECT COUNT(*) FROM recognition_history").fetchone()[0]
            rows = connection.execute(
                "SELECT * FROM recognition_history ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
                (page_size, (page - 1) * page_size),
            ).fetchall()
        return HistoryPage(total=total, page=page, page_size=page_size,
                           items=[self._record(row) for row in rows])

    def image(self, record_id: int) -> tuple[Path, str] | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT image_path FROM recognition_history WHERE id = ?", (record_id,)
            ).fetchone()
        if row is None:
            return None
        path = self._image_file(row["image_path"])
        if not path.is_file():
            raise ImageMissing("Stored image is missing")
        return path, "image/png" if path.suffix == ".png" else "image/jpeg"

    def delete(self, record_id: int) -> bool:
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT image_path FROM recognition_history WHERE id = ?", (record_id,)
            ).fetchone()
            if row is None:
                connection.rollback()
                return False
            image = self._image_file(row["image_path"])
            temporary = self.uploads_dir / f".{image.name}.{uuid.uuid4().hex}.deleting"
            moved = False
            try:
                if image.is_file():
                    os.replace(image, temporary)
                    moved = True
                connection.execute("DELETE FROM recognition_history WHERE id = ?", (record_id,))
                connection.commit()
            except Exception:
                connection.rollback()
                if moved:
                    os.replace(temporary, image)
                raise
        if moved:
            try:
                temporary.unlink()
            except OSError:
                # The committed row is gone; startup recovery removes this orphan.
                LOGGER.warning("Deferred cleanup of a deleted history image")
        return True
