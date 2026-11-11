"""Model lifecycle and HTTP checks without running training."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import torch
from fastapi.testclient import TestClient

from backend.core.config import PROJECT_ROOT, Settings
from backend.main import app
from backend.services.model_loader import load_model, select_device


MODEL_PATH = PROJECT_ROOT / "models" / "convnext_tiny_best.pt"


class BackendTests(unittest.TestCase):
    def setUp(self) -> None:
        self.history_temp = tempfile.TemporaryDirectory()
        self.history_env = patch.dict(os.environ, {
            "HERB_HISTORY_DB_PATH": str(Path(self.history_temp.name) / "history.db"),
            "HERB_UPLOADS_DIR": str(Path(self.history_temp.name) / "uploads"),
        })
        self.history_env.start()

    def tearDown(self) -> None:
        self.history_env.stop()
        self.history_temp.cleanup()

    def test_real_model_lifecycle_and_http(self) -> None:
        with patch.dict(os.environ, {"HERB_MODEL_PATH": str(MODEL_PATH), "HERB_DEVICE": "auto"}):
            with patch("backend.main.load_model", wraps=load_model) as loader:
                with TestClient(app) as client:
                    loaded = app.state.model
                    self.assertFalse(loaded.model.training)
                    self.assertEqual(loaded.class_to_idx, json.loads(
                        (PROJECT_ROOT / "reports/data_split/class_to_idx.json").read_text(encoding="utf-8")
                    ))
                    for _ in range(3):
                        response = client.get("/api/health")
                        self.assertEqual(response.status_code, 200)
                        self.assertEqual(response.json(), {
                            "status": "ok",
                            "model_loaded": True,
                            "model_name": "convnext_tiny",
                            "num_classes": 18,
                            "device": loaded.device,
                        })
                    self.assertEqual(client.get("/docs").status_code, 200)
                    schema = client.get("/openapi.json")
                    self.assertEqual(schema.status_code, 200)
                    self.assertIn("/api/health", schema.json()["paths"])
                    self.assertEqual(loader.call_count, 1)
                self.assertIsNone(app.state.model)

    def test_model_path_and_loading_do_not_depend_on_cwd(self) -> None:
        previous_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as temporary:
            try:
                os.chdir(temporary)
                with patch.dict(os.environ, {"HERB_MODEL_PATH": "models/convnext_tiny_best.pt", "HERB_DEVICE": "cpu"}):
                    settings = Settings.from_env()
                    self.assertEqual(settings.model_path, MODEL_PATH)
                    loaded = load_model(settings)
                    self.assertEqual(loaded.device, "cpu")
                    self.assertEqual(loaded.num_classes, 18)
            finally:
                os.chdir(previous_cwd)

    def test_missing_checkpoint_prevents_startup(self) -> None:
        with patch.dict(os.environ, {"HERB_MODEL_PATH": "models/not_found.pt", "HERB_DEVICE": "cpu"}):
            with self.assertRaisesRegex(FileNotFoundError, "Model checkpoint not found"):
                with TestClient(app):
                    pass

    def test_history_database_initialization_failure_prevents_startup(self) -> None:
        with patch.dict(os.environ, {"HERB_MODEL_PATH": str(MODEL_PATH), "HERB_DEVICE": "cpu"}):
            with patch("backend.main.HistoryStore.initialize", side_effect=OSError("D:\\private\\history.db")):
                with self.assertRaises(OSError):
                    with TestClient(app):
                        pass
        self.assertIsNone(app.state.model)
        self.assertIsNone(app.state.history_store)

    def test_corrupt_checkpoint_prevents_startup(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            damaged = Path(temporary) / "damaged.pt"
            damaged.write_bytes(b"not a checkpoint")
            with patch.dict(os.environ, {"HERB_MODEL_PATH": str(damaged), "HERB_DEVICE": "cpu"}):
                with self.assertRaisesRegex(RuntimeError, "Failed to load model checkpoint"):
                    with TestClient(app):
                        pass

    def test_incomplete_state_dict_prevents_startup(self) -> None:
        mapping = json.loads((PROJECT_ROOT / "reports/data_split/class_to_idx.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as temporary:
            incomplete = Path(temporary) / "incomplete.pt"
            torch.save({
                "model_name": "convnext_tiny",
                "num_classes": 18,
                "class_to_idx": mapping,
                "model_state_dict": {},
            }, incomplete)
            with patch.dict(os.environ, {"HERB_MODEL_PATH": str(incomplete), "HERB_DEVICE": "cpu"}):
                with self.assertRaisesRegex(RuntimeError, "Failed to load model checkpoint"):
                    with TestClient(app):
                        pass

    def test_checkpoint_class_count_is_checked(self) -> None:
        mapping = json.loads((PROJECT_ROOT / "reports/data_split/class_to_idx.json").read_text(encoding="utf-8"))
        metadata = {"model_name": "convnext_tiny", "num_classes": 17, "class_to_idx": mapping}
        with patch("backend.services.model_loader.load_checkpoint", return_value=(torch.nn.Linear(1, 1), metadata)):
            with self.assertRaisesRegex(RuntimeError, "Expected 18 checkpoint classes"):
                load_model(Settings(model_path=MODEL_PATH, device="cpu"))

    def test_device_selection_falls_back_to_cpu(self) -> None:
        with patch("backend.services.model_loader.torch.cuda.is_available", return_value=False):
            self.assertEqual(str(select_device("auto")), "cpu")
            with self.assertRaisesRegex(RuntimeError, "CUDA is unavailable"):
                select_device("cuda")


if __name__ == "__main__":
    unittest.main()
