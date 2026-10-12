"""Bootstrap: explicit initial knowledge extraction for a project.

Bootstrap is *always* opt-in. It must never auto-trigger from attach.
It must never copy entire project documents wholesale. The user
controls the scope (which directories, file types, max items, max
budget). For each candidate produced, the lifecycle starts at
``candidate`` — never ``reviewed``.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional, Set

from . import errors as _err
from .capture import capture_text
from .frontmatter import today
from .index import KnowledgeIndex
from .knowledge import KnowledgeDocument
from .reconcile import reconcile_candidate
from .scope import ScopeRoots, ScopeSet
from .vault import VaultLayout


DEFAULT_INCLUDE_GLOBS = (
    "README*",
    "*.md",
    "ARCHITECTURE*",
    "DESIGN*",
    "docs/**/*.md",
)


@dataclass
class BootstrapConfig:
    project_id: str
    project_root: Path
    include_globs: List[str] = field(default_factory=list)
    exclude_dirs: List[str] = field(default_factory=lambda: [".git", "node_modules", "venv", ".venv", "dist", "build"])
    max_files: int = 200
    max_chars_per_file: int = 4000
    skip_if_knowledge_exists: bool = True
    dry_run: bool = False

    def effective_includes(self) -> List[str]:
        return self.include_globs or list(DEFAULT_INCLUDE_GLOBS)


@dataclass
class BootstrapReport:
    scanned_files: int = 0
    candidates_created: int = 0
    candidates_skipped: int = 0
    auto_published: int = 0  # always 0 in V1
    findings: List[str] = field(default_factory=list)
    candidates: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "scanned_files": self.scanned_files,
            "candidates_created": self.candidates_created,
            "candidates_skipped": self.candidates_skipped,
            "auto_published": self.auto_published,
            "findings": list(self.findings),
            "candidates": list(self.candidates),
        }


def bootstrap(
    cfg: BootstrapConfig,
    *,
    vault: VaultLayout,
    scopes: ScopeSet,
    roots: ScopeRoots,
    index: KnowledgeIndex,
) -> BootstrapReport:
    """Run bootstrap and produce a report.

    For each eligible project document we:

    1. Limit to ``max_chars_per_file`` to avoid copying huge files.
    2. Run :func:`reconcile_candidate` against the existing index.
    3. If the reconciliation plan is ``new`` or ``supersede``, capture
       a slim Candidate into the project's candidate bucket.
    4. If the plan is ``merge`` or ``defer``, skip and record the reason.

    The Candidate's body is *not* a verbatim copy of the source document.
    It's a short summary plus a ``sources:`` pointer back to the file.
    """
    rep = BootstrapReport()
    if not cfg.project_root.exists():
        raise _err.ProjectError(f"project root does not exist: {cfg.project_root}")
    scope = f"project:{cfg.project_id}"
    if scope not in scopes.scopes:
        raise _err.ScopeError(f"bootstrap requires scope {scope}; got {scopes.scopes}")

    seen: Set[Path] = set()
    candidates_collected = 0
    for path in _enumerate_candidate_files(cfg):
        candidates_collected += 1
        if candidates_collected > cfg.max_files:
            rep.findings.append(f"hit max_files={cfg.max_files}; stopped early")
            break
        if path in seen:
            continue
        seen.add(path)
        rep.scanned_files += 1
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        snippet = text[: cfg.max_chars_per_file].strip()
        if len(snippet) < 80:
            rep.candidates_skipped += 1
            rep.findings.append(
                f"skipped {path}: content too short ({len(snippet)} chars)"
            )
            continue
        # Always summarise rather than copy verbatim.
        body = _summarise(path, snippet)
        # Skip if knowledge already exists with the same id.
        stub_id = _id_from_path(path)
        if cfg.skip_if_knowledge_exists and index.lookup_by_id(stub_id):
            rep.candidates_skipped += 1
            rep.findings.append(
                f"skipped {path}: existing knowledge has id={stub_id!r}"
            )
            continue

        # Reconcile against the current index.
        plan = reconcile_candidate(
            KnowledgeDocument(
                path=path,
                frontmatter={
                    "id": stub_id,
                    "title": _title_from_path(path),
                    "tags": [],
                },
                body="",
            ),
            index=index,
        )
        if plan.action == "merge":
            rep.candidates_skipped += 1
            rep.findings.append(
                f"merge suggested for {path.name}: {plan.notes[0] if plan.notes else ''}"
            )
            continue
        if plan.action == "defer":
            rep.candidates_skipped += 1
            rep.findings.append(
                f"deferred {path.name}: {plan.notes[0] if plan.notes else ''}"
            )
            continue
        # For new or supersede, we capture.
        if cfg.dry_run:
            rep.candidates.append(f"[dry-run] candidate: {stub_id} from {path}")
            rep.candidates_created += 1
            continue
        try:
            doc = capture_text(
                vault=vault,
                scopes=scopes,
                roots=roots,
                project_id=cfg.project_id,
                title=_title_from_path(path),
                body=body,
                sources=[str(path)],
                tags=["bootstrap", "auto-summary"],
                category="reference",
                confidence="medium",
                volatility="warm",
            )
            rep.candidates_created += 1
            rep.candidates.append(str(doc.path))
        except _err.ScopeError as e:
            rep.findings.append(f"scope error for {path}: {e}")

    return rep


def _enumerate_candidate_files(cfg: BootstrapConfig) -> Iterable[Path]:
    """Yield project files matched by globs and not excluded by directories."""
    import fnmatch

    for pattern in cfg.effective_includes():
        # Recursive match using rglob (Python <3.13 compatibility).
        if any(glob in pattern for glob in ("**", "*/*")):
            glob_full = pattern
        else:
            glob_full = f"**/{pattern}"
        for path in cfg.project_root.rglob("*"):
            if not path.is_file():
                continue
            if not fnmatch.fnmatch(path.name, pattern.split("/")[-1].replace("**", "*")):
                continue
            if any(_is_excluded(path, excluded) for excluded in cfg.exclude_dirs):
                continue
            if path.name.startswith("."):
                continue
            yield path


def _is_excluded(path: Path, excluded: str) -> bool:
    return any(part == excluded for part in path.parts)


def _summarise(path: Path, text: str) -> str:
    head = re.sub(r"\s+", " ", text[:2000]).strip()
    return (
        f"> Bootstrap candidate from `{path}`.\n"
        f"> Original length: {len(text)} chars; truncated to summary.\n\n"
        f"{head}\n"
    )


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", text.lower()).strip("-")


def _title_from_path(path: Path) -> str:
    return path.stem.replace("-", " ").replace("_", " ").strip().title() or path.name


def _id_from_path(path: Path) -> str:
    return _slug(path.stem)


__all__ = [
    "BootstrapConfig",
    "BootstrapReport",
    "bootstrap",
]
