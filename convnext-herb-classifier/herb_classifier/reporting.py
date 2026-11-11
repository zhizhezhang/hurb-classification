"""Automatic plots and validation report from a completed real training run."""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np
import torch
from torch.utils.data import DataLoader

from .data import (DATASET_ROOT, SPLIT_DIR, HerbImageDataset,
                   get_eval_transform, load_class_to_idx)
from .model import load_checkpoint


def _chinese_font() -> None:
    available = {font.name for font in font_manager.fontManager.ttflist}
    for name in ("Microsoft YaHei", "Noto Sans SC", "SimHei", "Noto Sans CJK SC"):
        if name in available:
            plt.rcParams["font.sans-serif"] = [name]
            plt.rcParams["axes.unicode_minus"] = False
            return
    raise RuntimeError("No Chinese font found; install Microsoft YaHei, Noto Sans SC or SimHei")


def _read_history(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))
    required = {"epoch", "train_loss", "val_loss", "train_accuracy", "val_accuracy",
                "val_macro_f1", "learning_rate", "epoch_seconds"}
    if not rows or not required.issubset(rows[0]):
        raise ValueError("metrics.csv is empty or lacks required columns")
    if [int(row["epoch"]) for row in rows] != list(range(1, len(rows) + 1)):
        raise ValueError("metrics.csv epoch sequence is incomplete")
    for row in rows:
        if not all(math.isfinite(float(row[key])) for key in required):
            raise ValueError("metrics.csv contains NaN or Inf")
    return rows


def plot_results(metrics_path: str | Path, output_path: str | Path) -> None:
    """Plot three panels using only the recorded epoch metrics."""
    _chinese_font()
    rows = _read_history(Path(metrics_path))
    epochs = [int(row["epoch"]) for row in rows]
    best = max(rows, key=lambda row: float(row["val_macro_f1"]))
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.7))
    specs = [("loss", "损失", "Loss"), ("accuracy", "准确率", "Accuracy")]
    for ax, (key, title, label) in zip(axes[:2], specs):
        ax.plot(epochs, [float(row[f"train_{key}"]) for row in rows], "o-", label="训练集")
        ax.plot(epochs, [float(row[f"val_{key}"]) for row in rows], "o-", label="验证集")
        ax.set(title=title, xlabel="Epoch", ylabel=label)
        ax.axvline(int(best["epoch"]), color="gray", linestyle="--", alpha=.7)
        ax.legend()
        ax.grid(alpha=.25)
    axes[2].plot(epochs, [float(row["val_macro_f1"]) for row in rows], "o-", color="#7b3294")
    axes[2].axvline(int(best["epoch"]), color="gray", linestyle="--", alpha=.7,
                    label=f"最佳 Epoch {best['epoch']}")
    axes[2].set(title="验证集 Macro-F1", xlabel="Epoch", ylabel="Macro-F1")
    axes[2].legend()
    axes[2].grid(alpha=.25)
    for ax in axes:
        ax.set_xticks(epochs)
    fig.tight_layout()
    fig.savefig(output_path, dpi=170)
    plt.close(fig)


def _plot_confusion(matrix: np.ndarray, names: list[str], path: Path, normalized: bool,
                    split_name: str = "验证集") -> None:
    values = matrix.astype(float)
    if normalized:
        denominators = matrix.sum(axis=1, keepdims=True)
        values = np.divide(values, denominators, out=np.zeros_like(values), where=denominators != 0)
    fig, ax = plt.subplots(figsize=(12, 11))
    im = ax.imshow(values, cmap="Blues", vmin=0, vmax=1 if normalized else None)
    ax.set_xticks(range(len(names)), names, rotation=55, ha="right")
    ax.set_yticks(range(len(names)), names)
    ax.set(xlabel="预测类别", ylabel="真实类别",
           title=f"{split_name}混淆矩阵（按真实类别归一化）" if normalized else f"{split_name}混淆矩阵")
    for row in range(len(names)):
        for column in range(len(names)):
            count = matrix[row, column]
            if count:
                value = f"{values[row, column]:.2f}" if normalized else str(count)
                color = "white" if values[row, column] > (0.5 if normalized else values.max() / 2) else "black"
                ax.text(column, row, value, ha="center", va="center", fontsize=7, color=color)
    fig.colorbar(im, ax=ax, shrink=.75)
    fig.tight_layout()
    fig.savefig(path, dpi=170)
    plt.close(fig)


