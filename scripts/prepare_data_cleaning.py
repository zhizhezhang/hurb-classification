"""Prepare a conservative cleaning manifest and offline review UI from task-01 CSVs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote


ATTENTION_SAMPLES = {
    "九层塔/九层塔 (11).png": "抽样网格：画面含较多文字与促销标识",
    "九层塔/九层塔 (193).png": "抽样网格：画面含类别文字与水印",
    "九层塔/九层塔 (212).png": "抽样网格：菜品画面，与鲜株照片呈现方式不同",
    "灵芝/03 (666).jpg": "抽样网格：盆景/陈列照片，需核对目标场景",
}
REVIEW_ISSUES = {"decode_error", "empty_file", "small_dimension", "extreme_aspect_ratio",
                 "unusual_color_mode", "large_file", "grid_read_error"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, type=Path, help="Original class-per-folder dataset")
    parser.add_argument("--audit", type=Path, default=Path("reports/data_audit"), help="Task-01 audit output")
    parser.add_argument("--output", type=Path, default=Path("reports/data_cleaning"))
    return parser.parse_args()


def read_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def browser_image_url(source: Path, output: Path) -> str:
    try:
        relative = os.path.relpath(source, output).replace("\\", "/")
        return quote(relative, safe="/.")
    except ValueError:  # Different Windows drives.
        return source.as_uri()


def normalize_pair(a: str, b: str) -> tuple[str, str]:
    return tuple(sorted((a, b)))


def connected_groups(edges: list[tuple[str, str]]) -> list[list[str]]:
    parent: dict[str, str] = {}

    def find(value: str) -> str:
        parent.setdefault(value, value)
        if parent[value] != value:
            parent[value] = find(parent[value])
        return parent[value]

    for a, b in edges:
        parent[find(a)] = find(b)
    components: dict[str, list[str]] = defaultdict(list)
    for value in parent:
        components[find(value)].append(value)
    return sorted((sorted(members) for members in components.values()), key=lambda group: group[0])


def main() -> int:
    args = parse_args()
    dataset, audit, output = (p.expanduser().resolve() for p in (args.dataset, args.audit, args.output))
    if not dataset.is_dir():
        raise SystemExit(f"Dataset directory not found: {dataset}")
    if output == dataset or dataset in output.parents:
        raise SystemExit("Output must be outside the original dataset directory")
    audit_files = ["images.csv", "exact_duplicate_groups.csv", "phash_similar_pairs.csv", "anomalies.csv", "summary.json"]
    missing = [name for name in audit_files if not (audit / name).is_file()]
    if missing:
        raise SystemExit(f"Missing task-01 audit files: {', '.join(missing)}")
    image_rows = read_csv(audit / "images.csv")
    exact_rows = read_csv(audit / "exact_duplicate_groups.csv")
    near_rows = read_csv(audit / "phash_similar_pairs.csv")
    anomaly_rows = read_csv(audit / "anomalies.csv")
    summary = json.loads((audit / "summary.json").read_text(encoding="utf-8"))
    if len(image_rows) != summary["file_count"] or len(near_rows) != summary["phash_similar_pairs"]:
        raise SystemExit("Task-01 CSV and summary counts disagree; rerun or repair the audit first")
    by_path = {row["path"]: row for row in image_rows}
    if len(by_path) != len(image_rows):
        raise SystemExit("Duplicate relative paths in images.csv")
    absent = [path for path in by_path if not (dataset / Path(path)).is_file()]
    if absent:
        raise SystemExit(f"Audit references missing original files (first example): {absent[0]}")
    # Exact duplicate groups come from task 01. Cross-class equality needs label review.
    exact_groups: dict[str, list[str]] = defaultdict(list)
    for row in exact_rows:
        exact_groups[row["group_id"]].append(row["path"])
    representative: dict[str, str] = {path: path for path in by_path}
    exact_group_for: dict[str, str] = {}
    duplicate_group_rows: list[dict] = []
    for source_id in sorted(exact_groups, key=int):
        members = sorted(exact_groups[source_id])
        if len(members) < 2 or any(path not in by_path for path in members):
            raise SystemExit(f"Invalid exact duplicate group: {source_id}")
        digests = {by_path[path]["sha256"] for path in members}
        if len(digests) != 1 or "" in digests:
            raise SystemExit(f"SHA-256 mismatch in exact group: {source_id}")
        if len({by_path[path]["class"] for path in members}) > 1:
            raise SystemExit(f"Cross-class exact group {source_id} requires manual label resolution")
        group_id = f"E{int(source_id):04d}"
        rep = members[0]
        for path in members:
            representative[path] = rep
            exact_group_for[path] = group_id
        duplicate_group_rows.append({"group_id": group_id, "method": "SHA-256", "status": "confirmed_exact",
                                     "member_count": len(members), "pair_count": len(members) * (len(members) - 1) // 2,
                                     "representative_path": rep, "member_paths_json": json.dumps(members, ensure_ascii=False),
                                     "note": "Identical file bytes; non-representatives excluded from clean manifest"})

    manifest, excluded, processing = [], [], []
    for row in image_rows:
        path = row["path"]
        rep = representative[path]
        valid = row["valid"].lower() == "true"
        action = "keep" if valid and path == rep else "exclude"
        reason = "" if action == "keep" else ("audit_invalid" if not valid else "sha256_exact_duplicate")
        base = {"class": row["class"], "path": path, "representative_path": rep,
                "sha256": row["sha256"], "phash": row["phash"],
                "exact_group_id": exact_group_for.get(path, ""), "action": action, "reason": reason}
        processing.append(base)
        if action == "keep":
            manifest.append({"class": row["class"], "path": path, "sha256": row["sha256"],
                             "phash": row["phash"], "width": row["width"], "height": row["height"],
                             "format": row["format"], "flags": row["flags"],
                             "confirmed_exact_group_id": exact_group_for.get(path, ""),
                             "manual_review_status": "pending" if any(code in row["flags"] for code in REVIEW_ISSUES) else "not_required"})
        else:
            excluded.append(base)

    # Normalize the 366 pHash pairs through exact-file representatives; retain a row
    # for every source pair so no audit evidence disappears during consolidation.
    normalized: dict[tuple[str, str], dict] = {}
    pair_mapping: list[dict] = []
    for index, row in enumerate(near_rows, 1):
        a, b = representative[row["path_a"]], representative[row["path_b"]]
        if a == b:
            pair_mapping.append({"audit_pair_index": index, "path_a": row["path_a"], "path_b": row["path_b"],
                                 "representative_a": a, "representative_b": b,
                                 "distance": row["hamming_distance"], "action": "covered_by_exact_group", "review_pair_id": ""})
            continue
        key = normalize_pair(a, b)
        record = normalized.setdefault(key, {"distance": int(row["hamming_distance"]), "source_indices": []})
        record["distance"] = min(record["distance"], int(row["hamming_distance"]))
        record["source_indices"].append(index)
        pair_mapping.append({"audit_pair_index": index, "path_a": row["path_a"], "path_b": row["path_b"],
                             "representative_a": key[0], "representative_b": key[1],
                             "distance": row["hamming_distance"], "action": "needs_pair_review", "review_pair_id": ""})

    components = connected_groups(list(normalized))
    group_for = {member: f"P{number:04d}" for number, members in enumerate(components, 1) for member in members}
    grouped_pairs: dict[str, list[dict]] = defaultdict(list)
    pairs = []
    pair_id_for = {}
    for key in sorted(normalized, key=lambda k: (group_for[k[0]], normalized[k]["distance"], k)):
        group_id = group_for[key[0]]
        pair_id = f"{group_id}-{len(grouped_pairs[group_id]) + 1:03d}"
        record = normalized[key]
        pair = {"id": pair_id, "group_id": group_id, "path_a": key[0], "path_b": key[1],
                "distance": record["distance"], "audit_pair_indices": record["source_indices"],
                "status": "pending"}
        pairs.append(pair)
        grouped_pairs[group_id].append(pair)
        pair_id_for[key] = pair_id
    for row in pair_mapping:
        if row["action"] == "needs_pair_review":
            row["review_pair_id"] = pair_id_for[normalize_pair(row["representative_a"], row["representative_b"])]
    groups = []
    for number, members in enumerate(components, 1):
        group_id = f"P{number:04d}"
        group_pairs = grouped_pairs[group_id]
        groups.append({"id": group_id, "member_paths": members, "pair_ids": [item["id"] for item in group_pairs]})
        duplicate_group_rows.append({"group_id": group_id, "method": "pHash", "status": "needs_pair_review",
                                     "member_count": len(members), "pair_count": len(group_pairs),
                                     "representative_path": "", "member_paths_json": json.dumps(members, ensure_ascii=False),
                                     "note": "Graph component only; members are not automatically a single duplicate set"})

    focus_reasons: dict[str, set[str]] = defaultdict(set)
    for row in anomaly_rows:
        if row["issue"] in REVIEW_ISSUES and row["path"] in representative:
            focus_reasons[representative[row["path"]]].add(f"审计异常：{row['issue']} ({row['detail']})")
    for path, reason in ATTENTION_SAMPLES.items():
        if path in representative:
            focus_reasons[representative[path]].add(reason)
    focus = [{"id": f"F{index:03d}", "path": path, "reasons": sorted(reasons), "status": "pending"}
             for index, (path, reasons) in enumerate(sorted(focus_reasons.items()), 1)]

    involved = {path for pair in pairs for path in (pair["path_a"], pair["path_b"])} | set(focus_reasons)
    for row in manifest:
        if row["path"] in involved:
            row["manual_review_status"] = "pending"
    images = {path: {"class": by_path[path]["class"], "name": Path(path).name,
                     "url": browser_image_url(dataset / Path(path), output), "width": by_path[path]["width"],
                     "height": by_path[path]["height"], "flags": by_path[path]["flags"]}
              for path in sorted(involved)}
    payload = {"schema_version": 1, "dataset_path": str(dataset), "audit_path": str(audit),
               "groups": groups, "pairs": pairs, "focus": focus, "images": images}
    output.mkdir(parents=True, exist_ok=True)
    manifest_fields = ["class", "path", "sha256", "phash", "width", "height", "format", "flags",
                       "confirmed_exact_group_id", "manual_review_status"]
    action_fields = ["class", "path", "representative_path", "sha256", "phash", "exact_group_id", "action", "reason"]
    write_csv(output / "clean_manifest.csv", manifest, manifest_fields)
    write_csv(output / "excluded_images.csv", excluded, action_fields)
    write_csv(output / "processing_log.csv", processing, action_fields)
    write_csv(output / "duplicate_groups.csv", duplicate_group_rows,
              ["group_id", "method", "status", "member_count", "pair_count", "representative_path", "member_paths_json", "note"])
    write_csv(output / "phash_pair_mapping.csv", pair_mapping,
              ["audit_pair_index", "path_a", "path_b", "representative_a", "representative_b", "distance", "action", "review_pair_id"])
    write_csv(output / "focus_review.csv",
              [{"id": item["id"], "path": item["path"], "class": by_path[item["path"]]["class"],
                "reasons": "; ".join(item["reasons"]), "status": item["status"]} for item in focus],
              ["id", "path", "class", "reasons", "status"])
    (output / "review_cases.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    template = (Path(__file__).with_name("review_template.html")).read_text(encoding="utf-8")
    embedded = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")
    (output / "review.html").write_text(template.replace("__REVIEW_DATA__", embedded), encoding="utf-8")
    stats = {"audit_file_count": len(image_rows), "audit_phash_pairs": len(near_rows),
             "exact_groups": len(exact_groups), "auto_excluded_files": len(excluded),
             "clean_manifest_files": len(manifest), "phash_pairs_after_exact_normalization": len(pairs),
             "phash_pairs_covered_by_exact_groups": sum(row["action"] == "covered_by_exact_group" for row in pair_mapping),
             "phash_review_groups": len(groups), "focus_review_images": len(focus),
             "unique_manual_review_images": len(involved),
             "auto_excluded_phash_files": 0,
             "source_audit_sha256": {name: file_sha256(audit / name) for name in audit_files},
             "original_dataset_modified": False}
    (output / "processing_summary.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    report = ["# 数据清洗与人工复核准备", "",
              f"- 输入：任务 01 审计文件 `{audit}`；原始数据集 `{dataset}`。",
              f"- 有效样本清单：**{len(manifest)}** 张；自动排除 SHA-256 完全重复副本 **{len(excluded)}** 张（{len(exact_groups)} 组）。",
              f"- pHash 原始候选 **{len(near_rows)}** 对；归一到完全重复代表文件后 **{len(pairs)}** 对，形成 **{len(groups)}** 个复核组。",
              f"- 单图重点复核：**{len(focus)}** 张；去重后共 **{len(involved)}** 张图片待人工复核。pHash 候选自动排除 **0** 张。",
              "", "## 复核规则", "",
              "- 仅 SHA-256 字节完全一致的副本自动从有效清单中排除；代表文件按相对路径排序确定，原件保持不变。",
              "- pHash 连通组只用于导航。逐对作出的“同源重复”结论才可作为未来分组划分依据；未审核或“暂不确定”的关系不能自动传递到整组。",
              "- 对低分辨率、宽高比异常及抽样中带文字/水印或场景特殊的图片，可单独标记“排除异常样本”。本阶段标记仅在审核导出中记录，不会立即修改有效清单。",
              "- 审核页面默认不预填任何人工结论。导出的 JSON/CSV 是后续应用人工决策的依据；本阶段不划分数据集。",
              "", "## 文件", "",
              "- [本地人工复核页面](review.html) · [复核案例数据](review_cases.json) · [单图重点复核](focus_review.csv)",
              "- [有效样本清单](clean_manifest.csv) · [自动排除清单](excluded_images.csv) · [全部处理记录](processing_log.csv)",
              "- [重复与候选组](duplicate_groups.csv) · [366 对候选映射](phash_pair_mapping.csv) · [处理摘要](processing_summary.json)", ""]
    (output / "report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Clean manifest: {len(manifest)}; auto excluded: {len(excluded)}; pHash groups: {len(groups)}; focus images: {len(focus)}")
    print(f"Review page: {output / 'review.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
