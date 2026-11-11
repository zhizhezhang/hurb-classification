"""Train/validation-only adapter for the accepted task 02.2 data module."""

from __future__ import annotations

from pathlib import Path

import torch
from torch.utils.data import DataLoader

from . import _accepted_data as _accepted

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SPLIT_DIR = PROJECT_ROOT / "reports" / "data_split"
DATASET_ROOT = PROJECT_ROOT / "Chinese Medicine datasets"
class HerbImageDataset(_accepted.HerbImageDataset):
    def __getitem__(self, index: int):
        try:
            return super().__getitem__(index)
        except Exception as exc:
            path = self.dataset_root / self.records[index]["path"]
            raise RuntimeError(f"Failed to read or preprocess image: {path}") from exc


get_train_transform = _accepted.get_train_transform
get_eval_transform = _accepted.get_eval_transform
get_preprocess_config = _accepted.get_preprocess_config
load_class_to_idx = _accepted.load_class_to_idx
create_dataloaders = _accepted.create_dataloaders


def create_loaders(batch_size: int, num_workers: int, seed: int) -> tuple[DataLoader, DataLoader]:
    """Create only train and val loaders; never open test.csv."""
    if batch_size < 1 or num_workers < 0:
        raise ValueError("batch_size must be positive and num_workers nonnegative")
    mapping = SPLIT_DIR / "class_to_idx.json"
    train = HerbImageDataset(SPLIT_DIR / "train.csv", DATASET_ROOT, mapping,
                             transform=get_train_transform())
    val = HerbImageDataset(SPLIT_DIR / "val.csv", DATASET_ROOT, mapping,
                           transform=get_eval_transform())
    options = dict(batch_size=batch_size, num_workers=num_workers,
                   pin_memory=torch.cuda.is_available(),
                   worker_init_fn=_accepted._seed_worker if num_workers else None)
    train_loader = DataLoader(train, shuffle=True,
                              generator=torch.Generator().manual_seed(seed), **options)
    val_loader = DataLoader(val, shuffle=False,
                            generator=torch.Generator().manual_seed(seed + 1), **options)
    return train_loader, val_loader
