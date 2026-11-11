"""Apply exported human review decisions without touching the source dataset."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path


PAIR_STATES = {"same_source", "different", "uncertain"}
IMAGE_STATES = {"keep", "exclude", "uncertain"}


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decisions", type=Path, required=True, help="Exported review_decisions.json")
    parser.add_argument("--review-csv", type=Path, help="Optional CSV export for consistency checking")
    parser.add_argument("--cleaning-dir", type=Path, default=Path("reports/data_cleaning"))
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


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def union_components(edges: list[tuple[str, str]]) -> list[list[str]]:
    parent: dict[str, str] = {}

    def find(value: str) -> str:
        parent.setdefault(value, value)
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    for a, b in edges:
        parent[find(a)] = find(b)
    components: dict[str, list[str]] = defaultdict(list)
    for value in parent:
        components[find(value)].append(value)
    return sorted((sorted(group) for group in components.values()), key=lambda group: group[0])


def validate_csv_export(path: Path, cases: dict, pair_decisions: dict, image_decisions: dict) -> None:
    rows = read_csv(path)
    pair_rows = {row["id"]: row for row in rows if row["item_type"] == "pair"}
    image_rows = {row["path_a"]: row for row in rows if row["item_type"] == "image_decision"}
    focus_rows = {row["path_a"]: row for row in rows if row["item_type"] == "focus"}
    if len(pair_rows) != len(cases["pairs"]) or len(image_rows) != len(image_decisions):
        raise SystemExit("CSV export and JSON export contain different review item counts")
    for pair in cases["pairs"]:
        row = pair_rows.get(pair["id"])
        if not row or row["decision"] != pair_decisions.get(pair["id"], "pending"):
            raise SystemExit(f"CSV/JSON pair decision mismatch: {pair['id']}")
    for path, state in image_decisions.items():
        if path not in image_rows or image_rows[path]["decision"] != state:
            raise SystemExit(f"CSV/JSON image decision mismatch: {path}")
    for focus in cases["focus"]:
        path = focus["path"]
        if path not in focus_rows or focus_rows[path]["decision"] != image_decisions.get(path, "pending"):
            raise SystemExit(f"CSV/JSON focus decision mismatch: {path}")


def main() -> int:
    args = arguments()
    decisions_path = args.decisions.expanduser().resolve()
    review_csv_path = args.review_csv.expanduser().resolve() if args.review_csv else None
    cleaning_dir = args.cleaning_dir.expanduser().resolve()
    output = args.output.expanduser().resolve()
    for path in (decisions_path, cleaning_dir / "review_cases.json", cleaning_dir / "clean_manifest.csv",
                 cleaning_dir / "excluded_images.csv"):
        if not path.is_file():
            raise SystemExit(f"Required input missing: {path}")
    if review_csv_path and not review_csv_path.is_file():
        raise SystemExit(f"CSV export missing: {review_csv_path}")
    submitted = json.loads(decisions_path.read_text(encoding="utf-8-sig"))
    cases = json.loads((cleaning_dir / "review_cases.json").read_text(encoding="utf-8"))
    if submitted.get("schema_version") != 1 or submitted.get("dataset_path") != cases["dataset_path"]:
        raise SystemExit("Review JSON schema or dataset path does not match the current review cases")
    pair_decisions = submitted.get("pair_decisions", {})
    image_decisions = submitted.get("image_decisions", {})
    notes = submitted.get("notes", {})
    pairs = {pair["id"]: pair for pair in cases["pairs"]}
    if not isinstance(pair_decisions, dict) or not isinstance(image_decisions, dict) or not isinstance(notes, dict):
        raise SystemExit("Review decisions must be JSON objects")
    if set(pair_decisions) - set(pairs) or set(image_decisions) - set(cases["images"]):
        raise SystemExit("Review JSON refers to unknown pair IDs or image paths")
    if set(pair_decisions.values()) - PAIR_STATES or set(image_decisions.values()) - IMAGE_STATES:
        raise SystemExit("Review JSON contains an unknown decision value")
    if review_csv_path:
        validate_csv_export(review_csv_path, cases, pair_decisions, image_decisions)

    baseline = read_csv(cleaning_dir / "clean_manifest.csv")
    exact_excluded = read_csv(cleaning_dir / "excluded_images.csv")
    by_path = {row["path"]: row for row in baseline}
    if len(by_path) != len(baseline):
        raise SystemExit("Baseline clean_manifest.csv contains duplicate paths")
    unknown_exclusions = {path for path, state in image_decisions.items() if state == "exclude" and path not in by_path}
    if unknown_exclusions:
        raise SystemExit(f"Manual exclusion is not a baseline sample: {sorted(unknown_exclusions)[0]}")

    confirmed = [pair for pair in cases["pairs"] if pair_decisions.get(pair["id"]) == "same_source"]
    for pair in confirmed:
        if pair["path_a"] not in by_path or pair["path_b"] not in by_path:
            raise SystemExit(f"Confirmed pair is outside the baseline manifest: {pair['id']}")
        if by_path[pair["path_a"]]["class"] != by_path[pair["path_b"]]["class"]:
            raise SystemExit(f"Cross-class same-source pair needs label resolution: {pair['id']}")
    components = union_components([(pair["path_a"], pair["path_b"]) for pair in confirmed])
    group_for = {path: f"H{number:04d}" for number, members in enumerate(components, 1) for path in members}
    confirmed_groups = []
    for number, members in enumerate(components, 1):
        group_id = f"H{number:04d}"
        support = sorted(pair["id"] for pair in confirmed if pair["path_a"] in members and pair["path_b"] in members)
        excluded_count = sum(image_decisions.get(path) == "exclude" for path in members)
        confirmed_groups.append({"group_id": group_id, "class": by_path[members[0]]["class"],
                                 "member_count": len(members), "kept_count": len(members) - excluded_count,
                                 "manually_excluded_count": excluded_count,
                                 "member_paths_json": json.dumps(members, ensure_ascii=False),
                                 "confirmed_pair_ids_json": json.dumps(support, ensure_ascii=False)})

    reviewed_manifest = []
    manual_excluded = []
    application_log = []
    for row in baseline:
        path = row["path"]
        decision = image_decisions.get(path, "pending")
        action = "exclude" if decision == "exclude" else "keep"
        note = notes.get("image:" + path, "")
        result = {**row, "image_review_decision": decision,
                  "confirmed_source_group_id": group_for.get(path, ""), "review_note": note}
        application_log.append({"class": row["class"], "path": path, "action": action,
                                "reason": "manual_exclude" if action == "exclude" else "retained",
                                "image_review_decision": decision,
                                "confirmed_source_group_id": group_for.get(path, ""), "review_note": note})
        if action == "keep":
            reviewed_manifest.append(result)
        else:
            manual_excluded.append({"class": row["class"], "path": path, "representative_path": path,
                                    "sha256": row["sha256"], "phash": row["phash"],
                                    "exact_group_id": row["confirmed_exact_group_id"],
                                    "action": "exclude", "reason": "manual_exclude",
                                    "review_note": note, "decision_source": "submitted_review_json"})
    all_excluded = [{**row, "review_note": "", "decision_source": "task02_exact_dedup"} for row in exact_excluded] + manual_excluded
    pending_pairs = [{"id": pair["id"], "group_id": pair["group_id"], "class": by_path[pair["path_a"]]["class"],
                      "path_a": pair["path_a"], "path_b": pair["path_b"], "phash_distance": pair["distance"]}
                     for pair in cases["pairs"] if pair["id"] not in pair_decisions]
    pending_group_ids = sorted({pair["group_id"] for pair in pending_pairs})
    uncertain_images = [path for path, state in image_decisions.items() if state == "uncertain"]

    output.mkdir(parents=True, exist_ok=True)
    write_csv(output / "reviewed_clean_manifest.csv", reviewed_manifest,
              list(baseline[0]) + ["image_review_decision", "confirmed_source_group_id", "review_note"])
    write_csv(output / "reviewed_excluded_images.csv", all_excluded,
              ["class", "path", "representative_path", "sha256", "phash", "exact_group_id", "action", "reason",
               "review_note", "decision_source"])
    write_csv(output / "confirmed_source_groups.csv", confirmed_groups,
              ["group_id", "class", "member_count", "kept_count", "manually_excluded_count",
               "member_paths_json", "confirmed_pair_ids_json"])
    write_csv(output / "pending_review_pairs.csv", pending_pairs,
              ["id", "group_id", "class", "path_a", "path_b", "phash_distance"])
    write_csv(output / "review_application_log.csv", application_log,
              ["class", "path", "action", "reason", "image_review_decision", "confirmed_source_group_id", "review_note"])
    (output / "review_decisions_submitted.json").write_bytes(decisions_path.read_bytes())
    if review_csv_path:
        (output / "review_decisions_submitted.csv").write_bytes(review_csv_path.read_bytes())

    counts = Counter(pair_decisions.values())
    image_counts = Counter(image_decisions.values())
    stats = {"schema_version": 1, "dataset_path": cases["dataset_path"],
             "submitted_exported_at": submitted.get("exported_at"),
             "input_json_sha256": sha256(decisions_path),
             "input_csv_sha256": sha256(review_csv_path) if review_csv_path else None,
             "baseline_clean_images": len(baseline), "baseline_exact_exclusions": len(exact_excluded),
             "review_candidate_pairs": len(cases["pairs"]), "pair_decisions": dict(counts),
             "pending_pair_count": len(pending_pairs), "pending_group_ids": pending_group_ids,
             "confirmed_source_groups": len(confirmed_groups),
             "image_decisions": dict(image_counts), "manual_image_exclusions": len(manual_excluded),
             "uncertain_image_paths": uncertain_images,
             "reviewed_clean_images": len(reviewed_manifest), "total_excluded_images": len(all_excluded),
             "pending_pairs_kept": True, "uncertain_images_kept": True,
             "confirmed_pairs_not_auto_removed": True}
    (output / "review_summary.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# 人工复核结果应用报告", "",
             f"- 与当前候选清单匹配；JSON 与 CSV 结论一致。导出时间（UTC）：`{stats['submitted_exported_at']}`。",
             f"- pHash 候选 **{len(cases['pairs'])}** 对：人工确认同源 **{counts['same_source']}** 对；不同图片 **{counts['different']}** 对；暂不确定 **{counts['uncertain']}** 对；未选择 **{len(pending_pairs)}** 对。",
             f"- 确认同源关系构成 **{len(confirmed_groups)}** 个关系组，仅供后续按组划分参考；这些关系没有触发额外删图。",
             f"- 单图标记：排除 **{len(manual_excluded)}** 张、保留 **{image_counts['keep']}** 张、暂不确定 **{image_counts['uncertain']}** 张。",
             f"- 当前有效清单 **{len(reviewed_manifest)}** 张；累计排除 **{len(all_excluded)}** 张（完全重复副本 {len(exact_excluded)} + 人工异常排除 {len(manual_excluded)}）。",
             f"- 待回看的候选组：`{', '.join(pending_group_ids)}`；暂不确定的单图：`{', '.join(uncertain_images) if uncertain_images else '无'}`。",
             "", "## 保守处理", "",
             "未选择的图片对以及暂不确定的图片继续保留，并在单独文件中记录。只有用户明确选择“同源重复”的边被纳入确认关系组。原始数据集、任务 01 审计结果和基线清单均保持不变。",
             "", "## 输出", "",
             "- [复核后有效清单](reviewed_clean_manifest.csv) · [累计排除清单](reviewed_excluded_images.csv) · [确认同源组](confirmed_source_groups.csv)",
             "- [未审核图片对](pending_review_pairs.csv) · [逐图处理记录](review_application_log.csv) · [复核摘要](review_summary.json)",
             "- [提交的 JSON](review_decisions_submitted.json) · [提交的 CSV](review_decisions_submitted.csv)", ""]
    (output / "review_report.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Reviewed clean images: {len(reviewed_manifest)}; total excluded: {len(all_excluded)}")
    print(f"Confirmed source groups: {len(confirmed_groups)}; pending pairs: {len(pending_pairs)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
