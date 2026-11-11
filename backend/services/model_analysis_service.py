"""Validate the original Run02 and final-test archives once at startup."""

from __future__ import annotations

import csv
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path

from PIL import Image
from pydantic import ValidationError

from herb_classifier.model import parameter_counts

from backend.core.config import PROJECT_ROOT
from backend.schemas.model_analysis import (
    BestValidation, ChartLink, FinalTest, ModelInfo, ModelMetrics, PerClass,
)
from backend.services.model_loader import LoadedModel


EXPERIMENTS_ROOT = PROJECT_ROOT / "experiments"
CHART_FILES = {
    "training_results": "run02/results.png",
    "accuracy_curve": "run02/accuracy_curve.png",
    "loss_curve": "run02/loss_curve.png",
    "confusion_matrix": "final_evaluation/confusion_matrix.png",
    "confusion_matrix_normalized": "final_evaluation/confusion_matrix_normalized.png",
}
REPORT_COLUMNS = {
    "class_idx", "class", "support", "true_positive", "false_positive",
    "false_negative", "precision", "recall", "f1_score",
}
TRAINING_COLUMNS = {"epoch", "val_accuracy", "val_macro_f1"}


@dataclass(frozen=True)
class ModelAnalysis:
    info: ModelInfo
    metrics: ModelMetrics
    chart_paths: dict[str, Path]


def _read_json(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"Missing model analysis source: {label}") from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Unreadable or invalid model analysis JSON: {label}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"Model analysis JSON must be an object: {label}")
    return value


def _read_csv(path: Path, label: str, required_columns: set[str]) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as source:
            reader = csv.DictReader(source)
            if not reader.fieldnames or not required_columns.issubset(reader.fieldnames):
                raise ValueError("required columns are missing")
            rows = list(reader)
    except FileNotFoundError as exc:
        raise RuntimeError(f"Missing model analysis source: {label}") from exc
    except (OSError, UnicodeError, csv.Error, ValueError) as exc:
        raise RuntimeError(f"Unreadable or invalid model analysis CSV: {label}") from exc
    return rows


def _integer(value: object, label: str, minimum: int = 0) -> int:
    try:
        if isinstance(value, bool) or isinstance(value, float):
            raise ValueError
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid integer: {label}") from exc
    if parsed < minimum:
        raise ValueError(f"Invalid integer: {label}")
    return parsed


def _ratio(value: object, label: str) -> float:
    try:
        if isinstance(value, bool):
            raise ValueError
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid ratio: {label}") from exc
    if not math.isfinite(parsed) or not 0 <= parsed <= 1:
        raise ValueError(f"Invalid ratio: {label}")
    return parsed


def _same(actual: float, expected: float, label: str) -> None:
    if not math.isclose(actual, expected, rel_tol=0, abs_tol=1e-9):
        raise ValueError(f"Inconsistent model analysis metric: {label}")


def _charts(root: Path) -> tuple[dict[str, Path], list[ChartLink]]:
    paths = {}
    links = []
    for name, relative in CHART_FILES.items():
        path = root / relative
        if not path.is_file():
            continue
        try:
            with Image.open(path) as image:
                if image.format != "PNG":
                    raise ValueError("not a PNG")
                image.verify()
        except (OSError, ValueError) as exc:
            raise RuntimeError(f"Invalid model analysis chart: {relative}") from exc
        paths[name] = path
        links.append(ChartLink(name=name, url=f"/api/model/charts/{name}"))
    return paths, links


