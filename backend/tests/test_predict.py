"""Real-image prediction and upload validation without training."""

from __future__ import annotations

import csv
import io
import math
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image

from backend.core.config import PROJECT_ROOT
from backend.main import app
from backend.services.model_loader import load_model


PREDICTIONS = PROJECT_ROOT / "experiments" / "final_evaluation" / "test_predictions.csv"
DATASET_ROOT = PROJECT_ROOT / "Chinese Medicine datasets"
MODEL_PATH = PROJECT_ROOT / "models" / "convnext_tiny_best.pt"


class PredictionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with PREDICTIONS.open(encoding="utf-8-sig", newline="") as source:
            rows = list(csv.DictReader(source))
        cls.examples = {
            suffix: next(row for row in rows if Path(row["path"]).suffix.lower() == suffix
                         and (DATASET_ROOT / row["path"]).is_file())
            for suffix in (".jpg", ".png")
        }
        cls.history_temp = tempfile.TemporaryDirectory()
        cls.env_patch = patch.dict(os.environ, {
            "HERB_MODEL_PATH": str(MODEL_PATH), "HERB_DEVICE": "auto",
            "HERB_HISTORY_DB_PATH": str(Path(cls.history_temp.name) / "history.db"),
            "HERB_UPLOADS_DIR": str(Path(cls.history_temp.name) / "uploads"),
        })
        cls.env_patch.start()
        cls.loader_patch = patch("backend.main.load_model", wraps=load_model)
        cls.loader_spy = cls.loader_patch.start()
        cls.client = TestClient(app)
        try:
            cls.client.__enter__()
        except Exception:
            cls.loader_patch.stop()
            cls.env_patch.stop()
            cls.history_temp.cleanup()
            raise

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.__exit__(None, None, None)
        cls.loader_patch.stop()
        cls.env_patch.stop()
        cls.history_temp.cleanup()

    def history_count(self) -> int:
        return app.state.history_store.list_page(1, 50).total

    def upload(self, row: dict, filename: str | None = None, content_type: str = "application/octet-stream"):
        path = DATASET_ROOT / row["path"]
        return self.client.post("/api/predict", files={
            "file": (filename or path.name, path.read_bytes(), content_type),
        })

    def test_real_jpeg_and_png_match_offline_results(self) -> None:
        record_ids = []
        for suffix, row in self.examples.items():
            with self.subTest(format=suffix):
                response = self.upload(row)
                self.assertEqual(response.status_code, 200, response.text)
                result = response.json()
                self.assertTrue(result["success"])
                data = result["data"]
                record_id = data["record_id"]
                self.assertIsInstance(record_id, int)
                self.assertGreater(record_id, 0)
                record_ids.append(record_id)
                self.assertEqual(data["predicted_class"], row["predicted_class"])
                self.assertLess(abs(data["confidence"] - float(row["predicted_confidence"])), 1e-4)
                self.assertEqual(data["model_version"], "convnext_tiny_lr3e5_epoch8")
                self.assertGreater(data["inference_time_ms"], 0)
                saved_response = self.client.get(f"/api/history/{record_id}")
                self.assertEqual(saved_response.status_code, 200)
                saved = saved_response.json()["data"]
                self.assertEqual(saved["predicted_class"], data["predicted_class"])
                self.assertEqual(saved["confidence"], data["confidence"])
                self.assertEqual(saved["top3"], data["top3"])
                self.assertEqual(saved["inference_time_ms"], data["inference_time_ms"])
                self.assertEqual(saved["model_version"], data["model_version"])
                image_response = self.client.get(saved["image_url"])
                self.assertEqual(image_response.status_code, 200)
                self.assertEqual(image_response.content, (DATASET_ROOT / row["path"]).read_bytes())
        self.assertEqual(len(set(record_ids)), 2)

    def test_top3_mapping_order_and_repeatability(self) -> None:
        first = self.upload(self.examples[".png"]).json()["data"]
        second = self.upload(self.examples[".png"]).json()["data"]
        self.assertNotEqual(first["record_id"], second["record_id"])
        mapping = app.state.model.class_to_idx
        top3 = first["top3"]
        self.assertEqual(len(top3), 3)
        self.assertEqual(first["predicted_class"], top3[0]["class_name"])
        self.assertEqual(first["confidence"], top3[0]["probability"])
        self.assertTrue(all(item["class_name"] in mapping for item in top3))
        self.assertTrue(all(0 <= item["probability"] <= 1 for item in top3))
        self.assertEqual([item["probability"] for item in top3],
                         sorted((item["probability"] for item in top3), reverse=True))
        self.assertEqual(first["predicted_class"], second["predicted_class"])
        self.assertEqual([item["class_name"] for item in top3],
                         [item["class_name"] for item in second["top3"]])
        for left, right in zip(top3, second["top3"]):
            self.assertTrue(math.isclose(left["probability"], right["probability"], abs_tol=1e-5))
        self.assertEqual(self.loader_spy.call_count, 1)

    def test_actual_format_not_filename_or_declared_type(self) -> None:
        response = self.upload(self.examples[".jpg"], filename="renamed.txt")
        self.assertEqual(response.status_code, 200, response.text)

    def test_invalid_uploads_are_rejected(self) -> None:
        before = self.history_count()
        self.assertEqual(self.client.post("/api/predict").status_code, 422)
        for contents, expected in ((b"", 400), (b"plain text", 415),
                                   (b"\xff\xd8\xffbroken", 422)):
            with self.subTest(expected=expected):
                response = self.client.post("/api/predict", files={"file": ("sample.jpg", contents, "image/jpeg")})
                self.assertEqual(response.status_code, expected, response.text)
        bmp = io.BytesIO()
        Image.new("RGB", (8, 8)).save(bmp, format="BMP")
        response = self.client.post("/api/predict", files={"file": ("fake.png", bmp.getvalue(), "image/png")})
        self.assertEqual(response.status_code, 415)
        self.assertEqual(self.history_count(), before)

    def test_file_size_and_pixel_limits(self) -> None:
        before = self.history_count()
        too_large = b"x" * (10 * 1024 * 1024 + 1)
        response = self.client.post("/api/predict", files={"file": ("large.png", too_large, "image/png")})
        self.assertEqual(response.status_code, 413, response.text)
        self.assertEqual(self.history_count(), before)
        huge_pixels = io.BytesIO()
        Image.new("1", (5000, 4001)).save(huge_pixels, format="PNG")
        response = self.client.post("/api/predict", files={
            "file": ("many_pixels.png", huge_pixels.getvalue(), "image/png"),
        })
        self.assertEqual(response.status_code, 413, response.text)
        self.assertEqual(self.history_count(), before)

    def test_inference_failure_is_generic(self) -> None:
        before = self.history_count()
        with patch.object(app.state.model.model, "forward", side_effect=RuntimeError("D:\\private\\weight.pt")):
            response = self.upload(self.examples[".png"])
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json(), {"detail": "Model inference failed"})
        self.assertNotIn("D:\\private", response.text)
        self.assertEqual(self.history_count(), before)

    def test_storage_failures_leave_no_partial_record_or_image(self) -> None:
        store = app.state.history_store
        image_bytes = (DATASET_ROOT / self.examples[".png"]["path"]).read_bytes()
        files = {"file": ("valid.png", image_bytes, "image/png")}
        before_count = self.history_count()
        before_images = {path.name for path in store.uploads_dir.iterdir()}

        real_open = Path.open

        def fail_image_write(path: Path, *args, **kwargs):
            if path.parent == store.uploads_dir and args and args[0] == "xb":
                raise OSError("D:\\private\\uploads denied")
            return real_open(path, *args, **kwargs)

        with patch.object(Path, "open", fail_image_write):
            response = self.client.post("/api/predict", files=files)
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json(), {"detail": "Could not save recognition history"})
        self.assertNotIn("D:\\private", response.text)
        self.assertEqual(self.history_count(), before_count)
        self.assertEqual({path.name for path in store.uploads_dir.iterdir()}, before_images)

        with patch.object(store, "_connect", side_effect=sqlite3.OperationalError("D:\\private\\history.db")):
            response = self.client.post("/api/predict", files=files)
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json(), {"detail": "Could not save recognition history"})
        self.assertNotIn("D:\\private", response.text)
        self.assertEqual(self.history_count(), before_count)
        self.assertEqual({path.name for path in store.uploads_dir.iterdir()}, before_images)

    def test_delete_prediction_history_removes_image(self) -> None:
        response = self.upload(self.examples[".jpg"])
        self.assertEqual(response.status_code, 200, response.text)
        record_id = response.json()["data"]["record_id"]
        image_url = f"/api/history/{record_id}/image"
        self.assertEqual(self.client.get(image_url).status_code, 200)
        self.assertEqual(self.client.delete(f"/api/history/{record_id}").status_code, 200)
        self.assertEqual(self.client.get(image_url).status_code, 404)

    def test_health_and_openapi_remain_available(self) -> None:
        self.assertEqual(self.client.get("/api/health").status_code, 200)
        self.assertEqual(self.client.get("/api/herbs").json()["total"], 18)
        self.assertEqual(self.client.get("/docs").status_code, 200)
        schema = self.client.get("/openapi.json")
        self.assertEqual(schema.status_code, 200)
        self.assertIn("post", schema.json()["paths"]["/api/predict"])


if __name__ == "__main__":
    unittest.main()
