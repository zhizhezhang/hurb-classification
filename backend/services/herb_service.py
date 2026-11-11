"""Load and validate atlas records once against the deployed model and artwork."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from backend.core.config import PROJECT_ROOT
from backend.schemas.herb import Herb


ATLAS_PATH = PROJECT_ROOT / "backend" / "data" / "herbs.json"
PUBLIC_ROOT = PROJECT_ROOT / "frontend" / "public"
IMAGE_PREFIX = "/assets/herbs/"
EXPECTED_COUNT = 18


@dataclass(frozen=True)
class HerbCatalog:
    ordered: tuple[Herb, ...]
    by_id: dict[str, Herb]

    def search(self, query: str | None) -> list[Herb]:
        if not query or not query.strip():
            return list(self.ordered)
        needle = query.strip().casefold()
        compact = "".join(needle.split())
        return [herb for herb in self.ordered if needle in herb.name.casefold()
                or needle in herb.pinyin.casefold()
                or compact in "".join(herb.pinyin.casefold().split())]


def load_herbs(class_to_idx: dict[str, int], atlas_path: Path = ATLAS_PATH) -> HerbCatalog:
    try:
        raw = json.loads(atlas_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Unable to read herbal atlas JSON: {atlas_path}: {exc}") from exc
    if not isinstance(raw, list) or len(raw) != EXPECTED_COUNT:
        raise RuntimeError(f"Herbal atlas must contain exactly {EXPECTED_COUNT} records")
    try:
        herbs = [Herb.model_validate(item) for item in raw]
    except ValidationError as exc:
        raise RuntimeError(f"Invalid herbal atlas record: {exc}") from exc

    ids = [item.id for item in herbs]
    names = [item.name for item in herbs]
    if len(set(ids)) != EXPECTED_COUNT or any(not re.fullmatch(r"[a-z][a-z0-9_]*", value) for value in ids):
        raise RuntimeError("Herbal atlas IDs must be unique, nonempty ASCII identifiers")
    if len(set(names)) != EXPECTED_COUNT or any(not value.strip() for value in names):
        raise RuntimeError("Herbal atlas category names must be unique and nonempty")
    if set(names) != set(class_to_idx) or len(class_to_idx) != EXPECTED_COUNT:
        raise RuntimeError("Herbal atlas categories differ from the deployed model mapping")
    if set(class_to_idx.values()) != set(range(EXPECTED_COUNT)):
        raise RuntimeError("Model mapping indices must cover 0 through 17")
    for herb in herbs:
        if herb.image_url != f"{IMAGE_PREFIX}herb_{herb.id}.png":
            raise RuntimeError(f"Invalid illustration URL for {herb.name}: {herb.image_url}")
        image_path = PUBLIC_ROOT / herb.image_url.lstrip("/")
        if not image_path.is_file():
            raise RuntimeError(f"Missing illustration for {herb.name}: {image_path}")
    ordered = tuple(sorted(herbs, key=lambda herb: class_to_idx[herb.name]))
    return HerbCatalog(ordered=ordered, by_id={herb.id: herb for herb in ordered})
