"""Gắn StreamHandler stderr cho ``agent`` và ``llm_pipeline`` — log luôn thấy trên terminal."""

from __future__ import annotations

import logging
import os
import sys

_done = False


def configure_package_terminal_logging() -> None:
    """Idempotent. Tắt log chi tiết agent: AGENT_TRACE=0. Mức: LOG_LEVEL (mặc định INFO)."""
    global _done
    if _done:
        return
    _done = True
    level_name = (os.getenv("LOG_LEVEL") or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s", datefmt="%H:%M:%S")
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(fmt)
    for pkg in ("agent", "llm_pipeline"):
        plog = logging.getLogger(pkg)
        if not any(
            type(h) is logging.StreamHandler and getattr(h, "stream", None) is sys.stderr for h in plog.handlers
        ):
            plog.addHandler(handler)
        plog.setLevel(level)
        plog.propagate = False
