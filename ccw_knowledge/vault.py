"""Vault layout and project space management.

The Vault is a directory tree whose top level hosts ``shared/`` and
``projects/<id>/`` subtrees. Each subtree contains three buckets:

    sources/    immutable raw materials (URL fetches, dumps, transcripts)
    candidates/ awaiting review (default state for new knowledge)
    knowledge/  approved published knowledge
    _meta.json  per-area metadata

These are the only directories created on init. We do not write to any
file inside an existing user's Obsidian tree other than those we created
ourselves (``_meta.json`` is also ours).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

from . import errors as _err
from .config import GlobalConfig, ensure_initialised, save_global_config
from .pathutil import normalise_path, strictly_within

SHARED_DIR = "shared"
PROJECTS_DIR = "projects"
SOURCES_DIR = "sources"
CANDIDATES_DIR = "candidates"
KNOWLEDGE_DIR = "knowledge"

PROJECT_META = "_meta.json"


@dataclass
class ProjectSpace:
    """A project's private subtree inside the Vault."""

    project_id: str
    root: Path
    sources: Path
    candidates: Path
    knowledge: Path

    @classmethod
    def from_root(cls, project_id: str, root: Path) -> "ProjectSpace":
        return cls(
            project_id=project_id,
            root=root,
            sources=root / SOURCES_DIR,
            candidates=root / CANDIDATES_DIR,
            knowledge=root / KNOWLEDGE_DIR,
        )


@dataclass
class VaultLayout:
    """Concrete paths of a fully initialised Vault."""

    root: Path
    shared_sources: Path
    shared_candidates: Path
    shared_knowledge: Path
    projects_root: Path

    @classmethod
    def from_root(cls, root: Path) -> "VaultLayout":
        return cls(
            root=root,
            shared_sources=root / SHARED_DIR / SOURCES_DIR,
            shared_candidates=root / SHARED_DIR / CANDIDATES_DIR,
            shared_knowledge=root / SHARED_DIR / KNOWLEDGE_DIR,
            projects_root=root / PROJECTS_DIR,
        )

    def project_space(self, project_id: str) -> ProjectSpace:
        return ProjectSpace.from_root(
            project_id, self.projects_root / project_id
        )

    def known_project_ids(self) -> list[str]:
        if not self.projects_root.exists():
            return []
        out = []
        for p in sorted(self.projects_root.iterdir()):
            if p.is_dir() and (p / SOURCES_DIR).exists():
                out.append(p.name)
        return out


def resolve_vault(cfg: Optional[GlobalConfig] = None) -> VaultLayout:
    cfg = cfg or ensure_initialised()
    cfg.validate()
    root = Path(cfg.vault).expanduser().resolve()
    if not root.exists():
        raise _err.VaultError(f"vault path no longer exists: {root}")
    if not root.is_dir():
        raise _err.VaultError(f"vault path is not a directory: {root}")
    layout = VaultLayout.from_root(root)
    if not (layout.shared_sources.exists() and layout.shared_knowledge.exists()):
        raise _err.VaultError(
            f"vault at {root} is not initialised; run `ccw-knowledge init --vault {root}`"
        )
    return layout


