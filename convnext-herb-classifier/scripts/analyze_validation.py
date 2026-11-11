"""Rebuild a real-data report in a new directory without touching an old run."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from herb_classifier.reporting import generate_report
from herb_classifier.utils import read_config


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True, help="Existing run with metrics.csv and best.pt")
    parser.add_argument("--output-dir", required=True, help="New, empty report directory")
    parser.add_argument("--device", choices=("cuda", "cpu"), default="cuda")
    args = parser.parse_args()
    source = (ROOT / args.run_dir).resolve()
    output = (ROOT / args.output_dir).resolve()
    if ROOT not in source.parents or ROOT not in output.parents:
        raise ValueError("Both paths must be inside the training project")
    if source == output or output.exists():
        raise FileExistsError("Report output must be a new directory, separate from the source run")
    config = read_config(source / "train_config.yaml")
    output.mkdir(parents=True, exist_ok=False)
    try:
        result = generate_report(source / "metrics.csv", source / "best.pt", output,
                                 config, source / "resource_info.json", device=args.device)
    except BaseException:
        (output / "REPORT_FAILED.txt").write_text("Report generation failed; this directory is incomplete.\n",
                                                   encoding="utf-8")
        raise
    print(result)


if __name__ == "__main__":
    main()
