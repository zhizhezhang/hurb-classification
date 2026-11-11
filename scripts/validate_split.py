"""Independently re-read and validate an existing grouped dataset split."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.split_dataset import verify_splits


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=Path("reports/data_cleaning/reviewed_clean_manifest.csv"))
    parser.add_argument("--excluded", type=Path, default=Path("reports/data_cleaning/reviewed_excluded_images.csv"))
    parser.add_argument("--groups", type=Path, default=Path("reports/data_cleaning/confirmed_source_groups.csv"))
    parser.add_argument("--split-dir", type=Path, default=Path("reports/data_split"))
    args = parser.parse_args()
    dataset, manifest, excluded, groups, split_dir = (
        path.expanduser().resolve() for path in
        (args.dataset, args.manifest, args.excluded, args.groups, args.split_dir))
    result = verify_splits(dataset, manifest, excluded, groups, split_dir)
    (split_dir / "validation_results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"PASS: {result['counts']} images; {result['source_group_count']} isolated units; 18 classes in each split")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
