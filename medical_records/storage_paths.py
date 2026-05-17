"""Configurable folders for medical-record uploads and extract text (UI / API)."""

from __future__ import annotations

import os
from pathlib import Path

# repo_root defined locally to avoid rag_milvus dependency
def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _resolve_dir(raw: str) -> Path:
    p = Path(raw.strip()).expanduser()
    if not p.is_absolute():
        p = (_repo_root() / p).resolve()
    else:
        p = p.resolve()
    return p


def medical_record_upload_dir() -> Path:
    """
    Upload copies from the UI are stored here (not under ``data/``).

    Set ``MEDICAL_RECORD_SESSION_DIR`` to a dedicated root; uploads go under
    ``<SESSION_DIR>/uploads``. Otherwise default: ``upload/medical_records``.
    """
    raw = (os.getenv("MEDICAL_RECORD_SESSION_DIR") or "").strip()
    if raw:
        return _resolve_dir(raw) / "uploads"
    return _repo_root() / "upload" / "medical_records"


def medical_record_extract_dir() -> Path | None:
    """
    If not ``None``, plain-text extracts are written as ``*_extract.txt`` here.

    - With ``MEDICAL_RECORD_SESSION_DIR``: extracts default to ``<SESSION_DIR>/extracts``
      unless ``MEDICAL_RECORD_SAVE_EXTRACT`` is ``0``/``false``.
    - Without session dir: set ``MEDICAL_RECORD_SAVE_EXTRACT=1`` and optionally
      ``MEDICAL_RECORD_EXTRACT_DIR``. If extract dir is unset but save is on,
      uses ``upload/extracts`` (alongside ``upload/medical_records``).
    """
    session = (os.getenv("MEDICAL_RECORD_SESSION_DIR") or "").strip()
    if session:
        save_default = "1"
        save = (os.getenv("MEDICAL_RECORD_SAVE_EXTRACT", save_default) or save_default).strip().lower()
        if save in ("0", "false", "no", "off"):
            return None
        return _resolve_dir(session) / "extracts"

    if not _env_truthy("MEDICAL_RECORD_SAVE_EXTRACT"):
        return None
    raw = (os.getenv("MEDICAL_RECORD_EXTRACT_DIR") or "").strip()
    if raw:
        return _resolve_dir(raw)
    return _repo_root() / "upload" / "extracts"


def _env_truthy(name: str) -> bool:
    v = (os.getenv(name) or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _cleanup_on_exit_enabled() -> bool:
    """Default: enabled (remove temp upload area when the API stops). Set to 0/false to keep files."""
    v = (os.getenv("MEDICAL_RECORD_CLEANUP_ON_EXIT") or "").strip().lower()
    if v in ("0", "false", "no", "off"):
        return False
    if v in ("1", "true", "yes", "on"):
        return True
    return True


def cleanup_roots_on_exit() -> list[Path]:
    """
    Directories to remove when the FastAPI process exits.

    - If ``MEDICAL_RECORD_SESSION_DIR`` is set: remove that tree (when cleanup enabled).
    - Else: remove ``upload/medical_records`` and ``upload/extracts`` (default UI paths),
      not other files you may place under ``upload/``.

    Disable with ``MEDICAL_RECORD_CLEANUP_ON_EXIT=0``.
    """
    if not _cleanup_on_exit_enabled():
        return []
    session = (os.getenv("MEDICAL_RECORD_SESSION_DIR") or "").strip()
    if session:
        return [_resolve_dir(session)]
    root = _repo_root() / "upload"
    return [root / "medical_records", root / "extracts"]


def session_dir_for_cleanup() -> Path | None:
    """Backward-compatible: first path from :func:`cleanup_roots_on_exit`, or ``None``."""
    roots = cleanup_roots_on_exit()
    return roots[0] if roots else None


def pill_image_dataset_dir() -> Path:
    """
    Thư mục gốc chứa các folder thuốc (mỗi folder có labels.jsonl + ảnh).

    Env: ``PILL_IMAGE_DATA_DIR`` (mặc định ``data/icrawler_pills_many``), đường dẫn tương đối repo hoặc tuyệt đối.
    """
    raw = (os.getenv("PILL_IMAGE_DATA_DIR") or "data/icrawler_pills_many").strip()
    return _resolve_dir(raw)
