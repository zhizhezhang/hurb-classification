"""PyTorch datasets and ConvNeXt-Tiny preprocessing for the audited herb images."""

from __future__ import annotations

import csv
import json
import random
from pathlib import Path

import torch
from PIL import Image, ImageOps
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms as T
from torchvision.models import ConvNeXt_Tiny_Weights
from torchvision.transforms import InterpolationMode


WEIGHTS = ConvNeXt_Tiny_Weights.IMAGENET1K_V1


def load_class_to_idx(path: str | Path) -> dict[str, int]:
    mapping = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(mapping, dict) or not mapping:
        raise ValueError("class_to_idx.json must be a nonempty object")
    if any(not isinstance(name, str) or not isinstance(index, int) for name, index in mapping.items()):
        raise ValueError("Class names must be strings and indices must be integers")
    if sorted(mapping.values()) != list(range(len(mapping))):
        raise ValueError("Class indices must be contiguous from zero")
    return mapping


def get_train_transform():
    preset = WEIGHTS.transforms()
    return T.Compose([
        T.RandomResizedCrop(224, scale=(0.80, 1.0), interpolation=InterpolationMode.BILINEAR),
        T.RandomHorizontalFlip(p=0.5),
        T.ColorJitter(brightness=0.10, contrast=0.10, saturation=0.05),
        T.ToTensor(),
        T.Normalize(mean=preset.mean, std=preset.std),
    ])


def get_eval_transform():
    """The exact deterministic preprocessing attached to the chosen pretrained weights."""
    return WEIGHTS.transforms()


def get_preprocess_config() -> dict:
    preset = WEIGHTS.transforms()
    return {
        "model": "convnext_tiny",
        "torchvision_weights": "ConvNeXt_Tiny_Weights.IMAGENET1K_V1",
        "image_color_mode": "RGB",
        "input_shape": [3, 224, 224],
        "normalization_mean": list(preset.mean),
        "normalization_std": list(preset.std),
        "evaluation": {"resize_shorter_side": preset.resize_size[0],
                       "center_crop": preset.crop_size[0], "interpolation": "bilinear",
                       "deterministic": True},
        "training": {"random_resized_crop": 224, "crop_scale": [0.80, 1.0],
                     "horizontal_flip_probability": 0.5,
                     "color_jitter": {"brightness": 0.10, "contrast": 0.10, "saturation": 0.05}},
    }


class HerbImageDataset(Dataset):
    """Read-only Dataset backed by a split CSV with dataset-relative image paths."""

    def __init__(self, csv_path: str | Path, dataset_root: str | Path,
                 class_to_idx_path: str | Path, transform=None):
        self.dataset_root = Path(dataset_root).expanduser().resolve()
        self.class_to_idx = load_class_to_idx(class_to_idx_path)
        self.transform = transform if transform is not None else get_eval_transform()
        with Path(csv_path).open("r", encoding="utf-8-sig", newline="") as source:
            self.records = list(csv.DictReader(source))
        if not self.records:
            raise ValueError(f"Split CSV is empty: {csv_path}")
        for row in self.records:
            if row["class"] not in self.class_to_idx:
                raise ValueError(f"Unknown class in split CSV: {row['class']}")
            if int(row["class_idx"]) != self.class_to_idx[row["class"]]:
                raise ValueError(f"Class mapping mismatch for {row['path']}")

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(self, index: int):
        row = self.records[index]
        image_path = (self.dataset_root / Path(row["path"])).resolve()
        if self.dataset_root not in image_path.parents:
            raise ValueError(f"Image path escapes dataset root: {row['path']}")
        with Image.open(image_path) as image:
            image = ImageOps.exif_transpose(image).convert("RGB")
            tensor = self.transform(image)
        return tensor, self.class_to_idx[row["class"]]


def _seed_worker(worker_id: int) -> None:
    random.seed(torch.initial_seed() % (2**32))


def create_dataloaders(dataset_root: str | Path, split_dir: str | Path,
                       batch_size: int = 32, num_workers: int = 0, seed: int = 42,
                       pin_memory: bool | None = None) -> dict[str, DataLoader]:
    """Create train/val/test loaders; Windows defaults to safe single-process loading."""
    if batch_size < 1 or num_workers < 0:
        raise ValueError("batch_size must be positive and num_workers must be nonnegative")
    random.seed(seed)
    torch.manual_seed(seed)
    split_dir = Path(split_dir)
    mapping_path = split_dir / "class_to_idx.json"
    eval_transform = get_eval_transform()
    transforms = {"train": get_train_transform(), "val": eval_transform, "test": eval_transform}
    if pin_memory is None:
        pin_memory = torch.cuda.is_available()
    loaders = {}
    for name in ("train", "val", "test"):
        dataset = HerbImageDataset(split_dir / f"{name}.csv", dataset_root, mapping_path,
                                   transform=transforms[name])
        generator = torch.Generator().manual_seed(seed + {"train": 0, "val": 1, "test": 2}[name])
        loaders[name] = DataLoader(dataset, batch_size=batch_size, shuffle=name == "train",
                                   num_workers=num_workers, pin_memory=pin_memory,
                                   worker_init_fn=_seed_worker if num_workers else None,
                                   generator=generator)
    return loaders
