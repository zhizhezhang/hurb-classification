"""Backend settings resolved independently of the current working directory."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL_PATH = Path("models/convnext_tiny_best.pt")
DEFAULT_HISTORY_DB_PATH = Path("backend/runtime/history.db")
DEFAULT_UPLOADS_DIR = Path("backend/runtime/uploads")
DEFAULT_DEEPSEEK_MODEL = "deepseek-flash"
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"


@dataclass(frozen=True)
class Settings:
    model_path: Path
    device: str
    history_db_path: Path = PROJECT_ROOT / DEFAULT_HISTORY_DB_PATH
    uploads_dir: Path = PROJECT_ROOT / DEFAULT_UPLOADS_DIR

    @classmethod
    def from_env(cls) -> Settings:
        configured_path = Path(os.getenv("HERB_MODEL_PATH", str(DEFAULT_MODEL_PATH))).expanduser()
        model_path = configured_path if configured_path.is_absolute() else PROJECT_ROOT / configured_path
        device = os.getenv("HERB_DEVICE", "auto").strip().lower()
        if device not in {"auto", "cuda", "cpu"}:
            raise ValueError("HERB_DEVICE must be auto, cuda, or cpu")
        configured_db = Path(os.getenv("HERB_HISTORY_DB_PATH", str(DEFAULT_HISTORY_DB_PATH))).expanduser()
        configured_uploads = Path(os.getenv("HERB_UPLOADS_DIR", str(DEFAULT_UPLOADS_DIR))).expanduser()
        history_db_path = configured_db if configured_db.is_absolute() else PROJECT_ROOT / configured_db
        uploads_dir = configured_uploads if configured_uploads.is_absolute() else PROJECT_ROOT / configured_uploads
        return cls(model_path=model_path.resolve(), device=device,
                   history_db_path=history_db_path.resolve(), uploads_dir=uploads_dir.resolve())


@dataclass(frozen=True)
class AISettings:
    api_key: str
    model: str
    timeout_seconds: float = 20.0
    max_tokens: int = 512

    @classmethod
    def from_env(cls) -> AISettings:
        return cls(
            api_key=os.getenv("DEEPSEEK_API_KEY", "").strip(),
            model=os.getenv("DEEPSEEK_MODEL", DEFAULT_DEEPSEEK_MODEL).strip(),
        )
