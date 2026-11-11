"""Simple formal-training entry point with a selectable YAML file."""

from __future__ import annotations

import argparse
from pathlib import Path

from herb_classifier.train import train

# 在 PyCharm 直接运行时，修改这一行即可选择训练配置。
CONFIG_FILE = "configs/convnext_tiny_lr3e5.yaml"


def resolve_config(filename: str) -> Path:
    path = Path(filename).expanduser()
    if not path.is_absolute():
        path = Path(__file__).resolve().parent / path
    return path.resolve()


def main() -> None:
    parser = argparse.ArgumentParser(description="Train ConvNeXt-Tiny using a YAML configuration")
    parser.add_argument("yaml_file", nargs="?", help="YAML path, relative to this train.py")
    parser.add_argument("--config", dest="config_option", help="Same as positional YAML path")
    args = parser.parse_args()
    if args.yaml_file and args.config_option:
        parser.error("Specify the YAML file once, either as a path or with --config")
    path = resolve_config(args.config_option or args.yaml_file or CONFIG_FILE)
    if not path.is_file():
        parser.error(f"YAML file does not exist: {path}")
    print(f"Training configuration: {path}", flush=True)
    train(path)


if __name__ == "__main__":
    main()
