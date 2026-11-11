"""Final Run02 archive validation and read-only analysis HTTP checks."""

from __future__ import annotations

import hashlib
import csv
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from herb_classifier.model import parameter_counts

from backend.core.config import PROJECT_ROOT
from backend.main import app
from backend.services.model_analysis_service import CHART_FILES, load_model_analysis
from backend.services.model_loader import load_model


MODEL_PATH = PROJECT_ROOT / "models" / "convnext_tiny_best.pt"
ARCHIVE = PROJECT_ROOT / "experiments"
SOURCE_FILES = [
    "run02/run_info.json", "run02/run_status.json", "run02/metrics.csv",
    "final_evaluation/test_metrics.json", "final_evaluation/classification_report.csv",
    *CHART_FILES.values(),
]


def sha256(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


class ModelAnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source_hashes = {name: sha256(ARCHIVE / name) for name in SOURCE_FILES}
        cls.runtime = tempfile.TemporaryDirectory()
        cls.env = patch.dict(os.environ, {
            "HERB_MODEL_PATH": str(MODEL_PATH),
            "HERB_HISTORY_DB_PATH": str(Path(cls.runtime.name) / "history.db"),
            "HERB_UPLOADS_DIR": str(Path(cls.runtime.name) / "uploads"),
        })
        cls.env.start()
        cls.client = TestClient(app)
        try:
            with patch("backend.main.load_model", wraps=load_model) as loader:
                cls.client.__enter__()
                cls.model_load_count = loader.call_count
            cls.loaded = app.state.model
        except Exception:
            cls.env.stop()
            cls.runtime.cleanup()
            raise

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.__exit__(None, None, None)
        cls.env.stop()
        cls.runtime.cleanup()
        for name, before in cls.source_hashes.items():
            assert sha256(ARCHIVE / name) == before, name

    def copy_sources(self, destination: Path) -> None:
        for name in SOURCE_FILES[:5]:
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ARCHIVE / name, target)

    def test_info_is_from_deployed_model_and_run02(self) -> None:
        response = self.client.get("/api/model/info")
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()["data"]
        self.assertEqual(data["model_name"], "convnext_tiny")
        self.assertEqual(data["model_version"], self.loaded.model_version)
        self.assertEqual(data["model_version"], "convnext_tiny_lr3e5_epoch8")
        self.assertEqual(data["num_classes"], 18)
        self.assertEqual(data["best_epoch"], 8)
        self.assertEqual(data["input_size"], 224)
        self.assertEqual(data["pretrained"], "ConvNeXt_Tiny_Weights.IMAGENET1K_V1")
        counts = parameter_counts(self.loaded.model)
        self.assertEqual(data["parameter_count"], counts["total"])
        self.assertEqual(data["trainable_parameter_count"], counts["trainable"])
        self.assertEqual(counts, {"total": 27833970, "trainable": 27833970})
        self.assertEqual(self.model_load_count, 1)
        self.assertNotIn("run01", response.text.lower())
        self.assertNotIn(str(PROJECT_ROOT), response.text)

    def test_metrics_match_original_validation_and_test_sources(self) -> None:
        response = self.client.get("/api/model/metrics")
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()["data"]
        metrics = json.loads((ARCHIVE / "final_evaluation/test_metrics.json").read_text(encoding="utf-8"))
        with (ARCHIVE / "run02/metrics.csv").open("r", encoding="utf-8-sig", newline="") as source:
            best = next(row for row in csv.DictReader(source) if row["epoch"] == "8")
        self.assertEqual(data["best_validation"], {
            "best_epoch": 8, **metrics["validation_at_best_epoch"]})
        self.assertEqual(data["best_validation"]["accuracy"], float(best["val_accuracy"]))
        self.assertEqual(data["best_validation"]["macro_f1"], float(best["val_macro_f1"]))
        self.assertEqual(data["final_test"], {
            "total_samples": metrics["test_samples"],
            "correct_predictions": metrics["correct"],
            "accuracy": metrics["accuracy"],
            "macro_precision": metrics["macro_precision"],
            "macro_recall": metrics["macro_recall"],
            "macro_f1": metrics["macro_f1"],
            "weighted_f1": metrics["weighted_f1"],
        })
        self.assertEqual(data["final_test"]["total_samples"], 788)
        self.assertEqual(data["final_test"]["correct_predictions"], 765)
        self.assertEqual(len(data["per_class"]), 18)
        self.assertEqual({row["class_name"] for row in data["per_class"]},
                         set(self.loaded.class_to_idx))
        self.assertEqual(sum(row["support"] for row in data["per_class"]), 788)
        self.assertEqual(data["per_class"][1]["class_name"], "人参")
        self.assertAlmostEqual(data["per_class"][1]["recall"], 24 / 35)
        self.assertNotIn("run01", response.text.lower())
        self.assertNotIn(str(PROJECT_ROOT), response.text)

    def test_requests_use_cache_and_do_not_reload_model(self) -> None:
        with patch("backend.main.load_model", side_effect=AssertionError("model reloaded")):
            with patch("backend.services.model_analysis_service.Path.read_text",
                       side_effect=AssertionError("archive re-read")):
                for _ in range(3):
                    self.assertEqual(self.client.get("/api/model/info").status_code, 200)
                    self.assertEqual(self.client.get("/api/model/metrics").status_code, 200)

    def test_chart_whitelist_content_type_and_original_bytes(self) -> None:
        info = self.client.get("/api/model/info").json()["data"]
        self.assertEqual({chart["name"] for chart in info["charts"]}, set(CHART_FILES))
        for name, relative in CHART_FILES.items():
            with self.subTest(chart=name):
                response = self.client.get(f"/api/model/charts/{name}")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers["content-type"], "image/png")
                self.assertEqual(hashlib.sha256(response.content).hexdigest(),
                                 self.source_hashes[relative])
        self.assertEqual(self.client.get("/api/model/charts/not_known").status_code, 404)
        self.assertEqual(self.client.get("/api/model/charts/%2e%2e%2fREADME.md").status_code, 404)
        self.assertEqual(self.client.get("/api/model/charts/..%5c..%5cREADME.md").status_code, 404)

    def test_missing_or_corrupt_required_sources_fail_explicitly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_sources(root)
            missing = root / "run02/run_status.json"
            missing.unlink()
            with self.assertRaisesRegex(RuntimeError, "Missing model analysis source: run02/run_status.json"):
                load_model_analysis(self.loaded, MODEL_PATH, root)
            shutil.copyfile(ARCHIVE / "run02/run_status.json", missing)
            missing.write_text("{", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "invalid model analysis JSON: run02/run_status.json"):
                load_model_analysis(self.loaded, MODEL_PATH, root)

    def test_inconsistent_report_and_checkpoint_hash_fail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_sources(root)
            metrics_path = root / "final_evaluation/test_metrics.json"
            metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
            metrics["source_hashes"]["checkpoint_sha256"] = "0" * 64
            metrics_path.write_text(json.dumps(metrics), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "checkpoint SHA-256 differs"):
                load_model_analysis(self.loaded, MODEL_PATH, root)
            shutil.copyfile(ARCHIVE / "final_evaluation/test_metrics.json", metrics_path)
            report = root / "final_evaluation/classification_report.csv"
            report.write_text(report.read_text(encoding="utf-8").replace("人参", "错误类别"),
                              encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "class mapping differs"):
                load_model_analysis(self.loaded, MODEL_PATH, root)

    def test_optional_chart_absence_is_not_advertised(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_sources(root)
            analysis = load_model_analysis(self.loaded, MODEL_PATH, root)
            self.assertEqual(analysis.info.charts, [])
            self.assertEqual(analysis.chart_paths, {})

    def test_existing_routes_and_openapi_remain_available(self) -> None:
        self.assertEqual(self.client.get("/api/health").status_code, 200)
        self.assertEqual(self.client.get("/api/herbs").status_code, 200)
        self.assertEqual(self.client.get("/api/history").status_code, 200)
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": ""}):
            self.assertEqual(self.client.post("/api/ai/chat", json={"message": "问题"}).status_code, 503)
        paths = self.client.get("/openapi.json").json()["paths"]
        for path in ("/api/predict", "/api/model/info", "/api/model/metrics",
                     "/api/model/charts/{name}"):
            self.assertIn(path, paths)


if __name__ == "__main__":
    unittest.main()
