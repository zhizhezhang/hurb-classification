"""Report-ready previews of the accepted online augmentation pipeline."""

from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import torch
from PIL import Image, ImageOps

from .data import DATASET_ROOT, get_preprocess_config, get_train_transform


def save_augmentation_preview(dataset, output: str | Path, count: int = 4) -> None:
    """One original and three independent random transforms for each class sample."""
    transform = get_train_transform()
    config = get_preprocess_config()
    mean = torch.tensor(config["normalization_mean"]).view(3, 1, 1)
    std = torch.tensor(config["normalization_std"]).view(3, 1, 1)
    chosen = []
    seen_classes = set()
    for row in dataset.records:
        if row["class"] not in seen_classes:
            seen_classes.add(row["class"])
            chosen.append(row)
        if len(chosen) == count:
            break
    fig, axes = plt.subplots(len(chosen), 4, figsize=(12, 3 * len(chosen)), squeeze=False)
    for index, row in enumerate(chosen):
        path = DATASET_ROOT / row["path"]
        with Image.open(path) as source:
            original = ImageOps.exif_transpose(source).convert("RGB")
            axes[index, 0].imshow(original)
            for variant in range(1, 4):
                tensor = transform(original)
                image = (tensor * std + mean).clamp(0, 1).permute(1, 2, 0).numpy()
                axes[index, variant].imshow(image)
        for variant, label in enumerate(("Original", "Augmented 1", "Augmented 2", "Augmented 3")):
            axes[index, variant].set_title(f"Class {row['class_idx']} - {label}")
            axes[index, variant].axis("off")
    fig.tight_layout()
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=170)
    plt.close(fig)
