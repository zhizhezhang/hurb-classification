"""One-time, read-only final evaluation of the selected ConvNeXt-Tiny checkpoint."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch
from PIL import Image, ImageOps
from torch.utils.data import DataLoader

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from herb_classifier.data import (DATASET_ROOT, SPLIT_DIR, HerbImageDataset,
                                  get_eval_transform, get_preprocess_config, load_class_to_idx)
from herb_classifier.model import load_checkpoint
from herb_classifier.reporting import _chinese_font, _plot_confusion
from herb_classifier.utils import environment_info, write_json

DEFAULT_CHECKPOINT = ROOT / "runs" / "convnext_tiny_lr3e5_20261028_113820_001" / "best.pt"
DEFAULT_OUTPUT = ROOT / "reports" / "final_evaluation"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_manifest(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def preflight(checkpoint_path: Path) -> dict:
    """Validate selected weights, immutable split and preprocessing before inference."""
    if checkpoint_path.name != "best.pt" or not checkpoint_path.is_file():
        raise ValueError("Final evaluation requires the selected best.pt checkpoint")
    mapping_path = SPLIT_DIR / "class_to_idx.json"
    preprocess_path = SPLIT_DIR / "preprocess_config.json"
    test_path = SPLIT_DIR / "test.csv"
    mapping = load_class_to_idx(mapping_path)
    if len(mapping) != 18:
        raise ValueError("Expected the accepted 18-class mapping")
    saved_preprocess = json.loads(preprocess_path.read_text(encoding="utf-8"))
    if saved_preprocess != get_preprocess_config():
        raise ValueError("Accepted preprocessing differs from the current deterministic transform")
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    if (checkpoint.get("kind") != "best" or checkpoint.get("epoch") != 8 or
            checkpoint.get("class_to_idx") != mapping or checkpoint.get("num_classes") != 18 or
            checkpoint.get("preprocess_config") != saved_preprocess or
            checkpoint.get("model_name") != "convnext_tiny"):
        raise ValueError("Checkpoint metadata differs from the selected Run02 best model")
    manifest = read_manifest(test_path)
    if len(manifest) != 788:
        raise ValueError(f"Expected 788 test images, found {len(manifest)}")
    paths = [row["path"] for row in manifest]
    if len(set(paths)) != len(paths):
        raise ValueError("Duplicate paths in test.csv")
    other_paths = {row["path"] for name in ("train.csv", "val.csv")
                   for row in read_manifest(SPLIT_DIR / name)}
    if set(paths) & other_paths:
        raise ValueError("Test paths overlap with training or validation")
    for row in manifest:
        if row["class"] not in mapping or int(row["class_idx"]) != mapping[row["class"]]:
            raise ValueError(f"Class mapping mismatch: {row['path']}")
        image_path = (DATASET_ROOT / row["path"]).resolve()
        if DATASET_ROOT not in image_path.parents or not image_path.is_file():
            raise FileNotFoundError(f"Missing or unsafe test image: {image_path}")
    train_config = checkpoint["training_config"]
    with (checkpoint_path.parent / "metrics.csv").open(encoding="utf-8-sig", newline="") as source:
        history = list(csv.DictReader(source))
    best_row = next((row for row in history if int(row["epoch"]) == checkpoint["epoch"]), None)
    if best_row is None or not math.isclose(float(best_row["val_macro_f1"]),
                                            checkpoint["best_val_macro_f1"], abs_tol=1e-12):
        raise ValueError("Best epoch or Macro-F1 does not match the training log")
    return {"mapping": mapping, "manifest": manifest, "preprocess": saved_preprocess,
            "checkpoint_epoch": checkpoint["epoch"], "train_config": train_config,
            "validation_accuracy": float(best_row["val_accuracy"]),
            "validation_macro_f1": float(best_row["val_macro_f1"]),
            "hashes": {"checkpoint_sha256": sha256_file(checkpoint_path),
                       "test_csv_sha256": sha256_file(test_path),
                       "class_to_idx_sha256": sha256_file(mapping_path),
                       "preprocess_config_sha256": sha256_file(preprocess_path)}}


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def plot_errors(rows: list[dict], output: Path) -> None:
    _chinese_font()
    # Keep different confusion pairs visible; fill remaining slots by confidence.
    ranked = sorted(rows, key=lambda row: row["predicted_confidence"], reverse=True)
    chosen, pairs = [], set()
    for row in ranked:
        pair = (row["true_class"], row["predicted_class"])
        if pair not in pairs:
            chosen.append(row)
            pairs.add(pair)
        if len(chosen) == 16:
            break
    for row in ranked:
        if len(chosen) == 16:
            break
        if row not in chosen:
            chosen.append(row)
    columns = 4
    count = max(1, len(chosen))
    lines = (count + columns - 1) // columns
    fig, axes = plt.subplots(lines, columns, figsize=(14, lines * 3.4), squeeze=False)
    for ax in axes.flat:
        ax.axis("off")
    if not chosen:
        axes[0, 0].text(.5, .5, "测试集没有误分类样本", ha="center", va="center")
    for ax, row in zip(axes.flat, chosen):
        with Image.open(DATASET_ROOT / row["path"]) as image:
            original = ImageOps.exif_transpose(image).convert("RGB")
            ax.imshow(original)
        ax.set_title(f"真实：{row['true_class']} → 预测：{row['predicted_class']}\n"
                     f"预测置信度：{row['predicted_confidence']:.3f}", fontsize=10)
        ax.axis("off")
    fig.tight_layout()
    fig.savefig(output, dpi=160)
    plt.close(fig)


def evaluate(checkpoint_path: Path, output_dir: Path, batch_size: int = 8,
             num_workers: int = 0, device: str = "cuda") -> dict:
    if output_dir.exists():
        raise FileExistsError(f"Evaluation directory already exists: {output_dir}")
    if batch_size < 1 or num_workers < 0:
        raise ValueError("batch_size must be positive and num_workers nonnegative")
    if device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA is unavailable; choose --device cpu explicitly if needed")
    facts = preflight(checkpoint_path)
    mapping, manifest = facts["mapping"], facts["manifest"]
    names = [name for name, _ in sorted(mapping.items(), key=lambda item: item[1])]
    dataset = HerbImageDataset(SPLIT_DIR / "test.csv", DATASET_ROOT,
                               SPLIT_DIR / "class_to_idx.json", transform=get_eval_transform())
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=False,
                        num_workers=num_workers, pin_memory=device == "cuda")
    output_dir.mkdir(parents=True, exist_ok=False)
    write_json(output_dir / "evaluation_status.json", {"status": "running"})
    try:
        model, checkpoint = load_checkpoint(checkpoint_path, device)
        model.eval()
        matrix = np.zeros((18, 18), dtype=np.int64)
        predictions = []
        mistakes = []
        offset = 0
        with torch.inference_mode():
            for batch_number, (images, labels) in enumerate(loader, 1):
                with torch.autocast("cuda", enabled=device == "cuda" and facts["train_config"]["amp"]):
                    logits = model(images.to(device, non_blocking=True))
                if logits.shape != (len(labels), 18) or not torch.isfinite(logits).all():
                    raise ValueError("Invalid test logits")
                probabilities = logits.float().softmax(dim=1).cpu()
                predicted = probabilities.argmax(dim=1).tolist()
                for i, (true_idx, pred_idx) in enumerate(zip(labels.tolist(), predicted)):
                    row = manifest[offset + i]
                    matrix[true_idx, pred_idx] += 1
                    item = {"path": row["path"], "true_class_idx": true_idx,
                            "true_class": names[true_idx], "predicted_class_idx": pred_idx,
                            "predicted_class": names[pred_idx],
                            "predicted_confidence": float(probabilities[i, pred_idx]),
                            "true_class_probability": float(probabilities[i, true_idx])}
                    predictions.append(item)
                    if true_idx != pred_idx:
                        mistakes.append(item)
                offset += len(labels)
                if batch_number % 25 == 0 or offset == 788:
                    print(f"Test inference: {offset}/788 images", flush=True)
        if offset != 788 or int(matrix.sum()) != 788:
            raise RuntimeError("Test inference did not cover all 788 samples")
        fields = ["path", "true_class_idx", "true_class", "predicted_class_idx",
                  "predicted_class", "predicted_confidence", "true_class_probability"]
        write_csv(output_dir / "test_predictions.csv", predictions, fields)
        write_csv(output_dir / "misclassified_samples.csv", mistakes, fields)
        class_rows = []
        for index, name in enumerate(names):
            tp = int(matrix[index, index])
            support = int(matrix[index, :].sum())
            predicted_count = int(matrix[:, index].sum())
            fp, fn = predicted_count - tp, support - tp
            precision = tp / predicted_count if predicted_count else 0.0
            recall = tp / support if support else 0.0
            f1 = 2 * tp / (support + predicted_count) if support + predicted_count else 0.0
            class_rows.append({"class_idx": index, "class": name, "support": support,
                               "true_positive": tp, "false_positive": fp, "false_negative": fn,
                               "precision": precision, "recall": recall, "f1_score": f1})
        write_csv(output_dir / "classification_report.csv", class_rows, list(class_rows[0]))
        correct = int(np.trace(matrix))
        environment = environment_info(batch_size)
        environment["device"] = device
        metrics = {
            "test_samples": 788, "correct": correct, "incorrect": 788 - correct,
            "accuracy": correct / 788,
            "macro_precision": float(np.mean([row["precision"] for row in class_rows])),
            "macro_recall": float(np.mean([row["recall"] for row in class_rows])),
            "macro_f1": float(np.mean([row["f1_score"] for row in class_rows])),
            "weighted_f1": sum(row["f1_score"] * row["support"] for row in class_rows) / 788,
            "confusion_matrix": matrix.tolist(),
            "class_to_idx": mapping,
            "preprocess_config": facts["preprocess"],
            "evaluation_config": {"checkpoint": str(checkpoint_path), "checkpoint_kind": "best",
                                  "checkpoint_epoch": checkpoint["epoch"], "test_csv": str(SPLIT_DIR / "test.csv"),
                                  "batch_size": batch_size, "num_workers": num_workers,
                                  "device": device, "amp": facts["train_config"]["amp"],
                                  "shuffle": False, "inference_mode": True},
            "source_hashes": facts["hashes"],
            "environment": environment,
            "validation_at_best_epoch": {"accuracy": facts["validation_accuracy"],
                                         "macro_f1": facts["validation_macro_f1"]},
        }
        write_json(output_dir / "test_metrics.json", metrics)
        _chinese_font()
        _plot_confusion(matrix, names, output_dir / "confusion_matrix.png", False, "测试集")
        _plot_confusion(matrix, names, output_dir / "confusion_matrix_normalized.png", True, "测试集")
        plot_errors(mistakes, output_dir / "misclassified_samples.png")
        confusions = sorted(((int(matrix[i, j]), names[i], names[j])
                             for i in range(18) for j in range(18) if i != j and matrix[i, j] > 0),
                            reverse=True)
        weakest = sorted(class_rows, key=lambda row: row["f1_score"])[:5]
        lines = ["# ConvNeXt-Tiny 最终测试集评估", "",
                 f"- 模型：{checkpoint_path}",
                 f"- 最佳 Epoch：{checkpoint['epoch']}；仅使用 `best.pt`",
                 f"- 测试清单：{SPLIT_DIR / 'test.csv'}（788 张，18 类）",
                 f"- Test Accuracy：{metrics['accuracy']:.6f}",
                 f"- Test Macro-Precision：{metrics['macro_precision']:.6f}",
                 f"- Test Macro-Recall：{metrics['macro_recall']:.6f}",
                 f"- Test Macro-F1：{metrics['macro_f1']:.6f}",
                 f"- Test Weighted-F1：{metrics['weighted_f1']:.6f}",
                 f"- 正确 / 错误：{correct} / {788 - correct}",
                 f"- 最佳 Epoch 验证 Accuracy：{facts['validation_accuracy']:.6f}；测试差值：{metrics['accuracy'] - facts['validation_accuracy']:+.6f}",
                 f"- 最佳 Epoch 验证 Macro-F1：{facts['validation_macro_f1']:.6f}；测试差值：{metrics['macro_f1'] - facts['validation_macro_f1']:+.6f}",
                 "", "## 各类别表现", "",
                 "| 类别 | 样本数 | Precision | Recall | F1-score |",
                 "|---|---:|---:|---:|---:|"]
        for row in class_rows:
            lines.append(f"| {row['class']} | {row['support']} | {row['precision']:.3f} | {row['recall']:.3f} | {row['f1_score']:.3f} |")
        lines.extend(["", "## 需要重点阅读的类别", "",
                      "、".join(f"{row['class']}（F1 {row['f1_score']:.3f}）" for row in weakest),
                      "", "## 主要混淆关系", ""])
        lines.extend(f"- 真实{true_name} → 预测{pred_name}：{count} 张"
                     for count, true_name, pred_name in confusions[:10])
        lines.extend(["", "## 错误样本观察", "",
                      "典型错误见 `misclassified_samples.png`；图像背景、药材形态及质量因素需要结合原图人工复核，不能仅凭混淆矩阵确定原因。",
                      "", "评估只执行固定测试集推理；未重新训练、调参或更改模型。", ""])
        (output_dir / "evaluation_summary.md").write_text("\n".join(lines), encoding="utf-8")
        write_json(output_dir / "evaluation_status.json", {"status": "completed", "samples": 788,
                                                           "checkpoint_sha256": facts["hashes"]["checkpoint_sha256"]})
        return {key: metrics[key] for key in ("test_samples", "correct", "incorrect", "accuracy",
                                             "macro_precision", "macro_recall", "macro_f1", "weighted_f1")}
    except BaseException as exc:
        write_json(output_dir / "evaluation_status.json", {"status": "failed", "error": str(exc),
                                                           "error_type": type(exc).__name__})
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--num-workers", type=int, default=0)
    parser.add_argument("--device", choices=("cuda", "cpu"), default="cuda")
    parser.add_argument("--preflight", action="store_true", help="Inspect metadata and list only; do not run inference")
    args = parser.parse_args()
    checkpoint = args.checkpoint if args.checkpoint.is_absolute() else (ROOT / args.checkpoint).resolve()
    output = args.output if args.output.is_absolute() else (ROOT / args.output).resolve()
    if ROOT not in output.parents:
        raise ValueError("Output directory must be inside the inner training project")
    if args.preflight:
        facts = preflight(checkpoint)
        print({"checkpoint_epoch": facts["checkpoint_epoch"], "test_samples": len(facts["manifest"]),
               "classes": len(facts["mapping"]), "preprocess_matches": True,
               "checkpoint_sha256": facts["hashes"]["checkpoint_sha256"]})
        return
    print(evaluate(checkpoint, output, args.batch_size, args.num_workers, args.device), flush=True)


if __name__ == "__main__":
    main()
