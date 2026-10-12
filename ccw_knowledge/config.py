"""Global engine configuration.

Only one configuration file lives on this machine:

    <CCW_HOME>/.ccw-knowledge/config.json

Vault absolute paths live here. Projects get their own per-project
metadata files under ``<CCW_HOME>/.ccw-knowledge/projects/<id>.json``.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional

from .errors import ConfigError, NotInitialized
from .pathutil import global_config_root, normalise_path

CONFIG_FILENAME = "config.json"
PROJECTS_DIRNAME = "projects"


@dataclass
class GlobalConfig:
    """In-memory representation of ``~/.ccw-knowledge/config.json``."""

    version: int = 1
    vault: Optional[str] = None
    engine_version: str = "1.0.0"

    def is_initialised(self) -> bool:
        return bool(self.vault)

    def validate(self) -> None:
        if self.version != 1:
            raise ConfigError(f"unsupported global config version: {self.version}")
        if not self.vault:
            raise ConfigError("vault path is not set; run `ccw-knowledge init --vault PATH`")


def global_config_path() -> Path:
    return global_config_root() / CONFIG_FILENAME


def projects_dir() -> Path:
    return global_config_root() / PROJECTS_DIRNAME


def load_global_config(path: Optional[Path] = None) -> GlobalConfig:
    p = path or global_config_path()
    if not p.exists():
        return GlobalConfig()
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ConfigError(f"malformed {p}: {e}") from e
    if not isinstance(raw, dict):
        raise ConfigError(f"malformed {p}: top-level must be an object")
    cfg = GlobalConfig(
        version=int(raw.get("version", 1)),
        vault=raw.get("vault"),
        engine_version=str(raw.get("engine_version", "1.0.0")),
    )
    if cfg.vault:
        # Resolve once on load; tolerate broken paths by keeping the raw string.
        try:
            cfg.vault = str(normalise_path(cfg.vault))
        except Exception:
            pass
    return cfg


def save_global_config(cfg: GlobalConfig, path: Optional[Path] = None) -> Path:
    p = path or global_config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(cfg)
    _atomic_write_json(p, payload)
    return p


def ensure_initialised() -> GlobalConfig:
    """Raise :class:`NotInitialized` unless ``init`` has been run."""
    cfg = load_global_config()
    if not cfg.is_initialised():
        raise NotInitialized(
            "ccw-knowledge is not initialised. Run `ccw-knowledge init --vault <path>` first."
        )
    cfg.validate()
    return cfg


def _atomic_write_json(path: Path, payload: dict) -> None:
    """Atomic JSON write: tmp + fsync + os.replace.

    We avoid holding a file handle across the replace so that readers see
    either the old or the new file — never a half-written one.
    """
    import json as _json
    import os
    import tempfile

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            _json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
        try:
            # fsync the directory for durability on POSIX.
            dir_fd = os.open(str(path.parent), os.O_DIRECTORY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except (OSError, AttributeError):
            pass
    except Exception:
        # Clean up temp on failure.
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


__all__ = [
    "GlobalConfig",
    "global_config_path",
    "projects_dir",
    "load_global_config",
    "save_global_config",
    "ensure_initialised",
]
