"""Cross-platform path utilities.

Goals:
- Honour ``$HOME`` / ``%USERPROFILE%`` / ``$CCW_HOME`` consistently.
- Produce absolute, normalised paths.
- Be robust to whitespace and trailing separators.
- Never assume Unix or Windows path conventions in stored data.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Optional

# A reasonable guess at "is this a Windows path" — used only for ergonomic
# reporting. All filesystem operations use ``pathlib``.
_WINDOWS_PATH_RE = re.compile(r"^[A-Za-z]:[\\/]")


def home_directory() -> Path:
    """Return the user's home directory.

    Honours ``$CCW_HOME`` if set, then ``$HOME`` (POSIX) or
    ``%USERPROFILE%`` (Windows). Falls back to ``Path.home()``.
    """
    override = os.environ.get("CCW_HOME")
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == "win32":
        userprofile = os.environ.get("USERPROFILE")
        if userprofile:
            return Path(userprofile).expanduser().resolve()
    home = os.environ.get("HOME")
    if home:
        return Path(home).expanduser().resolve()
    return Path.home().resolve()


def global_config_root() -> Path:
    """Return the directory holding the engine's global state.

    Defaults to ``<home>/.ccw-knowledge``. Override by setting ``$CCW_CONFIG_DIR``.
    """
    override = os.environ.get("CCW_CONFIG_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return home_directory() / ".ccw-knowledge"


def looks_like_windows_path(value: str) -> bool:
    """Heuristic only — does not assert anything about the runtime OS."""
    return bool(_WINDOWS_PATH_RE.match(value.strip()))


def normalise_path(value: str | os.PathLike) -> Path:
    """Resolve, expand, and return an absolute Path.

    Accepts forward-slash and back-slash inputs. Tilde (``~``) is expanded.
    """
    if isinstance(value, Path):
        return value.expanduser().resolve()
    text = str(value).strip().strip('"').strip("'")
    if not text:
        raise ValueError("path is empty")
    # pathlib handles both POSIX and Windows separators on the host OS.
    return Path(text).expanduser().resolve()


def safe_resolve(path: Path) -> Path:
    """Resolve to an absolute, normalised path without raising on broken symlinks."""
    return Path(os.path.normpath(str(path))).resolve()


def is_within(child: Path, parent: Path) -> bool:
    """Return True if ``child`` is within ``parent`` (after resolution).

    This is a logical boundary check. A symlink that resolves outside the
    parent directory is still reported as "within" if it starts with the
    parent's prefix string — for security-critical checks use
    :func:`strictly_within` which also resolves symlinks.
    """
    child_str = str(child)
    parent_str = str(parent)
    # Ensure trailing separator for prefix matching (don't match "/foo" vs "/foobar").
    if not parent_str.endswith(os.sep):
        parent_str = parent_str + os.sep
    return child_str == parent_str.rstrip(os.sep) or child_str.startswith(parent_str)


def strictly_within(child: Path, parent: Path) -> bool:
    """Like :func:`is_within` but also checks the resolved real path.

    Use this when the operation has side effects (writes) or pulls
    confidential content. Note: resolving can raise on broken symlinks;
    callers should handle ``OSError``.
    """
    try:
        real_child = child.resolve()
        real_parent = parent.resolve()
    except (OSError, RuntimeError):
        return False
    return is_within(real_child, real_parent)


def to_forward_slashes(path: Path | str) -> str:
    """Normalise to forward-slash form for portable storage (frontmatter values).

    On Windows, ``PurePosixPath`` representation is only a display convenience;
    the absolute path on the host OS is what matters for I/O.
    """
    s = str(path)
    return s.replace("\\", "/")


def encode_project_path_for_storage(path: Path) -> str:
    """Encode an absolute project path for cross-machine portability checks.

    Returns a fingerprint: a deterministic digest of the resolved absolute
    path. Two different machines sharing the same project produce the same
    fingerprint for the canonicalised path. This is used as part of project
    identity to avoid name collisions.

    Note: the *value* of the absolute local path is intentionally NOT stored
    in shared files. Only the fingerprint is.
    """
    import hashlib

    s = str(Path(path).expanduser().resolve())
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:12]


def project_id_from_path(path: Path) -> str:
    """Derive a default project id from a project root directory name.

    Slugifies the basename, lowers, replaces non-alphanumeric runs with
    ``-``. Adds the path fingerprint as a suffix to disambiguate projects
    that share the same directory name on different machines.
    """
    import re as _re

    name = Path(path).expanduser().resolve().name or "project"
    slug = _re.sub(r"[^a-zA-Z0-9]+", "-", name).strip("-").lower() or "project"
    return f"{slug}-{encode_project_path_for_storage(path)}"
