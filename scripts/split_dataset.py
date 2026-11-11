"""Deterministic, class-stratified train/val/test split with confirmed-source isolation."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import math
import random
from collections import Counter, defaultdict
from pathlib import Path

from herb_classifier.data import get_preprocess_config


SPLITS = ("train", "val", "test")
RATIOS = (0.70, 0.15, 0.15)
FONT_FILES = (Path("C:/Windows/Fonts/msyh.ttc"), Path("C:/Windows/Fonts/simhei.ttf"))


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True, help="Original read-only image directory")
    parser.add_argument("--manifest", type=Path, default=Path("reports/data_cleaning/reviewed_clean_manifest.csv"))
    parser.add_argument("--excluded", type=Path, default=Path("reports/data_cleaning/reviewed_excluded_images.csv"))
    parser.add_argument("--groups", type=Path, default=Path("reports/data_cleaning/confirmed_source_groups.csv"))
    parser.add_argument("--output", type=Path, default=Path("reports/data_split"))
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def read_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def integer_targets(total: int) -> dict[str, int]:
    exact = [total * ratio for ratio in RATIOS]
    counts = [math.floor(value) for value in exact]
    leftovers = total - sum(counts)
    order = sorted(range(3), key=lambda index: (-(exact[index] - counts[index]), index))
    for index in order[:leftovers]:
        counts[index] += 1
    return dict(zip(SPLITS, counts))


def validated_units(manifest: list[dict], groups: list[dict]) -> tuple[dict[str, list[dict]], dict]:
    by_path = {row["path"]: row for row in manifest}
    if len(by_path) != len(manifest):
        raise ValueError("Duplicate paths in reviewed clean manifest")
    declared: dict[str, str] = {}
    kept_group_sizes = Counter()
    for group in groups:
        group_id = group["group_id"]
        members = json.loads(group["member_paths_json"])
        kept = [path for path in members if path in by_path]
        if len(kept) != int(group["kept_count"]):
            raise ValueError(f"Kept count mismatch in confirmed source group {group_id}")
        if any(by_path[path]["class"] != group["class"] for path in kept):
            raise ValueError(f"Cross-class source group {group_id}")
        for path in kept:
            if path in declared:
                raise ValueError(f"Image belongs to multiple confirmed groups: {path}")
            declared[path] = group_id
        kept_group_sizes[len(kept)] += 1
    units: dict[str, list[dict]] = defaultdict(list)
    independent_shas = set()
    for row in manifest:
        path = row["path"]
        declared_id = declared.get(path, "")
        if row["confirmed_source_group_id"] != declared_id:
            raise ValueError(f"Confirmed group mismatch for {path}")
        if declared_id:
            unit_id = declared_id
        else:
            if row["sha256"] in independent_shas:
                raise ValueError(f"Repeated SHA-256 among independent samples: {path}")
            independent_shas.add(row["sha256"])
            unit_id = "I:" + row["sha256"]
        units[unit_id].append(row)
    if any(len({row["class"] for row in unit}) != 1 for unit in units.values()):
        raise ValueError("A split unit crosses class labels")
    return units, {"confirmed_group_kept_size_histogram": dict(sorted(kept_group_sizes.items())),
                   "independent_group_count": len(independent_shas),
                   "split_unit_size_histogram": dict(sorted(Counter(len(unit) for unit in units.values()).items())),
                   "max_kept_group_size": max((len(unit) for unit in units.values()), default=0),
                   "split_unit_count": len(units)}


def choose_weighted(rng: random.Random, options: list[str], weights: list[int]) -> str:
    return rng.choices(options, weights=weights, k=1)[0]


def assign_class(units: list[tuple[str, list[dict]]], targets: dict[str, int],
                 rng: random.Random) -> tuple[dict[str, list[dict]], dict[str, int]]:
    assigned = {name: [] for name in SPLITS}
    counts = {name: 0 for name in SPLITS}
    multi = [(key, rows) for key, rows in units if len(rows) > 1]
    singles = [(key, rows) for key, rows in units if len(rows) == 1]
    rng.shuffle(multi)
    multi.sort(key=lambda item: -len(item[1]))  # Stable shuffle breaks equal-size ties.
    for _, rows in multi:
        size = len(rows)
        feasible = [name for name in SPLITS if targets[name] - counts[name] >= size]
        if feasible:
            weights = [targets[name] - counts[name] for name in feasible]
            choice = choose_weighted(rng, feasible, weights)
        else:
            # Keep the group whole even when a target cannot fit it.
            choice = min(SPLITS, key=lambda name: (max(0, counts[name] + size - targets[name]),
                                                   abs(counts[name] + size - targets[name]), SPLITS.index(name)))
        assigned[choice].extend(rows)
        counts[choice] += size
    rng.shuffle(singles)
    for _, rows in singles:
        feasible = [name for name in SPLITS if targets[name] > counts[name]]
        if feasible:
            weights = [targets[name] - counts[name] for name in feasible]
            choice = choose_weighted(rng, feasible, weights)
        else:
            choice = min(SPLITS, key=lambda name: (counts[name] - targets[name], SPLITS.index(name)))
        assigned[choice].extend(rows)
        counts[choice] += 1
    return assigned, counts


def verify_splits(dataset: Path, manifest_path: Path, excluded_path: Path,
                  groups_path: Path, split_dir: Path) -> dict:
    """Read all generated CSVs afresh and fail on any data isolation violation."""
    manifest = read_csv(manifest_path)
    excluded = read_csv(excluded_path)
    groups = read_csv(groups_path)
    mapping = json.loads((split_dir / "class_to_idx.json").read_text(encoding="utf-8"))
    class_names = set(mapping)
    expected = {row["path"]: row for row in manifest}
    if len(expected) != len(manifest) or set(mapping.values()) != set(range(len(mapping))):
        raise ValueError("Manifest paths or class mapping are not unique/contiguous")
    split_rows = {name: read_csv(split_dir / f"{name}.csv") for name in SPLITS}
    all_rows = [row for name in SPLITS for row in split_rows[name]]
    paths = [row["path"] for row in all_rows]
    if len(paths) != len(set(paths)):
        raise ValueError("A file path occurs more than once in the split CSVs")
    if set(paths) != set(expected):
        missing, extra = set(expected) - set(paths), set(paths) - set(expected)
        raise ValueError(f"Split coverage mismatch: missing={len(missing)}, extra={len(extra)}")
    excluded_paths = {row["path"] for row in excluded}
    if excluded_paths & set(paths):
        raise ValueError("An excluded image appears in a split")
    if len(class_names) != 18 or set(row["class"] for row in manifest) != class_names:
        raise ValueError("Expected exactly 18 manifest classes")
    path_to_split = {row["path"]: name for name in SPLITS for row in split_rows[name]}
    unit_to_splits: dict[str, set[str]] = defaultdict(set)
    for row in all_rows:
        source = expected[row["path"]]
        if row["class"] != source["class"] or int(row["class_idx"]) != mapping[row["class"]]:
            raise ValueError(f"Class mapping mismatch: {row['path']}")
        expected_unit = source["confirmed_source_group_id"] or "I:" + source["sha256"]
        if row["source_group_id"] != expected_unit or row["sha256"] != source["sha256"]:
            raise ValueError(f"Group or SHA-256 mismatch: {row['path']}")
        unit_to_splits[expected_unit].add(path_to_split[row["path"]])
        image_path = (dataset / Path(row["path"])).resolve()
        if dataset not in image_path.parents or not image_path.is_file():
            raise ValueError(f"Image missing or outside dataset: {row['path']}")
    if any(len(splits) != 1 for splits in unit_to_splits.values()):
        raise ValueError("A source group crosses train/val/test")
    for group in groups:
        members = json.loads(group["member_paths_json"])
        kept_members = [path for path in members if path in expected]
        if len(kept_members) != int(group["kept_count"]):
            raise ValueError(f"Confirmed source group member count mismatch: {group['group_id']}")
        if any(expected[path]["confirmed_source_group_id"] != group["group_id"] for path in kept_members):
            raise ValueError(f"Confirmed source group ID mismatch: {group['group_id']}")
        kept_splits = {path_to_split[path] for path in kept_members}
        if len(kept_splits) > 1 or len(kept_splits) != (1 if int(group["kept_count"]) else 0):
            raise ValueError(f"Confirmed source group crosses splits or has missing members: {group['group_id']}")
    if len({row["sha256"] for row in all_rows}) != len(all_rows):
        raise ValueError("Identical SHA-256 files remain among selected samples")
    class_stats = {}
    for name in sorted(class_names):
        counts = {part: sum(row["class"] == name for row in split_rows[part]) for part in SPLITS}
        if any(value == 0 for value in counts.values()):
            raise ValueError(f"Class absent from a split: {name}")
        class_stats[name] = {"total": sum(counts.values()), **counts}
    counts = {part: len(split_rows[part]) for part in SPLITS}
    total = sum(counts.values())
    return {"passed": True, "checks": {
        "paths_unique_across_splits": True, "complete_manifest_coverage": True,
        "all_18_classes_in_each_split": True, "confirmed_source_groups_isolated": True,
        "excluded_images_absent": True, "sha256_unique": True, "source_paths_exist": True},
        "counts": counts, "total": total,
        "actual_ratios": {part: counts[part] / total for part in SPLITS},
        "class_distribution": class_stats,
        "source_group_count": len(unit_to_splits),
        "confirmed_group_count": len(groups),
        "excluded_count": len(excluded)}


def plot_distribution(class_stats: dict, output: Path) -> None:
    logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager

    for font_path in FONT_FILES:
        if font_path.exists():
            font_manager.fontManager.addfont(str(font_path))
            plt.rcParams["font.family"] = font_manager.FontProperties(fname=str(font_path)).get_name()
            break
    plt.rcParams["axes.unicode_minus"] = False
    names = list(class_stats)
    train = [class_stats[name]["train"] for name in names]
    val = [class_stats[name]["val"] for name in names]
    test = [class_stats[name]["test"] for name in names]
    fig, axis = plt.subplots(figsize=(13, 6))
    indexes = range(len(names))
    axis.bar(indexes, train, label="训练集", color="#397b86")
    axis.bar(indexes, val, bottom=train, label="验证集", color="#d39b52")
    axis.bar(indexes, test, bottom=[a + b for a, b in zip(train, val)], label="测试集", color="#76965a")
    axis.set_xticks(list(indexes), labels=names, rotation=55, ha="right")
    axis.set(title="18类中药材分层与同源分组划分", xlabel="类别", ylabel="图片数量")
    axis.legend()
    fig.tight_layout()
    fig.savefig(output / "class_split_counts.png", dpi=160)
    plt.close(fig)


def main() -> int:
    args = arguments()
    dataset, manifest_path, excluded_path, groups_path, output = (
        path.expanduser().resolve() for path in
        (args.dataset, args.manifest, args.excluded, args.groups, args.output))
    if not dataset.is_dir():
        raise SystemExit(f"Dataset directory not found: {dataset}")
    if output == dataset or dataset in output.parents:
        raise SystemExit("Output must be outside the read-only source dataset")
    for path in (manifest_path, excluded_path, groups_path):
        if not path.is_file():
            raise SystemExit(f"Required cleaning artifact missing: {path}")
    manifest = read_csv(manifest_path)
    excluded = read_csv(excluded_path)
    groups = read_csv(groups_path)
    if {row["path"] for row in manifest} & {row["path"] for row in excluded}:
        raise SystemExit("Reviewed manifest overlaps the excluded image list")
    classes = sorted({row["class"] for row in manifest})
    if len(classes) != 18:
        raise SystemExit(f"Expected 18 classes, got {len(classes)}")
    class_to_idx = {name: index for index, name in enumerate(classes)}
    units, group_stats = validated_units(manifest, groups)
    class_totals = Counter(row["class"] for row in manifest)
    anomalies = []
    for group_id, rows in units.items():
        class_name = rows[0]["class"]
        threshold = max(10, math.ceil(0.05 * class_totals[class_name]))
        if len(rows) > threshold:
            anomalies.append({"group_id": group_id, "class": class_name,
                              "size": len(rows), "threshold": threshold})
    rng = random.Random(args.seed)
    split_rows = {name: [] for name in SPLITS}
    class_targets = {}
    for class_name in classes:
        class_units = [(key, rows) for key, rows in sorted(units.items()) if rows[0]["class"] == class_name]
        targets = integer_targets(class_totals[class_name])
        class_targets[class_name] = targets
        assigned, _ = assign_class(class_units, targets, rng)
        for part in SPLITS:
            for row in assigned[part]:
                split_rows[part].append({"class": row["class"], "class_idx": class_to_idx[row["class"]],
                                         "path": row["path"], "sha256": row["sha256"],
                                         "source_group_id": row["confirmed_source_group_id"] or "I:" + row["sha256"]})
    output.mkdir(parents=True, exist_ok=True)
    fields = ["class", "class_idx", "path", "sha256", "source_group_id"]
    for part in SPLITS:
        split_rows[part].sort(key=lambda row: row["path"])
        write_csv(output / f"{part}.csv", split_rows[part], fields)
    (output / "class_to_idx.json").write_text(json.dumps(class_to_idx, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "preprocess_config.json").write_text(json.dumps(get_preprocess_config(), ensure_ascii=False, indent=2), encoding="utf-8")
    config = {"seed": args.seed, "requested_ratios": dict(zip(SPLITS, RATIOS)),
              "dataset_path": str(dataset), "manifest_path": str(manifest_path),
              "excluded_path": str(excluded_path), "groups_path": str(groups_path),
              "input_sha256": {"manifest": sha256(manifest_path), "excluded": sha256(excluded_path),
                               "groups": sha256(groups_path)},
              "class_targets": class_targets, "group_statistics": group_stats,
              "oversized_groups": anomalies}
    (output / "split_config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    result = verify_splits(dataset, manifest_path, excluded_path, groups_path, output)
    (output / "validation_results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    plot_distribution(result["class_distribution"], output)
    lines = ["# 数据集划分与验证报告", "",
             f"- 输入：复核后有效样本 **{result['total']}** 张，18 类；随机种子 **{args.seed}**。",
             "- 方法：先将人工确认同源的有效图片组成不可拆分单元，其余图片各成独立单元；再逐类别按 70/15/15 目标分配完整单元。",
             "- 预处理：ConvNeXt-Tiny ImageNet-1K V1 权重对应的 RGB、224×224 和 ImageNet 均值/标准差；具体参数见 [预处理配置](preprocess_config.json)。",
             "", "## 实际划分", "",
             "| 子集 | 数量 | 实际比例 | 目标比例 |", "|---|---:|---:|---:|"]
    for part in SPLITS:
        lines.append(f"| {part} | {result['counts'][part]} | {result['actual_ratios'][part]:.2%} | {dict(zip(SPLITS, RATIOS))[part]:.0%} |")
    lines += ["", "| 类别 | 总数 | 训练 | 验证 | 测试 |", "|---|---:|---:|---:|---:|"]
    for name, counts in result["class_distribution"].items():
        lines.append(f"| {name} | {counts['total']} | {counts['train']} | {counts['val']} | {counts['test']} |")
    lines += ["", "![各类别划分数量](class_split_counts.png)", "", "## 同源组与验证", "",
              f"- 确认同源组：**{len(groups)}** 组；有效图片最大组：**{group_stats['max_kept_group_size']}** 张；独立分组：**{group_stats['independent_group_count']}** 个。",
              f"- 确认同源组保留后大小分布（含 0 张组）：`{group_stats['confirmed_group_kept_size_histogram']}`。",
              f"- 所有划分单元大小分布：`{group_stats['split_unit_size_histogram']}`。",
              f"- 异常大关系组：**{len(anomalies)}** 组（阈值为 max(10, 该类别样本数的 5%)）。",
              "- 验证通过：路径互斥、完整覆盖、每个子集均含 18 类、确认同源组不跨子集、排除图片未进入、SHA-256 唯一、源图片路径存在。",
              "- 若未来数据出现无法精确满足目标比例的大组，脚本会保留组完整并记录实际比例，不拆分同源组。",
              "", "## 产物", "",
              "- [训练集](train.csv) · [验证集](val.csv) · [测试集](test.csv) · [类别映射](class_to_idx.json)",
              "- [划分配置](split_config.json) · [独立验证结果](validation_results.json) · [统计图](class_split_counts.png)", ""]
    (output / "split_report.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"train={result['counts']['train']} val={result['counts']['val']} test={result['counts']['test']}")
    print(f"Validation passed; report: {output / 'split_report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
