"""Configuration, reproducibility, checkpoints, and metric plotting."""

from __future__ import annotations

import csv
import json
import random
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch
import yaml

from .data import PROJECT_ROOT, SPLIT_DIR, get_preprocess_config
from .model import MODEL_NAME, WEIGHTS_NAME

INNER_ROOT = Path(__file__).resolve().parents[1]


def read_config(path: str | Path) -> dict:
    path = Path(path)
    if not path.is_absolute():
        path = INNER_ROOT / path
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("YAML config must be a mapping")
    required = {"model", "weights", "num_classes", "batch_size", "epochs", "learning_rate",
                "optimizer", "loss", "seed", "amp", "patience", "num_workers", "device"}
    missing = required - config.keys()
    if missing:
        raise ValueError(f"Missing config entries: {sorted(missing)}")
    if config["model"] != MODEL_NAME or config["weights"] != WEIGHTS_NAME:
        raise ValueError("This project requires pretrained ConvNeXt-Tiny ImageNet-1K V1")
    if config["num_classes"] != 18 or config["optimizer"] != "AdamW" or config["loss"] != "CrossEntropyLoss":
        raise ValueError("Unexpected model, optimizer, or loss configuration")
    if any(config[k] <= 0 for k in ("batch_size", "epochs", "learning_rate", "patience")):
        raise ValueError("Batch size, epochs, learning rate and patience must be positive")
    if config["num_workers"] < 0:
        raise ValueError("num_workers cannot be negative")
    if "experiment_name" not in config and "output_dir" not in config:
        raise ValueError("Set experiment_name (or legacy output_dir) in the YAML config")
    if "experiment_name" in config:
        name = config["experiment_name"]
        if not isinstance(name, str) or not re.fullmatch(r"[\w-]{1,64}", name):
            raise ValueError("experiment_name must contain 1-64 letters, digits, underscores or hyphens")
        if name.upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                            *(f"LPT{i}" for i in range(1, 10))}:
            raise ValueError("experiment_name is a reserved Windows filename")
    return config


def allocate_run_dir(config: dict) -> Path:
    """Atomically reserve a new directory without modifying prior experiments."""
    legacy = Path(config["output_dir"]) if "output_dir" in config else None
    name = config.get("experiment_name", legacy.name if legacy else None)
    if not isinstance(name, str) or not re.fullmatch(r"[\w-]{1,64}", name):
        raise ValueError("A valid experiment_name is required")
    root = (INNER_ROOT / config.get("runs_dir", legacy.parent if legacy else "runs")).resolve()
    if root != INNER_ROOT and INNER_ROOT not in root.parents:
        raise ValueError("runs_dir must be inside the training project")
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone(timedelta(hours=8))).strftime("%Y%m%d_%H%M%S")
    for suffix in range(1, 1000):
        run_dir = root / f"{name}_{stamp}_{suffix:03d}"
        try:
            run_dir.mkdir(exist_ok=False)
            return run_dir
        except FileExistsError:
            continue
    raise FileExistsError("Could not reserve a unique experiment directory")


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def require_cuda() -> torch.device:
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is unavailable; training will not fall back to CPU")
    return torch.device("cuda")


def environment_info(batch_size: int) -> dict:
    import sys
    import torchvision
    return {"python": sys.version.split()[0], "torch": torch.__version__,
            "torchvision": torchvision.__version__, "cuda_build": torch.version.cuda,
            "cuda_available": torch.cuda.is_available(),
            "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
            "device": "cuda", "batch_size": batch_size,
            "split_files": [str((SPLIT_DIR / name).relative_to(PROJECT_ROOT)) for name in
                            ("train.csv", "val.csv", "class_to_idx.json", "preprocess_config.json")],
            "determinism_note": "CUDA kernels may be nondeterministic; deterministic algorithms are not forced."}


def save_checkpoint(path: Path, model: torch.nn.Module, mapping: dict, config: dict,
                    epoch: int, best_f1: float, kind: str, *, optimizer=None, scaler=None,
                    stale_epochs: int = 0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"model_state_dict": model.state_dict(), "model_name": MODEL_NAME,
               "weights_source": WEIGHTS_NAME, "num_classes": len(mapping),
               "class_to_idx": mapping, "preprocess_config": get_preprocess_config(),
               "preprocess_config_source": "../reports/data_split/preprocess_config.json",
               "epoch": epoch, "best_val_macro_f1": best_f1, "training_config": config,
               "kind": kind}
    if optimizer is not None:
        payload["optimizer_state_dict"] = optimizer.state_dict()
        payload["amp_scaler_state_dict"] = scaler.state_dict() if scaler is not None else None
        payload["epochs_without_improvement"] = stale_epochs
        payload["torch_rng_state"] = torch.get_rng_state()
        payload["cuda_rng_state_all"] = torch.cuda.get_rng_state_all()
    try:
        torch.save(payload, path)
    except Exception as exc:
        raise RuntimeError(f"Could not save checkpoint {path}: {exc}") from exc


HISTORY_FIELDS = ["epoch", "train_loss", "train_accuracy", "val_loss",
                  "val_accuracy", "val_macro_f1", "learning_rate", "epoch_seconds",
                  "peak_cuda_memory_bytes"]


def write_history(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as target:
        writer = csv.DictWriter(target, fieldnames=HISTORY_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def plot_history(csv_path: str | Path, output_dir: str | Path) -> None:
    with Path(csv_path).open(encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))
    if not rows:
        raise ValueError("Training history has no epochs")
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    for metric, filename in (("loss", "loss_curve.png"), ("accuracy", "accuracy_curve.png")):
        fig, ax = plt.subplots(figsize=(7, 4))
        epochs = [int(row["epoch"]) for row in rows]
        for prefix, label in (("train", "Train"), ("val", "Validation")):
            ax.plot(epochs, [float(row[f"{prefix}_{metric}"]) for row in rows], marker="o", label=label)
        ax.set(xlabel="Epoch", ylabel=metric.title(), title=f"Train and validation {metric}")
        ax.grid(alpha=.25)
        ax.legend()
        fig.tight_layout()
        fig.savefig(out / filename, dpi=160)
        plt.close(fig)


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
