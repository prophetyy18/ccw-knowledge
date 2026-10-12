"""Project identity, registration, attach, and detach.

A *project* is a directory that the user wants ccw-knowledge to support.
Each project registers against the global engine (one file under
``~/.ccw-knowledge/projects/<id>.json``) and writes a tiny local config
file (``.ccw-knowledge.json``) inside the project root.

Identity:
- ``project_id`` defaults to a slug of the directory name plus a short
  fingerprint of the resolved absolute path. The fingerprint avoids
  collisions between two machines that share a Vault.
- The resolved absolute path of the project root is stored only on this
  machine (in the global config); it is never written into the Vault
  or shared with another machine.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from . import errors as _err
from .config import projects_dir, save_global_config
from .pathutil import (
    encode_project_path_for_storage,
    normalise_path,
    project_id_from_path,
)
from .scope import ScopeSet
from .vault import VaultLayout, ensure_project_space

LOCAL_CONFIG_FILENAME = ".ccw-knowledge.json"

# Markers we may write into a project's CLAUDE.md. The attach command
# uses these to introduce a non-intrusive section that detach can remove.
CLAUDE_MARK_BEGIN = "<!-- ccw-knowledge:begin -->"
CLAUDE_MARK_END = "<!-- ccw-knowledge:end -->"
CLAUDE_MARK_SECTION = """
<!-- ccw-knowledge:begin -->
This project uses ccw-knowledge. Knowledge Skills (`/knowledge-context`,
`/knowledge-capture`, `/knowledge-review`, `/knowledge-audit`) are available.
Run `ccw-knowledge status` to inspect the current state.
<!-- ccw-knowledge:end -->
""".strip()


@dataclass
class ProjectConfig:
    """The on-disk representation of ``<project>/.ccw-knowledge.json``.

    Only fields that are safe to share or that the user explicitly opted
    into live here. Absolute local paths never do.
    """

    version: int = 1
    project_id: str = ""
    knowledge_enabled: bool = True
    scopes: List[str] = field(default_factory=lambda: [])
    default_depth: str = "standard"
    context_budget: int = 2000
    capture_enabled: bool = True
    automatic_publication: bool = False
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict) -> "ProjectConfig":
        return cls(
            version=int(raw.get("version", 1)),
            project_id=str(raw.get("project_id", "")),
            knowledge_enabled=bool(raw.get("knowledge", {}).get("enabled", True)),
            scopes=list(raw.get("knowledge", {}).get("scopes", [])),
            default_depth=str(raw.get("retrieval", {}).get("default_depth", "standard")),
            context_budget=int(raw.get("retrieval", {}).get("context_budget", 2000)),
            capture_enabled=bool(raw.get("capture", {}).get("enabled", True)),
            automatic_publication=bool(raw.get("capture", {}).get("automatic_publication", False)),
            extra=dict(raw.get("extra", {})),
        )

    @classmethod
    def file_format_dict(cls, cfg: "ProjectConfig") -> dict:
        """Render in the YAML-style layout used in the example config."""
        return {
            "version": cfg.version,
            "project_id": cfg.project_id,
            "knowledge": {
                "enabled": cfg.knowledge_enabled,
                "scopes": cfg.scopes,
            },
            "retrieval": {
                "default_depth": cfg.default_depth,
                "context_budget": cfg.context_budget,
            },
            "capture": {
                "enabled": cfg.capture_enabled,
                "automatic_publication": cfg.automatic_publication,
            },
        }


@dataclass
class ProjectRecord:
    """The on-disk representation of ``<engine-root>/projects/<id>.json``."""

    version: int = 1
    project_id: str = ""
    project_root: str = ""
    registered_at: str = ""
    scopes: List[str] = field(default_factory=list)
    config_path: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _yaml_like_dump(d: dict, indent: int = 0) -> str:
    """Tiny YAML-ish serializer for ``ProjectConfig``.

    Supports dicts, lists, strings, ints, bools. Adequate for the small
    config file this tool writes (and avoids a PyYAML dependency).
    """
    pad = "  " * indent
    lines: List[str] = []
    if isinstance(d, dict):
        for k, v in d.items():
            if isinstance(v, (dict, list)):
                lines.append(f"{pad}{k}:")
                lines.append(_yaml_like_dump(v, indent + 1))
            elif isinstance(v, bool):
                lines.append(f"{pad}{k}: {'true' if v else 'false'}")
            elif isinstance(v, (int, float)):
                lines.append(f"{pad}{k}: {v}")
            elif isinstance(v, str):
                if v == "":
                    lines.append(f"{pad}{k}:")
                else:
                    lines.append(f"{pad}{k}: {v}")
            elif v is None:
                lines.append(f"{pad}{k}:")
            else:
                lines.append(f"{pad}{k}: {v}")
        return "\n".join(lines)
    if isinstance(d, list):
        for item in d:
            if isinstance(item, dict):
                lines.append(f"{pad}-")
                lines.append(_yaml_like_dump(item, indent + 1))
            else:
                lines.append(f"{pad}- {item}")
        return "\n".join(lines)
    return f"{pad}{d}"


def write_local_config(project_root: Path, cfg: ProjectConfig) -> Path:
    path = project_root / LOCAL_CONFIG_FILENAME
    rendered = _yaml_like_dump(ProjectConfig.file_format_dict(cfg)) + "\n"
    _atomic_write_text(path, rendered)
    return path


def _atomic_write_text(path: Path, content: str) -> None:
    import tempfile

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
        try:
            dfd = os.open(str(path.parent), os.O_DIRECTORY)
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
        except (OSError, AttributeError):
            pass
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def load_local_config(project_root: Path) -> Optional[ProjectConfig]:
    path = project_root / LOCAL_CONFIG_FILENAME
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    raw = _yaml_like_load(text)
    if not isinstance(raw, dict):
        raise _err.ProjectError(f"malformed local config: {path}")
    return ProjectConfig.from_dict(raw)


def _yaml_like_load(text: str) -> dict:
    """Tiny YAML-ish parser for ``ProjectConfig``.

    Sufficient for the layout ``write_local_config`` emits. Complicated
    YAML would require PyYAML; we explicitly do not support that to keep
    zero dependencies.
    """
    lines = []
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        lines.append(raw)
    root: dict = {}
    pos, _ = _yaml_parse_block(lines, 0, root, base_indent=0)
    return root


def _yaml_parse_block(lines, idx, into, base_indent):
    """Parse a YAML block whose content starts at indent ``base_indent``.

    Supports:
    - ``key: value`` scalars
    - ``key:`` followed by an indented mapping (recursive)
    - ``key:`` followed by a list of ``- item`` lines (same indent as
      children of the parent block)
    - ``- item`` inline lists at the start of a block

    Returns ``(next_idx, parsed_block)``.
    """
    # First, list items take precedence at the start of a block.
    while idx < len(lines):
        line = lines[idx]
        if not line.strip():
            idx += 1
            continue
        lead = len(line) - len(line.lstrip(" "))
        if lead < base_indent:
            return idx, into
        if lead > base_indent:
            raise _err.ProjectError(
                f"unexpected indent at {line!r} (base={base_indent}, got={lead})"
            )
        stripped = line.strip()
        # Inline list of ``- item``.
        if stripped.startswith("- "):
            # Caller is the list, but we support it inline.
            value = _yaml_scalar(stripped[2:].strip())
            into.setdefault("__list__", []).append(value)
            idx += 1
            continue
        if ":" not in line:
            raise _err.ProjectError(f"expected key: value line, got: {line!r}")
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if value == "":
            # Look ahead for the sub-block.
            j = idx + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j >= len(lines):
                into[key] = {}
                idx = j
                continue
            child = lines[j]
            child_stripped = child.strip()
            child_lead = len(child) - len(child.lstrip(" "))
            if child_lead <= base_indent:
                into[key] = {}
                idx = j
                continue
            if child_stripped.startswith("- "):
                # List under the key.
                items: list = []
                k = j
                while k < len(lines):
                    line2 = lines[k]
                    if not line2.strip():
                        k += 1
                        continue
                    cl = len(line2) - len(line2.lstrip(" "))
                    if cl < child_lead:
                        break
                    if cl > child_lead:
                        raise _err.ProjectError(
                            f"inconsistent list indent at {line2!r}"
                        )
                    s2 = line2.strip()
                    if not s2.startswith("- "):
                        break
                    items.append(_yaml_scalar(s2[2:].strip()))
                    k += 1
                into[key] = items
                idx = k
                continue
            else:
                # Mapping under the key.
                sub: dict = {}
                k, _ = _yaml_parse_block(lines, j, sub, base_indent=child_lead)
                into[key] = sub
                idx = k
                continue
        into[key] = _yaml_scalar(value)
        idx += 1
    return idx, into


def _yaml_scalar(value: str):
    s = value.strip()
    if s.startswith('"') and s.endswith('"'):
        return s[1:-1]
    if s.startswith("'") and s.endswith("'"):
        return s[1:-1]
    if s.lower() == "true":
        return True
    if s.lower() == "false":
        return False
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return s


def project_record_path(project_id: str) -> Path:
    safe = _safe_id(project_id)
    return projects_dir() / f"{safe}.json"


def _safe_id(pid: str) -> str:
    """Make ``project_id`` filesystem-safe (defensive; IDs are usually clean)."""
    pid = pid.strip().strip("/\\")
    if not pid:
        raise _err.ProjectError("empty project id")
    if ".." in pid.split("/") or ".." in pid.split("\\"):
        raise _err.ProjectError("project id contains path traversal")
    return pid


def save_project_record(rec: ProjectRecord) -> Path:
    p = project_record_path(rec.project_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_json(p, rec.to_dict())
    return p


def _atomic_write_json(path: Path, payload: dict) -> None:
    import tempfile

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
        try:
            dfd = os.open(str(path.parent), os.O_DIRECTORY)
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
        except (OSError, AttributeError):
            pass
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def load_project_record(project_id: str) -> Optional[ProjectRecord]:
    p = project_record_path(project_id)
    if not p.exists():
        return None
    raw = json.loads(p.read_text(encoding="utf-8"))
    return ProjectRecord(
        version=int(raw.get("version", 1)),
        project_id=str(raw.get("project_id", project_id)),
        project_root=str(raw.get("project_root", "")),
        registered_at=str(raw.get("registered_at", "")),
        scopes=list(raw.get("scopes", [])),
        config_path=str(raw.get("config_path", "")),
    )


def derive_project_id(project_root: Path, explicit_id: Optional[str] = None) -> str:
    """Pick a project id.

    If ``explicit_id`` is supplied and clean, use that. Otherwise derive a
    slug+fingerprint from the resolved project root.
    """
    if explicit_id:
        return _safe_id(explicit_id)
    return project_id_from_path(project_root)


def attach(
    project_root: Path,
    vault: VaultLayout,
    project_id: Optional[str] = None,
    scopes: Optional[List[str]] = None,
    update_claude_md: bool = False,
) -> ProjectRecord:
    """Register a project and write the minimal local config.

    Does NOT:
    - modify business code
    - generate knowledge content
    - scan the project
    - overwrite the project's existing CLAUDE.md
    """
    root = normalise_path(str(project_root))
    if not root.exists() or not root.is_dir():
        raise _err.ProjectError(f"project root is not a directory: {root}")
    pid = derive_project_id(root, project_id)
    # Idempotency: existing registration
    existing = load_project_record(pid)
    scope_set = ScopeSet.parse(scopes or [f"project:{pid}", "shared"])
    # Always make sure the project space in the Vault exists.
    ensure_project_space(vault, pid)

    local_cfg = load_local_config(root) or ProjectConfig()
    local_cfg.project_id = pid
    local_cfg.knowledge_enabled = True
    local_cfg.scopes = scope_set.to_list()
    write_local_config(root, local_cfg)

    rec = ProjectRecord(
        version=1,
        project_id=pid,
        project_root=str(root),
        registered_at=datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        scopes=scope_set.to_list(),
        config_path=str(root / LOCAL_CONFIG_FILENAME),
    )
    save_project_record(rec)

    if update_claude_md:
        update_project_claude_md(root, add=True)

    return rec


def detach(
    project_root: Path,
    project_id: Optional[str] = None,
    keep_local_config: bool = False,
    remove_claude_md_section: bool = True,
) -> Optional[ProjectRecord]:
    """Remove a project's registration and (optionally) its local config.

    Does not delete Vault knowledge under that project's namespace.
    """
    root = normalise_path(str(project_root))
    pid = derive_project_id(root, project_id)
    rec = load_project_record(pid)
    if rec is None and not (root / LOCAL_CONFIG_FILENAME).exists():
        return None
    rec_path = project_record_path(pid)
    if rec_path.exists():
        rec_path.unlink()
    if not keep_local_config:
        cfg_path = root / LOCAL_CONFIG_FILENAME
        if cfg_path.exists():
            cfg_path.unlink()
    if remove_claude_md_section:
        restore_project_claude_md(root)
    return rec


def update_project_claude_md(project_root: Path, *, add: bool) -> None:
    """Add or remove the ccw-knowledge section in the project's CLAUDE.md.

    We never touch user-written content outside our marked block. The
    block uses HTML comment markers so that downstream tools render it as
    a comment; we also keep the human-readable text below the end marker.
    """
    candidates = ["CLAUDE.md", "AGENTS.md"]
    if not add:
        for name in candidates:
            path = project_root / name
            if path.exists():
                _strip_ccw_section(path)
        return
    target = None
    for name in candidates:
        path = project_root / name
        if path.exists():
            target = path
            break
    if target is None:
        # Don't create one — the user's choice to skip this should be respected.
        return
    text = target.read_text(encoding="utf-8")
    if CLAUDE_MARK_BEGIN in text:
        return
    sep = "" if text.endswith("\n") else "\n"
    new = f"{text}{sep}{CLAUDE_MARK_SECTION}\n"
    _atomic_write_text(target, new)


def restore_project_claude_md(project_root: Path) -> None:
    """Convenience: pass `add=False` to ``update_project_claude_md``."""
    update_project_claude_md(project_root, add=False)


def _strip_ccw_section(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if CLAUDE_MARK_BEGIN not in text:
        return
    pattern = re.compile(
        re.escape(CLAUDE_MARK_BEGIN) + r".*?" + re.escape(CLAUDE_MARK_END) + r"\n?",
        re.DOTALL,
    )
    new = pattern.sub("", text).rstrip() + "\n"
    _atomic_write_text(path, new)


__all__ = [
    "ProjectConfig",
    "ProjectRecord",
    "LOCAL_CONFIG_FILENAME",
    "CLAUDE_MARK_BEGIN",
    "CLAUDE_MARK_END",
    "CLAUDE_MARK_SECTION",
    "project_record_path",
    "save_project_record",
    "load_project_record",
    "derive_project_id",
    "attach",
    "detach",
    "update_project_claude_md",
    "write_local_config",
    "load_local_config",
]