def load_model_analysis(loaded: LoadedModel, checkpoint_path: Path,
                        archive_root: Path = EXPERIMENTS_ROOT) -> ModelAnalysis:
    """Read archived data, compare it with the deployed checkpoint, and cache results."""
    run = _read_json(archive_root / "run02/run_info.json", "run02/run_info.json")
    status = _read_json(archive_root / "run02/run_status.json", "run02/run_status.json")
    test = _read_json(archive_root / "final_evaluation/test_metrics.json",
                      "final_evaluation/test_metrics.json")
    training_rows = _read_csv(archive_root / "run02/metrics.csv", "run02/metrics.csv",
                              TRAINING_COLUMNS)
    report_rows = _read_csv(archive_root / "final_evaluation/classification_report.csv",
                            "final_evaluation/classification_report.csv", REPORT_COLUMNS)

    try:
        config = run["config"]
        params = run["model_parameters"]
        best_epoch = _integer(status["best_epoch"], "run02 best_epoch", 1)
        input_size = _integer(config["input_size"], "run02 input_size", 1)
        if (config["model"] != loaded.model_name or config["num_classes"] != loaded.num_classes
                or loaded.num_classes != 18 or loaded.checkpoint_epoch != best_epoch
                or test["evaluation_config"]["checkpoint_epoch"] != best_epoch
                or test["evaluation_config"]["checkpoint_kind"] != "best"
                or loaded.model_version != f"{config['experiment_name']}_epoch{best_epoch}"):
            raise ValueError("Run02 archive and deployed checkpoint metadata differ")
        if (test["class_to_idx"] != loaded.class_to_idx
                or test["preprocess_config"]["input_shape"] != [3, input_size, input_size]
                or test["preprocess_config"]["torchvision_weights"] != config["weights"]):
            raise ValueError("Final evaluation mapping or preprocessing differs from Run02")

        actual_params = parameter_counts(loaded.model)
        if (actual_params["total"] != _integer(params["total"], "total parameters", 1)
                or actual_params["trainable"] != _integer(params["trainable"], "trainable parameters")):
            raise ValueError("Run02 parameter counts differ from the deployed model")

        expected_hash = test["source_hashes"]["checkpoint_sha256"]
        with checkpoint_path.open("rb") as source:
            actual_hash = hashlib.file_digest(source, "sha256").hexdigest()
        if actual_hash != expected_hash:
            raise ValueError("Deployed checkpoint SHA-256 differs from final evaluation")

        indexed = {}
        for row in training_rows:
            epoch = _integer(row["epoch"], "training epoch", 1)
            if epoch in indexed:
                raise ValueError("Duplicate Run02 epoch")
            indexed[epoch] = row
        if best_epoch not in indexed or not indexed:
            raise ValueError("Run02 best epoch is absent from metrics.csv")
        best_accuracy = _ratio(indexed[best_epoch]["val_accuracy"], "best validation accuracy")
        best_f1 = _ratio(indexed[best_epoch]["val_macro_f1"], "best validation macro_f1")
        if best_f1 < max(_ratio(row["val_macro_f1"], "validation macro_f1")
                         for row in training_rows):
            raise ValueError("Run02 best epoch is not the best validation Macro-F1")
        _same(best_f1, _ratio(status["best_val_macro_f1"], "run02 status macro_f1"),
              "Run02 status macro_f1")
        _same(best_accuracy, _ratio(test["validation_at_best_epoch"]["accuracy"],
                                    "evaluation validation accuracy"), "validation accuracy")
        _same(best_f1, _ratio(test["validation_at_best_epoch"]["macro_f1"],
                              "evaluation validation macro_f1"), "validation macro_f1")

        total = _integer(test["test_samples"], "test_samples", 1)
        correct = _integer(test["correct"], "correct")
        incorrect = _integer(test["incorrect"], "incorrect")
        if correct + incorrect != total:
            raise ValueError("Test sample counts disagree")
        final = FinalTest(
            total_samples=total, correct_predictions=correct,
            accuracy=_ratio(test["accuracy"], "test accuracy"),
            macro_precision=_ratio(test["macro_precision"], "macro_precision"),
            macro_recall=_ratio(test["macro_recall"], "macro_recall"),
            macro_f1=_ratio(test["macro_f1"], "macro_f1"),
            weighted_f1=_ratio(test["weighted_f1"], "weighted_f1"),
        )
        _same(final.accuracy, correct / total, "test accuracy")

        per_class = []
        supports = {}
        true_positives = {}
        for row in report_rows:
            name = row["class"]
            index = _integer(row["class_idx"], "class_idx")
            if name not in loaded.class_to_idx or loaded.class_to_idx[name] != index or name in supports:
                raise ValueError("Classification report class mapping differs from model")
            support = _integer(row["support"], "support", 1)
            tp = _integer(row["true_positive"], "true_positive")
            fp = _integer(row["false_positive"], "false_positive")
            fn = _integer(row["false_negative"], "false_negative")
            if tp + fn != support or tp > support:
                raise ValueError("Classification report support and true positives disagree")
            precision = _ratio(row["precision"], "class precision")
            recall = _ratio(row["recall"], "class recall")
            f1 = _ratio(row["f1_score"], "class f1_score")
            _same(precision, tp / (tp + fp) if tp + fp else 0, "class precision")
            _same(recall, tp / support, "class recall")
            _same(f1, 2 * precision * recall / (precision + recall)
                  if precision + recall else 0, "class f1_score")
            supports[name] = support
            true_positives[name] = tp
            per_class.append(PerClass(class_name=name, precision=precision,
                                      recall=recall, f1_score=f1, support=support))
        if (len(per_class) != 18 or set(supports) != set(loaded.class_to_idx)
                or sum(supports.values()) != total or sum(true_positives.values()) != correct):
            raise ValueError("Classification report does not cover the 18-class test set")
        per_class.sort(key=lambda item: loaded.class_to_idx[item.class_name])

        matrix = test["confusion_matrix"]
        if not isinstance(matrix, list) or len(matrix) != 18:
            raise ValueError("Final test confusion matrix must be 18 by 18")
        for name, index in loaded.class_to_idx.items():
            row = matrix[index]
            if (not isinstance(row, list) or len(row) != 18
                    or any(type(value) is not int or value < 0 for value in row)
                    or sum(row) != supports[name] or row[index] != true_positives[name]):
                raise ValueError("Final test confusion matrix differs from the classification report")
        _same(final.macro_precision, sum(item.precision for item in per_class) / 18,
              "macro_precision")
        _same(final.macro_recall, sum(item.recall for item in per_class) / 18,
              "macro_recall")
        _same(final.macro_f1, sum(item.f1_score for item in per_class) / 18,
              "macro_f1")
        _same(final.weighted_f1,
              sum(item.f1_score * item.support for item in per_class) / total,
              "weighted_f1")
    except (KeyError, TypeError, ValueError, ValidationError, OSError) as exc:
        raise RuntimeError(f"Invalid or inconsistent Run02/final evaluation data: {exc}") from exc

    chart_paths, charts = _charts(archive_root)
    info = ModelInfo(
        model_name=loaded.model_name, model_version=loaded.model_version,
        num_classes=loaded.num_classes, parameter_count=actual_params["total"],
        trainable_parameter_count=actual_params["trainable"], input_size=input_size,
        pretrained=config["weights"], best_epoch=best_epoch, charts=charts,
    )
    metrics = ModelMetrics(
        best_validation=BestValidation(best_epoch=best_epoch, accuracy=best_accuracy,
                                       macro_f1=best_f1),
        final_test=final, per_class=per_class, charts=charts,
    )
    return ModelAnalysis(info=info, metrics=metrics, chart_paths=chart_paths)
