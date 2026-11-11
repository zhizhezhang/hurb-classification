"""Load the validated training checkpoint once for the application lifespan."""

from __future__ import annotations

import json
from dataclasses import dataclass

import torch
from herb_classifier.data import get_preprocess_config, load_class_to_idx
from herb_classifier.model import MODEL_NAME, load_checkpoint

from backend.core.config import PROJECT_ROOT, Settings


CLASS_MAPPING_PATH = PROJECT_ROOT / "reports" / "data_split" / "class_to_idx.json"
PREPROCESS_CONFIG_PATH = PROJECT_ROOT / "reports" / "data_split" / "preprocess_config.json"
EXPECTED_CLASSES = 18


@dataclass
class LoadedModel:
    model: torch.nn.Module
    model_name: str
    num_classes: int
    device: str
    class_to_idx: dict[str, int]
    amp_enabled: bool
    model_version: str
    checkpoint_epoch: int


def select_device(preference: str) -> torch.device:
    if preference == "cpu":
        return torch.device("cpu")
    if preference == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError("HERB_DEVICE=cuda was requested, but CUDA is unavailable")
        return torch.device("cuda")
    if preference == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    raise ValueError(f"Unsupported device preference: {preference}")


def load_model(settings: Settings) -> LoadedModel:
    checkpoint_path = settings.model_path
    if not checkpoint_path.is_file():
        raise FileNotFoundError(f"Model checkpoint not found: {checkpoint_path}")

    mapping = load_class_to_idx(CLASS_MAPPING_PATH)
    if len(mapping) != EXPECTED_CLASSES:
        raise RuntimeError(f"Expected {EXPECTED_CLASSES} classes in {CLASS_MAPPING_PATH}")

    device = select_device(settings.device)
    try:
        model, checkpoint = load_checkpoint(checkpoint_path, device)
    except Exception as exc:
        raise RuntimeError(f"Failed to load model checkpoint {checkpoint_path}: {exc}") from exc

    if checkpoint.get("model_name") != MODEL_NAME:
        raise RuntimeError(f"Unexpected checkpoint model: {checkpoint.get('model_name')}")
    if checkpoint.get("num_classes") != EXPECTED_CLASSES:
        raise RuntimeError(f"Expected {EXPECTED_CLASSES} checkpoint classes, got {checkpoint.get('num_classes')}")
    if checkpoint.get("class_to_idx") != mapping:
        raise RuntimeError("Checkpoint class_to_idx differs from reports/data_split/class_to_idx.json")
    saved_preprocess = json.loads(PREPROCESS_CONFIG_PATH.read_text(encoding="utf-8"))
    if checkpoint.get("preprocess_config") != saved_preprocess or get_preprocess_config() != saved_preprocess:
        raise RuntimeError("Checkpoint preprocessing differs from the accepted evaluation transform")
    training_config = checkpoint.get("training_config")
    if not isinstance(training_config, dict) or not isinstance(training_config.get("amp"), bool):
        raise RuntimeError("Checkpoint training configuration lacks the AMP setting")
    experiment_name = training_config.get("experiment_name")
    if not isinstance(experiment_name, str) or not isinstance(checkpoint.get("epoch"), int):
        raise RuntimeError("Checkpoint lacks a valid experiment name or epoch")

    model.eval()
    actual_device = str(next(model.parameters()).device)
    return LoadedModel(
        model=model,
        model_name=checkpoint["model_name"],
        num_classes=checkpoint["num_classes"],
        device=actual_device,
        class_to_idx=mapping,
        amp_enabled=training_config["amp"],
        model_version=f"{experiment_name}_epoch{checkpoint['epoch']}",
        checkpoint_epoch=checkpoint["epoch"],
    )
