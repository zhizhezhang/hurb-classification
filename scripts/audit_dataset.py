"""Read-only image dataset audit for a class-per-directory dataset."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import math
import random
import statistics
import sys
import warnings
from collections import Counter, defaultdict
from itertools import combinations, product
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps
from scipy.fft import dctn


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tif", ".tiff", ".webp"}
EXTENSION_FORMAT = {".jpg": "JPEG", ".jpeg": "JPEG", ".tif": "TIFF", ".tiff": "TIFF"}
FONT_FILES = (Path("C:/Windows/Fonts/msyh.ttc"), Path("C:/Windows/Fonts/simhei.ttf"))


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True, help="Dataset directory; direct subdirectories are classes")
    parser.add_argument("--output", type=Path, default=Path("reports/data_audit"))
    parser.add_argument("--seed", type=int, default=20261027)
    parser.add_argument("--samples-per-class", type=int, default=12)
    parser.add_argument("--phash-threshold", type=int, default=6, help="Hamming radius, 0-6")
    parser.add_argument("--max-candidate-comparisons", type=int, default=2_000_000)
    parser.add_argument("--max-similar-pairs", type=int, default=200_000)
    args = parser.parse_args()
    if not 0 <= args.phash_threshold <= 6:
        parser.error("--phash-threshold must be between 0 and 6")
    if args.samples_per_class < 0 or args.max_candidate_comparisons < 1 or args.max_similar_pairs < 1:
        parser.error("sample count must be nonnegative and comparison/pair limits must be positive")
    return args


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def perceptual_hash(image: Image.Image) -> int:
    """64-bit DCT pHash after EXIF orientation; RGB is converted to luminance."""
    gray = ImageOps.exif_transpose(image).convert("L").resize((32, 32), Image.Resampling.LANCZOS)
    low = dctn(np.asarray(gray, dtype=np.float32), type=2, norm="ortho")[:8, :8]
    median = np.median(low[1:, :].ravel())  # DC does not set the threshold.
    bits = (low > median).ravel()
    value = 0
    for bit in bits:
        value = (value << 1) | int(bit)
    return value


def add_anomaly(anomalies: list[dict], row: dict, code: str, detail: str = "") -> None:
    row["flags"].append(code)
    anomalies.append({"class": row["class"], "path": row["path"], "issue": code, "detail": detail})


def inspect_file(path: Path, dataset: Path, class_name: str, anomalies: list[dict]) -> dict:
    relative = path.relative_to(dataset).as_posix()
    row = {"class": class_name, "path": relative, "extension": path.suffix.lower(), "format": "",
           "valid": False, "width": "", "height": "", "aspect_ratio": "", "mode": "",
           "file_size_bytes": "", "sha256": "", "phash": "", "flags": []}
    try:
        row["file_size_bytes"] = path.stat().st_size
        row["sha256"] = sha256_file(path)
        if row["file_size_bytes"] == 0:
            add_anomaly(anomalies, row, "empty_file")
        if row["extension"] not in IMAGE_EXTENSIONS:
            add_anomaly(anomalies, row, "unsupported_extension", "Skipped image decode")
            return row
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                image.load()  # Decode pixels as well as checking the header.
                row["format"] = image.format or ""
                row["width"], row["height"] = image.size
                row["mode"] = image.mode
                row["aspect_ratio"] = round(image.width / image.height, 4)
                row["phash"] = f"{perceptual_hash(image):016x}"
        row["valid"] = True
        expected = EXTENSION_FORMAT.get(row["extension"], row["extension"].lstrip(".").upper())
        if row["format"] != expected:
            add_anomaly(anomalies, row, "extension_format_mismatch", f"extension={expected}; content={row['format']}")
        if min(row["width"], row["height"]) < 128:
            add_anomaly(anomalies, row, "small_dimension", f"{row['width']}x{row['height']}")
        if row["aspect_ratio"] > 3 or row["aspect_ratio"] < 1 / 3:
            add_anomaly(anomalies, row, "extreme_aspect_ratio", str(row["aspect_ratio"]))
        if row["mode"] not in {"RGB", "RGBA", "L"}:
            add_anomaly(anomalies, row, "unusual_color_mode", row["mode"])
        if row["file_size_bytes"] > 20 * 1024 * 1024:
            add_anomaly(anomalies, row, "large_file", str(row["file_size_bytes"]))
    except Exception as exc:  # A bad file must not abort the remainder of the audit.
        add_anomaly(anomalies, row, "decode_error", f"{type(exc).__name__}: {exc}")
    return row


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def set_chinese_font():
    logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    for file in FONT_FILES:
        if file.exists():
            from matplotlib import font_manager
            font_manager.fontManager.addfont(str(file))
            plt.rcParams["font.family"] = font_manager.FontProperties(fname=str(file)).get_name()
            break
    plt.rcParams["axes.unicode_minus"] = False
    return plt


def make_charts(valid_rows: list[dict], classes: list[str], output: Path) -> None:
    plt = set_chinese_font()
    counts = Counter(row["class"] for row in valid_rows)
    fig, ax = plt.subplots(figsize=(12, 6))
    bars = ax.bar(classes, [counts[name] for name in classes], color="#3d7892")
    ax.bar_label(bars, padding=3, fontsize=8)
    ax.set(title="各类别有效图片数量", xlabel="类别", ylabel="图片数")
    ax.tick_params(axis="x", rotation=55)
    ax.margins(y=0.1)
    fig.tight_layout()
    fig.savefig(output / "class_counts.png", dpi=160)
    plt.close(fig)

    widths = [row["width"] for row in valid_rows]
    heights = [row["height"] for row in valid_rows]
    ratios = [row["aspect_ratio"] for row in valid_rows]
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    axes[0].scatter(widths, heights, s=8, alpha=0.24, color="#3d7892")
    axes[0].set(title="图片宽高分布", xlabel="宽度（像素）", ylabel="高度（像素）")
    axes[1].hist(ratios, bins=40, color="#8d6e63", edgecolor="white")
    axes[1].set(title="宽高比分布", xlabel="宽 / 高", ylabel="图片数")
    fig.tight_layout()
    fig.savefig(output / "image_dimensions.png", dpi=160)
    plt.close(fig)


def make_grids(valid_rows: list[dict], classes: list[str], dataset: Path,
               output: Path, seed: int, sample_count: int, anomalies: list[dict]) -> None:
    plt = set_chinese_font()
    grid_dir = output / "sample_grids"
    grid_dir.mkdir(exist_ok=True)
    by_class = defaultdict(list)
    for row in valid_rows:
        by_class[row["class"]].append(row)
    rng = random.Random(seed)
    for class_name in classes:
        population = sorted(by_class[class_name], key=lambda r: r["path"])
        chosen = rng.sample(population, min(sample_count, len(population)))
        columns = 4
        lines = max(1, math.ceil(len(chosen) / columns))
        fig, axes = plt.subplots(lines, columns, figsize=(12, 2.65 * lines))
        for axis in np.asarray(axes).flat:
            axis.axis("off")
        for axis, row in zip(np.asarray(axes).flat, chosen):
            try:
                with Image.open(dataset / row["path"]) as image:
                    image = ImageOps.exif_transpose(image).convert("RGB")
                    image.thumbnail((420, 320))
                    axis.imshow(image)
                    axis.set_title(Path(row["path"]).name[:24], fontsize=8)
            except Exception as exc:
                add_anomaly(anomalies, row, "grid_read_error", f"{type(exc).__name__}: {exc}")
        fig.suptitle(f"{class_name}：固定种子随机样本（{len(chosen)} 张）")
        fig.tight_layout()
        fig.savefig(grid_dir / f"{class_name}.png", dpi=130)
        plt.close(fig)


def phash_near_hashes(by_hash: dict[int, list[dict]], radius: int, max_comparisons: int) -> tuple[list[tuple[int, int, int]], int, bool]:
    """Multi-index: radius+1 disjoint bands ensure recall within the radius."""
    bands = radius + 1
    widths = [64 // bands + (1 if i < 64 % bands else 0) for i in range(bands)]
    masks = []
    offset = 0
    for width in widths:
        masks.append((offset, (1 << width) - 1))
        offset += width
    buckets: dict[tuple[int, int], list[int]] = defaultdict(list)
    matches: list[tuple[int, int, int]] = []
    comparisons = 0
    completed = True
    for current in sorted(by_hash):
        possible: set[int] = set()
        keys = [(i, (current >> shift) & mask) for i, (shift, mask) in enumerate(masks)]
        for key in keys:
            possible.update(buckets[key])
        for prior in sorted(possible):
            if comparisons >= max_comparisons:
                completed = False
                break
            comparisons += 1
            distance = (prior ^ current).bit_count()
            if distance <= radius:
                matches.append((prior, current, distance))
        if not completed:
            break
        for key in keys:
            buckets[key].append(current)
    matches.extend((value, value, 0) for value, group in by_hash.items() if len(group) > 1)
    return sorted(matches, key=lambda item: (item[2], item[0], item[1])), comparisons, completed


def similar_pairs(by_hash: dict[int, list[dict]], matches: list[tuple[int, int, int]], cross_only: bool):
    for left_hash, right_hash, distance in matches:
        left, right = by_hash[left_hash], by_hash[right_hash]
        pairs = combinations(left, 2) if left_hash == right_hash else product(left, right)
        for a, b in pairs:
            cross = a["class"] != b["class"]
            if cross != cross_only or a["sha256"] == b["sha256"]:
                continue
            yield {"class_a": a["class"], "path_a": a["path"], "class_b": b["class"],
                   "path_b": b["path"], "hamming_distance": distance, "cross_class": cross}


def duplicate_analysis(rows: list[dict], output: Path, radius: int,
                       comparison_limit: int, pair_limit: int) -> dict:
    by_sha = defaultdict(list)
    by_hash = defaultdict(list)
    for row in rows:
        if row["sha256"]:
            by_sha[row["sha256"]].append(row)
        if row["valid"]:
            by_hash[int(row["phash"], 16)].append(row)

    exact_groups = []
    cross_exact_pairs = []
    cross_exact_complete = True
    exact_group_count = exact_file_count = cross_exact_group_count = 0
    for digest, group in sorted(by_sha.items()):
        if len(group) < 2:
            continue
        exact_group_count += 1
        exact_file_count += len(group)
        cross = len({r["class"] for r in group}) > 1
        cross_exact_group_count += int(cross)
        for row in group:
            exact_groups.append({"group_id": exact_group_count, "sha256": digest, "class": row["class"],
                                 "path": row["path"], "cross_class": cross, "group_size": len(group)})
        if cross:
            for a, b in combinations(group, 2):
                if a["class"] != b["class"]:
                    if len(cross_exact_pairs) >= pair_limit:
                        cross_exact_complete = False
                        break
                    cross_exact_pairs.append({"method": "SHA-256", "class_a": a["class"], "path_a": a["path"],
                                              "class_b": b["class"], "path_b": b["path"],
                                              "hamming_distance": "", "sha256": digest})
    write_csv(output / "exact_duplicate_groups.csv", exact_groups,
              ["group_id", "sha256", "class", "path", "cross_class", "group_size"])

    matches, comparisons, completed = phash_near_hashes(by_hash, radius, comparison_limit)
    near_count = cross_near_count = 0
    truncated = False
    cross_fields = ["method", "class_a", "path_a", "class_b", "path_b", "hamming_distance", "sha256"]
    near_fields = ["class_a", "path_a", "class_b", "path_b", "hamming_distance", "cross_class"]
    with (output / "phash_similar_pairs.csv").open("w", encoding="utf-8-sig", newline="") as near_file, \
         (output / "cross_class_candidates.csv").open("w", encoding="utf-8-sig", newline="") as cross_file:
        near_writer = csv.DictWriter(near_file, fieldnames=near_fields)
        cross_writer = csv.DictWriter(cross_file, fieldnames=cross_fields)
        near_writer.writeheader()
        cross_writer.writeheader()
        for row in cross_exact_pairs:
            cross_writer.writerow(row)
        # Cross-class pairs are written first so they are retained if the output cap is reached.
        for cross_only in (True, False):
            for row in similar_pairs(by_hash, matches, cross_only):
                if near_count >= pair_limit:
                    truncated = True
                    break
                near_writer.writerow(row)
                near_count += 1
                if cross_only:
                    cross_near_count += 1
                    cross_writer.writerow({"method": "pHash", **row, "sha256": ""})
            if truncated:
                break
    return {"exact_duplicate_groups": exact_group_count, "files_in_exact_groups": exact_file_count,
            "cross_class_exact_groups": cross_exact_group_count, "cross_class_exact_pairs": len(cross_exact_pairs),
            "cross_class_exact_pair_output_complete": cross_exact_complete,
            "phash_unique_values": len(by_hash), "phash_candidate_comparisons": comparisons,
            "phash_candidate_search_complete": completed, "phash_hash_pairs_within_threshold": len(matches),
            "phash_similar_pairs": near_count, "cross_class_phash_pairs": cross_near_count,
            "phash_pair_output_complete": not truncated}


def numeric_stats(values: list[float]) -> dict:
    if not values:
        return {}
    series = np.asarray(values, dtype=float)
    return {"min": float(series.min()), "median": float(np.median(series)),
            "p95": float(np.percentile(series, 95)), "max": float(series.max())}


def make_report(summary: dict, classes: list[dict], anomalies: list[dict], output: Path) -> None:
    lines = ["# 中药材图像数据集分析报告", "",
             f"- 数据集路径：`{summary['dataset_path']}`", f"- 类别数：**{summary['class_count']}**",
             f"- 文件总数：**{summary['file_count']}**；有效图片：**{summary['valid_image_count']}**；无效/未解码文件：**{summary['invalid_file_count']}**",
             f"- 随机抽样种子：`{summary['sample_seed']}`；每类最多 `{summary['samples_per_class']}` 张",
             "", "## 类别分布", "", "| 类别 | 文件数 | 有效图片 |", "|---|---:|---:|"]
    lines += [f"| {row['class']} | {row['file_count']} | {row['valid_image_count']} |" for row in classes]
    balance = summary["class_balance"]
    ratio_text = f"{balance['max_min_ratio']:.2f}" if balance["max_min_ratio"] is not None else "不可计算（存在空类别）"
    cv_text = f"{balance['coefficient_of_variation']:.3f}" if balance["coefficient_of_variation"] is not None else "不可计算"
    lines += ["", f"有效图片最多/最少类别数量比：**{ratio_text}**；变异系数：**{cv_text}**。",
              "", "![类别数量柱状图](class_counts.png)", "", "## 图像属性", "",
              f"- 文件扩展名：`{summary['extension_counts']}`",
              f"- Pillow 实际格式：`{summary['format_counts']}`",
              f"- 颜色模式：`{summary['mode_counts']}`",
              f"- 扩展名/实际格式组合：`{summary['extension_content_counts']}`",
              f"- 宽度（像素）统计：`{summary['width_pixels']}`",
              f"- 高度（像素）统计：`{summary['height_pixels']}`",
              f"- 宽高比统计：`{summary['aspect_ratio']}`",
              f"- 文件大小（字节）统计：`{summary['file_size_bytes']}`",
              "", "![图片尺寸统计图](image_dimensions.png)", "", "## 异常与重复候选", "",
              f"- 异常记录 **{len(anomalies)}** 条（同一文件可有多条）：`{summary['anomaly_counts']}`。",
              f"- SHA-256 完全重复组 **{summary['exact_duplicate_groups']}** 组，涉及 **{summary['files_in_exact_groups']}** 个文件；其中跨类别 **{summary['cross_class_exact_groups']}** 组。",
              f"- pHash 阈值：汉明距离 ≤ **{summary['phash_threshold']}**；独立哈希值 **{summary['phash_unique_values']}** 个；候选哈希比较 **{summary['phash_candidate_comparisons']}** 次。",
              f"- 不同 SHA-256 的 pHash 相似图片对 **{summary['phash_similar_pairs']}** 对，其中跨类别 **{summary['cross_class_phash_pairs']}** 对。",
              f"- 候选筛选完成：**{summary['phash_candidate_search_complete']}**；pHash 相似对导出完整：**{summary['phash_pair_output_complete']}**；跨类别完全重复对导出完整：**{summary['cross_class_exact_pair_output_complete']}**。",
              "", "pHash 仅提示视觉相似，不能单独证明重复或标签错误；图像网格与跨类别候选需要人工核对。",
              "训练、验证和测试集划分前，应先处理已核实的重复组，避免相同或近似图片分布到不同子集造成数据泄漏。",
              "", "## 数据质量风险及人工审核", ""]
    lines += ["", "固定种子抽样网格中，九层塔可见带文字/水印的图片及鲜株、叶片、菜品等不同呈现方式；灵芝可见野生、干品和盆景等差异。",
              "这些观察仅来自抽样，应人工核对标签定义与目标应用场景，并留意模型利用背景或文字而非药材外观进行分类的风险。"]
    if anomalies:
        lines += ["| 类别 | 文件 | 问题 | 说明 |", "|---|---|---|---|"]
        by_issue = defaultdict(list)
        for item in anomalies:
            by_issue[item["issue"]].append(item)
        for issue in sorted(by_issue):
            limit = 3 if len(by_issue[issue]) > 10 else len(by_issue[issue])
            for item in by_issue[issue][:limit]:
                detail = item["detail"].replace("|", "/").replace("\n", " ")[:100]
                lines.append(f"| {item['class']} | `{item['path']}` | {item['issue']} | {detail} |")
        lines.append("\n记录超过 10 条的问题仅展示前 3 条；完整记录见 [异常清单](anomalies.csv)。")
    else:
        lines.append("本次扫描未发现按上述规则判定的异常文件；仍须人工检查抽样网格及相似图片候选。")
    cross_count = summary["cross_class_exact_pairs"] + summary["cross_class_phash_pairs"]
    cross_advice = ("人工复核 `cross_class_candidates.csv`，确认重复采集或标签冲突，记录裁决依据。" if cross_count
                    else "当前跨类别候选为空；仍需抽检标签，新增数据后重新检查跨类别重复。")
    lines += ["", "## 下一阶段清洗建议", "",
              f"1. {cross_advice}",
              "2. 复核低分辨率和极端宽高比文件；对大量扩展名与编码不符的图片，在派生数据目录中统一编码和文件名，不改动原件。",
              "3. 人工核对同类 SHA-256 重复组及 pHash 候选，为确认的重复/近重复样本建立分组；后续按组划分数据集，防止泄漏。",
              "4. 结合类别数量和抽样网格核对标签定义、拍摄背景、文字水印与类别偏差，再决定训练阶段的平衡策略。",
              "", "## 产物索引", "",
              "- [逐文件清单](images.csv) · [类别统计](class_summary.csv) · [异常清单](anomalies.csv) · [完全重复组](exact_duplicate_groups.csv)",
              "- [pHash 相似对](phash_similar_pairs.csv) · [跨类别候选](cross_class_candidates.csv) · [机器可读摘要](summary.json)",
              "- [每类抽样网格](sample_grids/) · [类别数量图](class_counts.png) · [图片尺寸图](image_dimensions.png)", ""]
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = arguments()
    dataset = args.dataset.expanduser().resolve()
    output = args.output.expanduser().resolve()
    if not dataset.is_dir():
        print(f"Dataset directory does not exist: {dataset}", file=sys.stderr)
        return 2
    if output == dataset or dataset in output.parents:
        print("Output must be outside the dataset directory to preserve read-only input.", file=sys.stderr)
        return 2
    class_dirs = sorted((item for item in dataset.iterdir() if item.is_dir()), key=lambda p: p.name)
    if not class_dirs:
        print("No class subdirectories found.", file=sys.stderr)
        return 2
    files = sorted((path for path in dataset.rglob("*") if path.is_file()), key=lambda p: p.relative_to(dataset).as_posix())
    output.mkdir(parents=True, exist_ok=True)
    anomalies: list[dict] = []
    rows = []
    for index, path in enumerate(files, 1):
        relative = path.relative_to(dataset)
        class_name = relative.parts[0] if len(relative.parts) > 1 else "[unclassified]"
        row = inspect_file(path, dataset, class_name, anomalies)
        if class_name == "[unclassified]":
            add_anomaly(anomalies, row, "unclassified_root_file")
        rows.append(row)
        if index % 500 == 0 or index == len(files):
            print(f"Inspected {index}/{len(files)} files", flush=True)
    valid_rows = [row for row in rows if row["valid"]]
    names = [path.name for path in class_dirs]
    class_rows = [{"class": name, "file_count": sum(r["class"] == name for r in rows),
                   "valid_image_count": sum(r["class"] == name for r in valid_rows)} for name in names]
    counts = [row["valid_image_count"] for row in class_rows]
    duplicate_stats = duplicate_analysis(rows, output, args.phash_threshold,
                                         args.max_candidate_comparisons, args.max_similar_pairs)
    make_charts(valid_rows, names, output)
    make_grids(valid_rows, names, dataset, output, args.seed, args.samples_per_class, anomalies)
    summary = {"dataset_path": str(dataset), "class_count": len(names), "file_count": len(rows),
               "valid_image_count": len(valid_rows), "invalid_file_count": len(rows) - len(valid_rows),
               "classes": class_rows, "extension_counts": dict(sorted(Counter(r["extension"] for r in rows).items())),
               "format_counts": dict(sorted(Counter(r["format"] for r in valid_rows).items())),
               "mode_counts": dict(sorted(Counter(r["mode"] for r in valid_rows).items())),
               "extension_content_counts": dict(sorted(Counter(f"{r['extension']} → {r['format']}" for r in valid_rows).items())),
               "anomaly_counts": dict(sorted(Counter(a["issue"] for a in anomalies).items())),
               "width_pixels": numeric_stats([r["width"] for r in valid_rows]),
               "height_pixels": numeric_stats([r["height"] for r in valid_rows]),
               "aspect_ratio": numeric_stats([r["aspect_ratio"] for r in valid_rows]),
               "file_size_bytes": numeric_stats([r["file_size_bytes"] for r in valid_rows]),
               "class_balance": {"min": min(counts), "max": max(counts),
                                 "max_min_ratio": max(counts) / min(counts) if min(counts) else None,
                                 "coefficient_of_variation": statistics.pstdev(counts) / statistics.mean(counts) if statistics.mean(counts) else None},
               "sample_seed": args.seed, "samples_per_class": args.samples_per_class,
               "phash_threshold": args.phash_threshold, **duplicate_stats}
    image_fields = ["class", "path", "extension", "format", "valid", "width", "height", "aspect_ratio",
                    "mode", "file_size_bytes", "sha256", "phash", "flags"]
    write_csv(output / "images.csv", [{**row, "flags": ";".join(row["flags"])} for row in rows], image_fields)
    write_csv(output / "class_summary.csv", class_rows, ["class", "file_count", "valid_image_count"])
    write_csv(output / "anomalies.csv", anomalies, ["class", "path", "issue", "detail"])
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    make_report(summary, class_rows, anomalies, output)
    print(f"Report: {output / 'report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
