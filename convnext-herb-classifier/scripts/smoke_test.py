"""Short CUDA/AMP training and checkpoint round-trip; never opens the test split."""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from herb_classifier.data import SPLIT_DIR, create_loaders, load_class_to_idx
from herb_classifier.model import build_model, load_checkpoint, parameter_counts
from herb_classifier.train import run_epoch
from herb_classifier.utils import (HISTORY_FIELDS, INNER_ROOT, environment_info, plot_history,
                                   read_config, require_cuda, save_checkpoint, set_seed, write_json)
from herb_classifier.visualize import save_augmentation_preview


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/convnext_tiny.yaml")
    parser.add_argument("--train-batches", type=int, default=2)
    parser.add_argument("--val-batches", type=int, default=2)
    parser.add_argument("--batch-size", type=int, default=None,
                        help="Optional recorded smoke-only batch size")
    args = parser.parse_args()
    if args.train_batches < 1 or args.val_batches < 1:
        raise ValueError("Smoke batch counts must be positive")
    config = read_config(args.config)
    batch_size = args.batch_size or config["batch_size"]
    device = require_cuda()
    set_seed(config["seed"])
    output = INNER_ROOT / "runs" / "smoke_test"
    output.mkdir(parents=True, exist_ok=True)
    mapping = load_class_to_idx(SPLIT_DIR / "class_to_idx.json")
    if len(mapping) != config["num_classes"]:
        raise ValueError("Class mapping differs from YAML class count")
    train_loader, val_loader = create_loaders(batch_size, config["num_workers"], config["seed"])
    if len(train_loader.dataset) != 3692 or len(val_loader.dataset) != 795:
        raise ValueError("Unexpected train/validation split size")
    first_train = next(iter(train_loader))
    first_val = next(iter(val_loader))
    for name, (images, labels) in (("train", first_train), ("val", first_val)):
        if images.shape[1:] != (3, 224, 224) or not torch.isfinite(images).all():
            raise ValueError(f"Invalid {name} image batch: {tuple(images.shape)}")
        if labels.min() < 0 or labels.max() >= 18:
            raise ValueError(f"Invalid {name} label")
    val_image_1, val_label_1 = val_loader.dataset[0]
    val_image_2, val_label_2 = val_loader.dataset[0]
    if val_label_1 != val_label_2 or not torch.equal(val_image_1, val_image_2):
        raise ValueError("Validation preprocessing is not deterministic")
    save_augmentation_preview(train_loader.dataset, output / "augmentation_preview.png")
    started = time.perf_counter()
    model = build_model(len(mapping), pretrained=True).to(device)
    model.eval()
    with torch.inference_mode(), torch.autocast("cuda", enabled=config["amp"]):
        initial_output = model(first_val[0].to(device))
    if initial_output.shape != (len(first_val[1]), 18) or not torch.isfinite(initial_output).all():
        raise ValueError("Initial model output is invalid")
    counts = parameter_counts(model)
    criterion = torch.nn.CrossEntropyLoss()
    optimizer = torch.optim.AdamW(model.parameters(), lr=config["learning_rate"],
                                  weight_decay=config.get("weight_decay", .01))
    scaler = torch.amp.GradScaler("cuda", enabled=config["amp"])
    before = model.classifier[2].weight.detach().clone()
    torch.cuda.reset_peak_memory_stats(device)
    try:
        train_metrics = run_epoch(model, train_loader, criterion, device, optimizer=optimizer,
                                  scaler=scaler, amp=config["amp"], max_batches=args.train_batches,
                                  num_classes=len(mapping))
        updated = not torch.equal(before, model.classifier[2].weight)
        if not updated:
            raise RuntimeError("Optimizer did not update the classifier weights")
        val_metrics = run_epoch(model, val_loader, criterion, device, amp=config["amp"],
                                max_batches=args.val_batches, num_classes=len(mapping))
    except torch.cuda.OutOfMemoryError as exc:
        raise RuntimeError(f"CUDA OOM in smoke test at batch size {batch_size}; retry with --batch-size 4") from exc
    model.eval()
    reference = first_val[0][:1].to(device)
    with torch.inference_mode():
        before_save = model(reference).cpu()
    checkpoint_path = output / "smoke_checkpoint.pt"
    smoke_config = {**config, "batch_size": batch_size, "smoke_train_batches": args.train_batches,
                    "smoke_val_batches": args.val_batches}
    save_checkpoint(checkpoint_path, model, mapping, smoke_config, 0, val_metrics["macro_f1"], "smoke_only")
    del model
    torch.cuda.empty_cache()
    loaded, metadata = load_checkpoint(checkpoint_path, device)
    with torch.inference_mode():
        after_load = loaded(reference).cpu()
    difference = (before_save - after_load).abs().max().item()
    if metadata["class_to_idx"] != mapping or after_load.shape != (1, 18) or difference > 1e-5:
        raise ValueError(f"Checkpoint round trip failed, max difference={difference}")
    # Exercise the plotting utility with disposable sample rows. These are never presented as training results.
    fixture = output / "plot_fixture.csv"
    fixture_plots = [output / "loss_curve.png", output / "accuracy_curve.png"]
    try:
        path = fixture
        with path.open("w", encoding="utf-8", newline="") as target:
            writer = csv.DictWriter(target, fieldnames=HISTORY_FIELDS)
            writer.writeheader()
            writer.writerow({"epoch": 1, "train_loss": 1, "train_accuracy": .1,
                             "val_loss": 1.2, "val_accuracy": .08, "val_macro_f1": .05,
                             "learning_rate": .0001, "epoch_seconds": 1,
                             "peak_cuda_memory_bytes": 1})
        plot_history(path, output)
        if not all(plot.is_file() for plot in fixture_plots):
            raise RuntimeError("Training curve plotting did not produce both figures")
    finally:
        for path in [fixture, *fixture_plots]:
            path.unlink(missing_ok=True)
    result = {"purpose": "functionality_smoke_test_only", "environment": environment_info(batch_size),
              "model_name": metadata["model_name"], "weights_source": metadata["weights_source"],
              "model_parameters": counts, "num_classes": len(mapping),
              "dataset_sizes": {"train": len(train_loader.dataset), "val": len(val_loader.dataset)},
              "train": {k: v for k, v in train_metrics.items() if k != "batch_seconds"},
              "validation": {k: v for k, v in val_metrics.items() if k != "batch_seconds"},
              "train_batch_seconds": train_metrics["batch_seconds"],
              "peak_cuda_memory_bytes": torch.cuda.max_memory_allocated(device),
              "peak_cuda_reserved_bytes": torch.cuda.max_memory_reserved(device),
              "checkpoint_max_abs_difference": difference, "optimizer_updated": updated,
              "oom": False, "plotting_function_verified": True,
              "elapsed_seconds": time.perf_counter() - started}
    write_json(output / "smoke_result.json", result)
    print(result, flush=True)


if __name__ == "__main__":
    main()
