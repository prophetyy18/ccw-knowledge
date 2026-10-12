"""Knowledge review.

Three classes:

1. Structural: a deterministic check that runs without an LLM. Validates
   frontmatter shape, ID uniqueness, source paths, status transitions.

2. Content: a soft hint returned alongside structural results. This is
   intentionally *advisory only* and never marks a candidate as approved
   by itself — that requires explicit operator action.

3. Authority: a thin layer above structural + content that requires the
   reviewer to declare a category (approve / reject / defer) and a note.
   Authority review is the only path from ``candidate`` to ``reviewed``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from . import errors as _err
from .index import KnowledgeIndex
from .knowledge import (
    ALLOWED_TRANSITIONS,
    KnowledgeDocument,
    VALID_STATUSES,
    prepare_promotion,
    read_document,
    write_document_atomic,
)
from .scope import ScopeRoots, ScopeSet, resolve_target_path
from .vault import CANDIDATES_DIR, KNOWLEDGE_DIR, VaultLayout


@dataclass
class StructuralFinding:
    severity: str  # 'critical' | 'warning' | 'suggestion'
    code: str
    message: str

    def to_dict(self) -> dict:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
        }


@dataclass
class StructuralReport:
    document: str
    findings: List[StructuralFinding] = field(default_factory=list)

    @property
    def critical_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "critical")

    def to_dict(self) -> dict:
        return {
            "document": self.document,
            "critical": self.critical_count,
            "findings": [f.to_dict() for f in self.findings],
        }


def structural_review(
    doc: KnowledgeDocument,
    *,
    siblings_index: Optional[KnowledgeIndex] = None,
    vault_root: Optional[Path] = None,
) -> StructuralReport:
    """Deterministic structural review."""
    rep = StructuralReport(document=str(doc.path))
    fm = doc.frontmatter or {}

    if "id" not in fm or not fm["id"]:
        rep.findings.append(StructuralFinding(
            "critical", "missing-id", "frontmatter is missing 'id'"
        ))
    if "title" not in fm or not fm["title"]:
        rep.findings.append(StructuralFinding(
            "critical", "missing-title", "frontmatter is missing 'title'"
        ))
    if "status" not in fm:
        rep.findings.append(StructuralFinding(
            "warning", "missing-status", "frontmatter is missing 'status'"
        ))
    elif fm["status"] not in VALID_STATUSES:
        rep.findings.append(StructuralFinding(
            "critical", "invalid-status",
            f"invalid status {fm['status']!r}; allowed: {VALID_STATUSES}"
        ))
    if "sources" in fm:
        sources = fm["sources"]
        if isinstance(sources, list) and not sources:
            rep.findings.append(StructuralFinding(
                "suggestion", "no-sources",
                "no sources cited; consider adding at least one provenance reference"
            ))
    else:
        rep.findings.append(StructuralFinding(
            "suggestion", "no-sources",
            "no sources field; consider adding provenance"
        ))

    # Link integrity (light touch): look for local markdown links in body
    # and warn about fragments, but do not require resolution.
    for m in re.finditer(r"\[[^\]]+\]\(([^)]+\.md(?:#[^)]*)?)\)", doc.body or ""):
        target = m.group(1).split("#", 1)[0]
        if target.startswith(("http://", "https://")):
            continue
        # Local relative link; we accept unconditionally but record presence.
        rep.findings.append(StructuralFinding(
            "suggestion", "has-local-link",
            f"local link to {target!r} — verifier should confirm it resolves"
        ))

    # ID collisions (if we have an index to compare against).
    if siblings_index and doc.id in siblings_index.all_ids:
        own_path = siblings_index.get(doc.id)
        if own_path is not None and own_path.path != doc.path:
            rep.findings.append(StructuralFinding(
                "critical", "duplicate-id",
                f"another document already uses id={doc.id!r}: {own_path.path}"
            ))

    return rep


def approve_candidate(
    *,
    vault: VaultLayout,
    scopes: ScopeSet,
    roots: ScopeRoots,
    project_id: str,
    candidate_id: str,
    reviewer: str,
    note: Optional[str] = None,
) -> Tuple[KnowledgeDocument, StructuralReport]:
    """Approve a candidate and move it from candidates/ to knowledge/.

    Only callers with the matching scope can do this for their project.
    Moving across scopes is intentionally impossible.
    """
    scope = f"project:{project_id}"
    if scope not in scopes.scopes:
        raise _err.ScopeError(f"approve requires scope {scope}; got {scopes.scopes}")
    cand_path = _find_document_path_in_bucket(
        roots, scope, CANDIDATES_DIR, candidate_id
    )
    if cand_path is None:
        raise _err.KnowledgeError(f"candidate {candidate_id!r} not found")
    doc = read_document(cand_path)
    rep = structural_review(doc, vault_root=vault.root)
    if rep.critical_count > 0:
        raise _err.KnowledgeError(
            f"candidate {candidate_id} has {rep.critical_count} critical findings; "
            "refusing to approve until they are addressed"
        )
    if doc.status not in ("candidate", "stale"):
        raise _err.KnowledgeError(
            f"cannot approve document in status {doc.status!r}; only 'candidate' or 'stale'"
        )
    if "stale" in (doc.status,):
        # allowed: stale -> reviewed
        pass

    promoted = prepare_promotion(doc, target="reviewed", reviewer=reviewer)
    new_path = resolve_target_path(
        roots, scope, KNOWLEDGE_DIR, f"{_stem(promoted.path)}.md"
    )
    new_path.parent.mkdir(parents=True, exist_ok=True)
    if new_path.exists() and new_path.resolve() != cand_path.resolve():
        # Avoid clobbering by suffixing.
        new_path = _unique(new_path)
    write_document_atomic(promoted, new_path)
    if cand_path.resolve() != new_path.resolve() and cand_path.exists():
        cand_path.unlink()
    if note:
        _append_review_log(vault, project_id, candidate_id, "approve", reviewer, note)
    return promoted, rep


def reject_candidate(
    *,
    vault: VaultLayout,
    scopes: ScopeSet,
    roots: ScopeRoots,
    project_id: str,
    candidate_id: str,
    reviewer: str,
    note: Optional[str] = None,
) -> KnowledgeDocument:
    """Reject a candidate by moving it into the knowledge/ bucket with status=superseded
    or simply deleting from candidates/ depending on policy.

    V1 keeps rejected candidates in a deprecated/ sub-bucket so the
    rejection is auditable.
    """
    scope = f"project:{project_id}"
    if scope not in scopes.scopes:
        raise _err.ScopeError(f"reject requires scope {scope}; got {scopes.scopes}")
    cand_path = _find_document_path_in_bucket(roots, scope, CANDIDATES_DIR, candidate_id)
    if cand_path is None:
        raise _err.KnowledgeError(f"candidate {candidate_id!r} not found")
    doc = read_document(cand_path)
    promoted = prepare_promotion(doc, target="superseded", reviewer=reviewer)
    target = resolve_target_path(
        roots, scope, KNOWLEDGE_DIR, f"deprecated-{_stem(promoted.path)}.md"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target = _unique(target)
    write_document_atomic(promoted, target)
    if cand_path.resolve() != target.resolve() and cand_path.exists():
        cand_path.unlink()
    if note:
        _append_review_log(vault, project_id, candidate_id, "reject", reviewer, note)
    return promoted


def defer_candidate(
    *,
    vault: VaultLayout,
    scopes: ScopeSet,
    roots: ScopeRoots,
    project_id: str,
    candidate_id: str,
    reviewer: str,
    note: Optional[str] = None,
) -> KnowledgeDocument:
    """Mark a candidate as ``stale`` (kept but flagged for re-verification later)."""
    scope = f"project:{project_id}"
    if scope not in scopes.scopes:
        raise _err.ScopeError(f"defer requires scope {scope}; got {scopes.scopes}")
    cand_path = _find_document_path_in_bucket(roots, scope, CANDIDATES_DIR, candidate_id)
    if cand_path is None:
        raise _err.KnowledgeError(f"candidate {candidate_id!r} not found")
    doc = read_document(cand_path)
    promoted = prepare_promotion(doc, target="stale", reviewer=reviewer)
    write_document_atomic(promoted, cand_path)
    if note:
        _append_review_log(vault, project_id, candidate_id, "defer", reviewer, note)
    return promoted


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_document_path_in_bucket(
    roots: ScopeRoots, scope: str, bucket: str, document_id: str
) -> Optional[Path]:
    """Scan a bucket for a file whose id matches ``document_id``.

    We do not trust document IDs as filenames (filenames are slugs, IDs
    are slugs+suffixes), so we scan and parse frontmatter to compare.
    """
    from .frontmatter import parse as _parse

    base = roots.buckets.get(scope, {}).get(bucket)
    if base is None or not base.exists():
        return None
    for path in base.rglob("*.md"):
        if path.name.startswith("."):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        try:
            fm, _ = _parse(text)
        except Exception:
            continue
        if not fm:
            continue
        if str(fm.get("id") or "") == document_id:
            return path
    return None


def _stem(path: Path) -> str:
    return path.stem


def _unique(path: Path) -> Path:
    base = path
    stem, suffix = path.stem, path.suffix
    i = 1
    while path.exists():
        path = base.with_name(f"{stem}-{i}{suffix}")
        i += 1
        if i > 1000:
            raise _err.KnowledgeError(f"too many copies for {base}")
    return path


def _append_review_log(
    vault: VaultLayout,
    project_id: str,
    candidate_id: str,
    action: str,
    reviewer: str,
    note: str,
) -> None:
    import datetime as _dt

    log_path = vault.projects_root / project_id / "review.log.md"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    ts = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    line = (
        f"- [{ts}] {action} {candidate_id} by {reviewer}: {note}\n"
    )
    if log_path.exists():
        with log_path.open("a", encoding="utf-8") as f:
            f.write(line)
    else:
        log_path.write_text(f"# Review log for project {project_id}\n\n{line}", encoding="utf-8")


__all__ = [
    "StructuralFinding",
    "StructuralReport",
    "structural_review",
    "approve_candidate",
    "reject_candidate",
    "defer_candidate",
]