def init_vault(vault_path: str | os.PathLike, *, force: bool = False) -> VaultLayout:
    """Create or repair the Vault layout.

    - If the directory does not exist we create it.
    - If it does exist we ensure our four subdirectories exist (created
      if missing) and that ``shared/`` itself exists.
    - We never delete user content.

    The check is permissive: we do not refuse to create ``sources/`` /
    ``candidates/`` / ``knowledge/`` / ``projects/`` simply because a
    sibling already exists. The user owns the Vault root and explicitly
    invoked ``init`` on it; the directory's existing content is theirs.
    """
    root = normalise_path(str(vault_path))
    if root.exists() and not root.is_dir():
        raise _err.VaultError(f"vault path exists but is not a directory: {root}")
    if not root.exists():
        root.mkdir(parents=True, exist_ok=True)
    layout = VaultLayout.from_root(root)
    # shared/ and projects/ are the only two top-level subdirs we own.
    layout.root.mkdir(parents=True, exist_ok=True)
    (layout.root / "shared").mkdir(parents=True, exist_ok=True)
    layout.projects_root.mkdir(parents=True, exist_ok=True)
    # Now create the three bucket directories under shared/ if missing.
    for d in (layout.shared_sources, layout.shared_candidates, layout.shared_knowledge):
        if d.exists():
            if not d.is_dir():
                raise _err.VaultError(f"refusing to overwrite non-directory: {d}")
            continue
        d.mkdir(parents=True, exist_ok=True)
    # Write _meta files for the shared area.
    _write_meta_if_missing(layout.shared_sources, {"kind": "shared-sources", "version": 1})
    _write_meta_if_missing(layout.shared_candidates, {"kind": "shared-candidates", "version": 1})
    _write_meta_if_missing(layout.shared_knowledge, {"kind": "shared-knowledge", "version": 1})

    cfg = GlobalConfig(vault=str(root))
    save_global_config(cfg)
    return layout


def _write_meta_if_missing(path: Path, payload: dict) -> None:
    meta = path / PROJECT_META
    if not meta.exists():
        meta.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def ensure_project_space(vault: VaultLayout, project_id: str) -> ProjectSpace:
    """Create the project's subtree if it doesn't exist yet."""
    space = vault.project_space(project_id)
    for d in (space.sources, space.candidates, space.knowledge):
        d.mkdir(parents=True, exist_ok=True)
    _write_meta_if_missing(
        space.sources,
        {"kind": "project-sources", "project_id": project_id, "version": 1},
    )
    _write_meta_if_missing(
        space.candidates,
        {"kind": "project-candidates", "project_id": project_id, "version": 1},
    )
    _write_meta_if_missing(
        space.knowledge,
        {"kind": "project-knowledge", "project_id": project_id, "version": 1},
    )
    return space


def list_project_knowledge_roots(vault: VaultLayout) -> Iterable[Path]:
    """Yield candidate+knowledge directories for all scopes (used by indexer)."""
    yield vault.shared_knowledge
    yield vault.shared_candidates
    for pid in vault.known_project_ids():
        space = vault.project_space(pid)
        yield space.knowledge
        yield space.candidates


def find_scope_for_path(vault: VaultLayout, path: Path) -> Optional[dict]:
    """Identify which scope a path belongs to (``shared`` or ``project:<id>``).

    Returns a dict with ``scope`` (string) and ``bucket`` (sources / candidates /
    knowledge) on success, or ``None`` if the path is outside any known scope.
    """
    root = vault.root
    try:
        rel = path.resolve().relative_to(root)
    except ValueError:
        return None
    parts = rel.parts
    if not parts:
        return None
    if parts[0] == SHARED_DIR and len(parts) >= 2:
        bucket = _BUCKET_BY_DIR.get(parts[1])
        if bucket is None:
            return None
        return {"scope": "shared", "bucket": bucket}
    if parts[0] == PROJECTS_DIR and len(parts) >= 3:
        pid = parts[1]
        bucket = _BUCKET_BY_DIR.get(parts[2])
        if bucket is None:
            return None
        return {"scope": f"project:{pid}", "bucket": bucket, "project_id": pid}
    return None


_BUCKET_BY_DIR = {
    SOURCES_DIR: "sources",
    CANDIDATES_DIR: "candidates",
    KNOWLEDGE_DIR: "knowledge",
}


__all__ = [
    "SHARED_DIR",
    "PROJECTS_DIR",
    "SOURCES_DIR",
    "CANDIDATES_DIR",
    "KNOWLEDGE_DIR",
    "PROJECT_META",
    "VaultLayout",
    "ProjectSpace",
    "resolve_vault",
    "init_vault",
    "ensure_project_space",
    "list_project_knowledge_roots",
    "find_scope_for_path",
]
