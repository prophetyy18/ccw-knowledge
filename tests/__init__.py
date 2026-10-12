"""Shared test helpers."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Iterator


def make_tempdir(prefix: str = "ccw-test-") -> Path:
    return Path(tempfile.mkdtemp(prefix=prefix))


def isolate_home(monkeypatch, tmp_path: Path) -> None:
    """Force the engine to use ``tmp_path`` as its global root."""
    monkeypatch.setenv("CCW_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CCW_CONFIG_DIR", str(tmp_path / "home" / ".ccw-knowledge"))


def temp_home(monkeypatch) -> Path:
    base = make_tempdir()
    isolate_home(monkeypatch, base)
    return base / "home" / ".ccw-knowledge"
