"""Full training entry point. Run only after smoke-test review."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import torch
import yaml

from .data import SPLIT_DIR, create_loaders, load_class_to_idx
from .model import build_model, parameter_counts
from .reporting import generate_report
from .utils import (allocate_run_dir, environment_info, plot_history, read_config,
                    require_cuda, save_checkpoint, set_seed, write_history, write_json)


def macro_f1(targets: list[int], predictions: list[int], num_classes: int) -> float:
    if len(targets) != len(predictions) or not targets:
        raise ValueError("Expected equal, nonempty target and prediction arrays")
    scores = []
    for cls in range(num_classes):
        tp = sum(t == cls and p == cls for t, p in zip(targets, predictions))
        fp = sum(t != cls and p == cls for t, p in zip(targets, predictions))
        fn = sum(t == cls and p != cls for t, p in zip(targets, predictions))
        scores.append(2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0)
    return sum(scores) / num_classes


def run_epoch(model, loader, criterion, device, *, optimizer=None, scaler=None,
              amp=True, max_batches=None, num_classes=18):
    training = optimizer is not None
    model.train(training)
    total_loss = correct = seen = 0
    targets, predictions = [], []
    batch_times = []
    context = torch.enable_grad() if training else torch.inference_mode()
    with context:
        for batch_idx, (images, labels) in enumerate(loader):
            if max_batches is not None and batch_idx >= max_batches:
                break
            start = time.perf_counter()
            images = images.to(device, non_blocking=True)
            labels = labels.to(device, non_blocking=True)
            if not torch.isfinite(images).all():
                raise ValueError("Images contain NaN or Inf")
            if labels.min() < 0 or labels.max() >= num_classes:
                raise ValueError("Label outside the class mapping")
            if training:
                optimizer.zero_grad(set_to_none=True)
            with torch.autocast(device_type="cuda", enabled=amp):
                logits = model(images)
                if logits.shape != (len(labels), num_classes):
                    raise ValueError(f"Incorrect model output shape: {tuple(logits.shape)}")
                loss = criterion(logits, labels)
            if not torch.isfinite(loss):
                raise FloatingPointError("Non-finite loss")
            if training:
                if scaler is not None and scaler.is_enabled():
                    scaler.scale(loss).backward()
                    scaler.step(optimizer)
                    scaler.update()
                else:
                    loss.backward()
                    optimizer.step()
            predicted = logits.argmax(1)
            n = len(labels)
            total_loss += loss.item() * n
            correct += (predicted == labels).sum().item()
            seen += n
            targets.extend(labels.cpu().tolist())
            predictions.extend(predicted.cpu().tolist())
            if device.type == "cuda":
                torch.cuda.synchronize(device)
            batch_times.append(time.perf_counter() - start)
    if not seen:
        raise ValueError("No batches were processed")
    return {"loss": total_loss / seen, "accuracy": correct / seen,
            "macro_f1": macro_f1(targets, predictions, num_classes),
            "samples": seen, "batches": len(batch_times), "batch_seconds": batch_times}


def train(config_path: str | Path) -> None:
    config = read_config(config_path)
    if config["device"] != "cuda":
        raise ValueError("Formal training requires device: cuda")
    device = require_cuda()
    set_seed(config["seed"])
    run_dir = allocate_run_dir(config)
    print(f"Experiment directory: {run_dir}", flush=True)
    (run_dir / "train_config.yaml").write_text(
        yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8")
    write_json(run_dir / "run_status.json", {"status": "running", "completed_epochs": 0})
    rows = []
    best_f1 = -1.0
    stale = 0
    started_training = time.perf_counter()
    try:
        mapping = load_class_to_idx(SPLIT_DIR / "class_to_idx.json")
        if len(mapping) != config["num_classes"]:
            raise ValueError("Configured class count differs from accepted class mapping")
        train_loader, val_loader = create_loaders(config["batch_size"], config["num_workers"], config["seed"])
        model = build_model(config["num_classes"], pretrained=True).to(device)
        optimizer = torch.optim.AdamW(model.parameters(), lr=config["learning_rate"],
                                      weight_decay=config.get("weight_decay", .01))
        criterion = torch.nn.CrossEntropyLoss()
        scaler = torch.amp.GradScaler("cuda", enabled=config["amp"])
        write_json(run_dir / "run_info.json", {
            "config": config, "environment": environment_info(config["batch_size"]),
            "experiment_dir": str(run_dir), "model_parameters": parameter_counts(model),
            "dataset_sizes": {"train": len(train_loader.dataset), "val": len(val_loader.dataset)}})
        classifier_before = model.classifier[2].weight.detach().clone()
        torch.cuda.reset_peak_memory_stats(device)
        for epoch in range(1, config["epochs"] + 1):
            started = time.perf_counter()
            torch.cuda.reset_peak_memory_stats(device)
            train_metrics = run_epoch(model, train_loader, criterion, device, optimizer=optimizer,
                                      scaler=scaler, amp=config["amp"], num_classes=len(mapping))
            if epoch == 1 and torch.equal(classifier_before, model.classifier[2].weight):
                raise RuntimeError("Classifier weights did not update during the first epoch")
            val_metrics = run_epoch(model, val_loader, criterion, device,
                                    amp=config["amp"], num_classes=len(mapping))
            row = {"epoch": epoch, "train_loss": train_metrics["loss"],
                   "train_accuracy": train_metrics["accuracy"], "val_loss": val_metrics["loss"],
                   "val_accuracy": val_metrics["accuracy"], "val_macro_f1": val_metrics["macro_f1"],
                   "learning_rate": optimizer.param_groups[0]["lr"],
                   "epoch_seconds": time.perf_counter() - started,
                   "peak_cuda_memory_bytes": torch.cuda.max_memory_allocated(device)}
            rows.append(row)
            write_history(run_dir / "metrics.csv", rows)
            print(row, flush=True)
            if val_metrics["macro_f1"] > best_f1:
                best_f1 = val_metrics["macro_f1"]
                stale = 0
                save_checkpoint(run_dir / "best.pt", model, mapping, config, epoch, best_f1, "best")
            else:
                stale += 1
            save_checkpoint(run_dir / "last.pt", model, mapping, config, epoch, best_f1, "last",
                            optimizer=optimizer, scaler=scaler, stale_epochs=stale)
            if stale >= config["patience"]:
                print(f"Early stopping after {epoch} epochs", flush=True)
                break
        resource_info = {
            "peak_cuda_memory_bytes": max((r["peak_cuda_memory_bytes"] for r in rows), default=0),
            "actual_batch_size": config["batch_size"],
            "elapsed_seconds": time.perf_counter() - started_training,
            "completed_epochs": len(rows)}
        write_json(run_dir / "resource_info.json", resource_info)
        plot_history(run_dir / "metrics.csv", run_dir)
        report = generate_report(run_dir / "metrics.csv", run_dir / "best.pt", run_dir,
                                 config, run_dir / "resource_info.json", device="cuda")
        write_json(run_dir / "run_status.json", {"status": "completed", "completed_epochs": len(rows),
                                                  "best_epoch": report["best_epoch"],
                                                  "best_val_macro_f1": report["val_macro_f1"]})
        print(report, flush=True)
    except BaseException as exc:
        if rows:
            write_history(run_dir / "metrics.csv", rows)
            write_json(run_dir / "resource_info.json", {
                "peak_cuda_memory_bytes": max(r["peak_cuda_memory_bytes"] for r in rows),
                "actual_batch_size": config["batch_size"],
                "elapsed_seconds": time.perf_counter() - started_training,
                "completed_epochs": len(rows)})
            try:
                plot_history(run_dir / "metrics.csv", run_dir)
            except Exception:
                pass
        message = (f"CUDA out of memory at batch size {config['batch_size']}; lower it in YAML"
                   if isinstance(exc, torch.cuda.OutOfMemoryError) else str(exc))
        write_json(run_dir / "run_status.json", {"status": "interrupted" if isinstance(exc, KeyboardInterrupt) else "failed",
                                                  "completed_epochs": len(rows),
                                                  "error_type": type(exc).__name__, "error": message})
        if isinstance(exc, torch.cuda.OutOfMemoryError):
            raise RuntimeError(message) from exc
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/convnext_tiny.yaml")
    args = parser.parse_args()
    train(args.config)


if __name__ == "__main__":
    main()