def generate_report(metrics_path: str | Path, best_path: str | Path,
                    output_dir: str | Path, config: dict,
                    resource_info_path: str | Path | None = None,
                    device: str = "cuda") -> dict:
    """Reload best.pt, evaluate all validation images, and write real-data figures."""
    _chinese_font()
    metrics_path, best_path, output_dir = Path(metrics_path), Path(best_path), Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = _read_history(metrics_path)
    mapping = load_class_to_idx(SPLIT_DIR / "class_to_idx.json")
    model, checkpoint = load_checkpoint(best_path, device)
    if checkpoint["kind"] != "best" or checkpoint["class_to_idx"] != mapping:
        raise ValueError("Best checkpoint kind or class mapping is invalid")
    best = next((row for row in rows if int(row["epoch"]) == checkpoint["epoch"]), None)
    if best is None or float(best["val_macro_f1"]) != max(float(row["val_macro_f1"]) for row in rows):
        raise ValueError("Best checkpoint does not match the top validation Macro-F1 epoch")
    dataset = HerbImageDataset(SPLIT_DIR / "val.csv", DATASET_ROOT,
                               SPLIT_DIR / "class_to_idx.json", transform=get_eval_transform())
    loader = DataLoader(dataset, batch_size=config["batch_size"], shuffle=False,
                        num_workers=config["num_workers"], pin_memory=device == "cuda")
    truth, predictions = [], []
    with torch.inference_mode():
        for images, labels in loader:
            with torch.autocast("cuda", enabled=device == "cuda" and config["amp"]):
                logits = model(images.to(device, non_blocking=True))
            if logits.shape != (len(labels), len(mapping)) or not torch.isfinite(logits).all():
                raise ValueError("Invalid validation logits")
            truth.extend(labels.tolist())
            predictions.extend(logits.argmax(1).cpu().tolist())
    if len(truth) != len(dataset):
        raise RuntimeError("Validation set was not fully evaluated")
    matrix = np.zeros((len(mapping), len(mapping)), dtype=np.int64)
    np.add.at(matrix, (truth, predictions), 1)
    accuracy = float(np.trace(matrix) / matrix.sum())
    class_rows = []
    names = [name for name, _ in sorted(mapping.items(), key=lambda item: item[1])]
    for index, name in enumerate(names):
        tp = int(matrix[index, index])
        support = int(matrix[index, :].sum())
        predicted = int(matrix[:, index].sum())
        precision = tp / predicted if predicted else 0.0
        recall = tp / support if support else 0.0
        f1 = 2 * tp / (support + predicted) if support + predicted else 0.0
        class_rows.append({"class_idx": index, "class": name, "support": support,
                           "precision": precision, "recall": recall, "f1_score": f1})
    macro_f1 = sum(row["f1_score"] for row in class_rows) / len(class_rows)
    if abs(accuracy - float(best["val_accuracy"])) > 1e-6 or abs(macro_f1 - float(best["val_macro_f1"])) > 1e-6:
        raise ValueError("Reloaded best checkpoint metrics differ from the recorded best epoch")
    plot_results(metrics_path, output_dir / "results.png")
    _plot_confusion(matrix, names, output_dir / "confusion_matrix.png", normalized=False)
    _plot_confusion(matrix, names, output_dir / "confusion_matrix_normalized.png", normalized=True)
    with (output_dir / "classification_report.csv").open("w", encoding="utf-8-sig", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=class_rows[0].keys())
        writer.writeheader()
        writer.writerows(class_rows)
    resources = {}
    if resource_info_path is not None and Path(resource_info_path).is_file():
        resources = json.loads(Path(resource_info_path).read_text(encoding="utf-8"))
    lowest = sorted(class_rows, key=lambda row: row["f1_score"])[:3]
    total_seconds = resources.get("elapsed_seconds")
    peak_bytes = resources.get("peak_cuda_memory_bytes")
    summary = ["# ConvNeXt-Tiny 训练总结", "",
               f"- 实验名称：{config.get('experiment_name', 'legacy_run')}",
               f"- 完成 Epoch：{len(rows)} / {config['epochs']}",
               f"- 最佳 Epoch：{checkpoint['epoch']}（完整验证集 Macro-F1）",
               f"- 最佳验证 Accuracy：{accuracy:.6f}",
               f"- 最佳验证 Macro-F1：{macro_f1:.6f}",
               f"- 最佳 Epoch Train Loss：{float(best['train_loss']):.6f}",
               f"- 最佳 Epoch Validation Loss：{float(best['val_loss']):.6f}",
               f"- 验证样本：{len(truth)}，类别：{len(names)}",
               f"- 训练总耗时：{float(total_seconds):.1f} 秒" if total_seconds is not None else "- 训练总耗时：未提供",
               f"- 峰值已分配显存：{int(peak_bytes) / 1048576:.1f} MiB" if peak_bytes is not None else "- 峰值显存：未提供",
               "", "## 趋势与类别表现", "",
               f"- 首轮 Train/Val Loss：{float(rows[0]['train_loss']):.4f} / {float(rows[0]['val_loss']):.4f}",
               f"- 末轮 Train/Val Loss：{float(rows[-1]['train_loss']):.4f} / {float(rows[-1]['val_loss']):.4f}",
               "- 验证集 F1 较低的三类：" + "、".join(f"{r['class']} {r['f1_score']:.3f}" for r in lowest),
               "", "| 类别 | 样本数 | Precision | Recall | F1-score |",
               "|---|---:|---:|---:|---:|"]
    for row in class_rows:
        summary.append(f"| {row['class']} | {row['support']} | {row['precision']:.3f} | {row['recall']:.3f} | {row['f1_score']:.3f} |")
    summary += ["", "本报告只使用训练日志与完整验证集；未读取测试集。", ""]
    (output_dir / "training_summary.md").write_text("\n".join(summary), encoding="utf-8")
    return {"best_epoch": checkpoint["epoch"], "val_accuracy": accuracy,
            "val_macro_f1": macro_f1, "validation_samples": len(truth),
            "classes": len(names), "output_dir": str(output_dir)}
