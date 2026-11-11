"""SQLite history and image safety checks without modifying live runtime data."""

from __future__ import annotations

import io
import json
import os
import sqlite3
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from PIL import Image

from backend.api.predict import PredictionData
from backend.core.config import PROJECT_ROOT
from backend.main import app
from backend.services.history_service import HistoryStore, ImageMissing


MAPPING = json.loads((PROJECT_ROOT / "reports/data_split/class_to_idx.json").read_text(encoding="utf-8"))
MODEL_PATH = PROJECT_ROOT / "models/convnext_tiny_best.pt"


def picture(format_name: str) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (12, 8), color=(100, 150, 40)).save(output, format=format_name)
    return output.getvalue()


def prediction() -> PredictionData:
    return PredictionData(
        predicted_class="人参", confidence=0.8,
        top3=[
            {"class_name": "人参", "probability": 0.8},
            {"class_name": "黄芪", "probability": 0.15},
            {"class_name": "当归", "probability": 0.05},
        ],
        inference_time_ms=12.5, model_version="test_model_version",
    )


class HistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app_temp = tempfile.TemporaryDirectory()
        cls.env_patch = patch.dict(os.environ, {
            "HERB_MODEL_PATH": str(MODEL_PATH), "HERB_DEVICE": "auto",
            "HERB_HISTORY_DB_PATH": str(Path(cls.app_temp.name) / "app.db"),
            "HERB_UPLOADS_DIR": str(Path(cls.app_temp.name) / "app_uploads"),
        })
        cls.env_patch.start()
        cls.client = TestClient(app)
        try:
            cls.client.__enter__()
            cls.original_store = app.state.history_store
        except Exception:
            cls.env_patch.stop()
            cls.app_temp.cleanup()
            raise

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.__exit__(None, None, None)
        cls.env_patch.stop()
        cls.app_temp.cleanup()

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.store = HistoryStore(root / "history.db", root / "uploads", MAPPING)
        self.store.initialize()
        app.state.history_store = self.store

    def tearDown(self) -> None:
        app.state.history_store = self.original_store
        self.temp.cleanup()

    def test_database_initialization_create_and_utc(self) -> None:
        with closing(sqlite3.connect(self.store.db_path)) as connection, connection:
            columns = {row[1] for row in connection.execute("PRAGMA table_info(recognition_history)")}
        self.assertEqual(columns, {"id", "created_at", "image_path", "predicted_class", "confidence",
                                   "top3_json", "inference_time_ms", "model_version"})
        record = self.store.create(picture("PNG"), prediction())
        self.assertEqual(record.id, 1)
        self.assertEqual(record.predicted_class, "人参")
        self.assertEqual(record.top3[0].probability, 0.8)
        self.assertEqual(datetime.fromisoformat(record.created_at).utcoffset().total_seconds(), 0)
        with closing(sqlite3.connect(self.store.db_path)) as connection, connection:
            row = connection.execute("SELECT image_path, top3_json FROM recognition_history").fetchone()
        self.assertRegex(row[0], r"^[0-9a-f]{32}\.png$")
        self.assertNotIn(str(self.store.uploads_dir), row[0])
        self.assertEqual(json.loads(row[1])[0]["class_name"], "人参")

    def test_list_sort_pagination_and_detail(self) -> None:
        records = [self.store.create(picture("PNG"), prediction()) for _ in range(3)]
        first = self.client.get("/api/history", params={"page": 1, "page_size": 2})
        self.assertEqual(first.status_code, 200, first.text)
        data = first.json()["data"]
        self.assertEqual((data["total"], data["page"], data["page_size"]), (3, 1, 2))
        self.assertEqual([item["id"] for item in data["items"]], [records[2].id, records[1].id])
        second = self.client.get("/api/history", params={"page": 2, "page_size": 2}).json()["data"]
        self.assertEqual([item["id"] for item in second["items"]], [records[0].id])
        self.assertEqual(self.client.get(f"/api/history/{records[0].id}").json()["data"]["top3"][1],
                         {"class_name": "黄芪", "probability": 0.15})
        self.assertEqual(self.client.get("/api/history", params={"page_size": 51}).status_code, 422)

    def test_image_read_and_delete(self) -> None:
        for format_name, media_type in (("PNG", "image/png"), ("JPEG", "image/jpeg")):
            with self.subTest(format=format_name):
                contents = picture(format_name)
                record = self.store.create(contents, prediction())
                response = self.client.get(f"/api/history/{record.id}/image")
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.headers["content-type"], media_type)
                self.assertEqual(response.content, contents)
                result = self.client.delete(f"/api/history/{record.id}")
                self.assertEqual(result.status_code, 200, result.text)
                self.assertEqual(result.json(), {"success": True, "data": {"id": record.id, "deleted": True}})
                self.assertEqual(self.client.delete(f"/api/history/{record.id}").status_code, 404)
                self.assertEqual(self.client.get(f"/api/history/{record.id}").status_code, 404)
                self.assertEqual(list(self.store.uploads_dir.iterdir()), [])

    def test_missing_image_and_missing_record(self) -> None:
        self.assertEqual(self.client.get("/api/history").json()["data"]["items"], [])
        self.assertEqual(self.client.get("/api/history/999").status_code, 404)
        self.assertEqual(self.client.get("/api/history/999/image").status_code, 404)
        record = self.store.create(picture("PNG"), prediction())
        with closing(sqlite3.connect(self.store.db_path)) as connection, connection:
            filename = connection.execute("SELECT image_path FROM recognition_history WHERE id = ?", (record.id,)).fetchone()[0]
        (self.store.uploads_dir / filename).unlink()
        response = self.client.get(f"/api/history/{record.id}/image")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Stored image is missing")
        self.assertEqual(self.client.delete(f"/api/history/{record.id}").status_code, 200)

    def test_path_traversal_and_sql_parameters(self) -> None:
        outside = Path(self.temp.name) / "outside.png"
        outside.write_bytes(picture("PNG"))
        with closing(sqlite3.connect(self.store.db_path)) as connection, connection:
            connection.execute(
                """INSERT INTO recognition_history
                   (created_at,image_path,predicted_class,confidence,top3_json,inference_time_ms,model_version)
                   VALUES (?,?,?,?,?,?,?)""",
                (datetime.now(timezone.utc).isoformat(), "../outside.png", "人参", 0.8,
                 json.dumps([item.model_dump() for item in prediction().top3]), 12.5, "test"),
            )
        response = self.client.get("/api/history/1/image")
        self.assertEqual(response.status_code, 500)
        self.assertNotIn(str(outside), response.text)
        self.assertEqual(self.client.delete("/api/history/1").status_code, 500)
        self.assertEqual(outside.read_bytes(), picture("PNG"))
        self.assertIsNone(self.store.get("1 OR 1=1"))
        self.assertEqual(self.client.get("/api/history/1%20OR%201=1").status_code, 422)
        with closing(sqlite3.connect(self.store.db_path)) as connection, connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM recognition_history").fetchone()[0], 1)

    def test_invalid_write_and_name_collision_preserve_existing_file(self) -> None:
        with self.assertRaises(HTTPException):
            self.store.create(b"not an image", prediction())
        invalid = prediction().model_copy(update={"predicted_class": "'; DROP TABLE recognition_history;--"})
        with self.assertRaises(ValueError):
            self.store.create(picture("PNG"), invalid)
        with patch("backend.services.history_service.uuid.uuid4") as uuid_mock:
            uuid_mock.return_value.hex = "a" * 32
            first = self.store.create(picture("PNG"), prediction())
            with self.assertRaises(FileExistsError):
                self.store.create(picture("PNG"), prediction())
        self.assertEqual(self.client.get(f"/api/history/{first.id}/image").content, picture("PNG"))
        self.assertEqual(self.client.get("/api/history").json()["data"]["total"], 1)

    def test_write_and_delete_failures_keep_consistent_state(self) -> None:
        with patch.object(self.store, "_connect", side_effect=sqlite3.OperationalError("database unavailable")):
            with self.assertRaises(sqlite3.OperationalError):
                self.store.create(picture("PNG"), prediction())
        self.assertEqual(list(self.store.uploads_dir.iterdir()), [])
        self.assertEqual(self.store.list_page(1, 10).total, 0)

        record = self.store.create(picture("PNG"), prediction())
        with patch("backend.services.history_service.os.replace", side_effect=OSError("image locked")):
            response = self.client.delete(f"/api/history/{record.id}")
        self.assertEqual(response.status_code, 500)
        self.assertIsNotNone(self.store.get(record.id))
        self.assertEqual(self.client.get(f"/api/history/{record.id}/image").status_code, 200)

    def test_image_disappearing_after_commit_removes_record(self) -> None:
        real_is_file = Path.is_file

        def remove_saved_image(path: Path) -> bool:
            if path.parent == self.store.uploads_dir and path.suffix == ".png":
                path.unlink(missing_ok=True)
                return False
            return real_is_file(path)

        with patch.object(Path, "is_file", remove_saved_image):
            with self.assertRaises(ImageMissing):
                self.store.create(picture("PNG"), prediction())
        self.assertEqual(self.store.list_page(1, 10).total, 0)
        self.assertEqual(list(self.store.uploads_dir.iterdir()), [])

    def test_interrupted_delete_recovers_on_startup(self) -> None:
        record = self.store.create(picture("PNG"), prediction())
        with closing(sqlite3.connect(self.store.db_path)) as connection, connection:
            filename = connection.execute("SELECT image_path FROM recognition_history WHERE id = ?", (record.id,)).fetchone()[0]
        image = self.store.uploads_dir / filename
        marker = self.store.uploads_dir / f".{filename}.{'b' * 32}.deleting"
        image.replace(marker)
        self.store.initialize()
        self.assertTrue(image.is_file())
        self.assertFalse(marker.exists())
        self.store.delete(record.id)
        marker.write_bytes(b"orphan")
        self.store.initialize()
        self.assertFalse(marker.exists())

    def test_runtime_is_ignored_and_existing_routes_remain(self) -> None:
        for filename in ("backend/runtime/history.db", "backend/runtime/uploads/sample.png"):
            result = subprocess.run(["git", "check-ignore", "--quiet", filename], cwd=PROJECT_ROOT, check=False)
            self.assertEqual(result.returncode, 0, filename)
        self.assertEqual(self.client.get("/api/health").status_code, 200)
        self.assertEqual(self.client.get("/api/herbs").json()["total"], 18)
        paths = self.client.get("/openapi.json").json()["paths"]
        self.assertIn("post", paths["/api/predict"])
        self.assertIn("get", paths["/api/history"])
        self.assertIn("delete", paths["/api/history/{record_id}"])


if __name__ == "__main__":
    unittest.main()
