"""Common harness for end-to-end CLI tests."""

from __future__ import annotations

import io
import json
import os
import shutil
import tempfile
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Iterable, Tuple

from ccw_knowledge import cli


class CLIRunner:
    """Invoke the CLI as a subprocess would, but in-process."""

    def __init__(self, home: Path):
        self.home = home
        self.last_stdout = ""
        self.last_stderr = ""
        self.last_returncode = 0

    def run(self, *argv: str) -> int:
        buf_out = io.StringIO()
        buf_err = io.StringIO()
        with redirect_stdout(buf_out), redirect_stderr(buf_err):
            try:
                rc = cli.main(list(argv))
            except SystemExit as e:
                rc = int(e.code or 0)
        self.last_stdout = buf_out.getvalue()
        self.last_stderr = buf_err.getvalue()
        self.last_returncode = rc
        return rc

    def json(self) -> dict:
        try:
            return json.loads(self.last_stdout)
        except json.JSONDecodeError:
            return {}


def isolated_home(tmp_parent: Path) -> Tuple[Path, Path]:
    """Return (home_dir, vault_dir) within tmp_parent.

    Sets environment so the engine state goes inside tmp_parent."""
    home = tmp_parent / "home"
    vault = tmp_parent / "vault"
    os.environ["CCW_HOME"] = str(home)
    os.environ["CCW_CONFIG_DIR"] = str(home / ".ccw-knowledge")
    return home, vault


@contextmanager
def fresh_environment():
    with tempfile.TemporaryDirectory() as tmp:
        home, vault = isolated_home(Path(tmp))
        home.mkdir(parents=True, exist_ok=True)
        yield Path(tmp), home, vault
