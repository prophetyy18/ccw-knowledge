"""Knowledge document model.

A knowledge document is a single Markdown file with a YAML frontmatter
header. The minimal required fields are documented in ARCHITECTURE.md
§2.5. This module is the source of truth for in-memory access: parsing,
validation, lifecycle state transitions, and atomic writes.
"""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from . import errors as _err
from .frontmatter import (
    FrontmatterError,
    ensure_required_keys,
    now_iso,
    parse,
    render,
    today,
)

VALID_STATUSES = ("candidate", "reviewed", "stale", "superseded")
VALID_CATEGORIES = ("concept", "topic", "reference")
VALID_VOLATILITY = ("hot", "warm", "cold")
VALID_CONFIDENCE = ("high", "medium", "low")

# Lifecycle transitions allowed through normal user/CLI commands.
ALLOWED_TRANSITIONS: dict[str, List[str]] = {
    "candidate": ["reviewed", "stale"],
    "reviewed": ["stale", "superseded"],
    "stale": ["reviewed"],
    "superseded": [],  # terminal; only kept for history
}


@dataclass
class KnowledgeDocument:
    """In-memory model of a single knowledge document."""

    path: Path
    frontmatter: dict
    body: str = ""

    @property
    def id(self) -> str:
        return str(self.frontmatter.get("id") or _slug_from_path(self.path))

    @property
    def title(self) -> str:
        return str(self.frontmatter.get("title") or self.path.stem)

    @property
    def status(self) -> str:
        return str(self.frontmatter.get("status") or "candidate")

    @property
    def category(self) -> str:
        return str(self.frontmatter.get("category") or "topic")

    @property
    def confidence(self) -> str:
        return str(self.frontmatter.get("confidence") or "medium")

    @property
    def volatility(self) -> str:
        return str(self.frontmatter.get("volatility") or "warm")

    @property
    def tags(self) -> List[str]:
        v = self.frontmatter.get("tags") or []
        return [str(x) for x in v]

    @property
    def aliases(self) -> List[str]:
        v = self.frontmatter.get("aliases") or []
        return [str(x) for x in v]

    @property
    def sources(self) -> List[str]:
        v = self.frontmatter.get("sources") or []
        return [str(x) for x in v]

    @property
    def supersedes(self) -> Optional[str]:
        v = self.frontmatter.get("supersedes")
        return str(v) if v else None

    @property
    def superseded_by(self) -> Optional[str]:
        v = self.frontmatter.get("superseded_by")
        return str(v) if v else None

    @property
    def created(self) -> str:
        return str(self.frontmatter.get("created") or today())

    @property
    def updated(self) -> str:
        return str(self.frontmatter.get("updated") or self.created)

    @property
    def short_summary(self) -> str:
        body = self.body or ""
        # First non-empty paragraph.
        for line in body.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("#"):
                continue
            if line.startswith("[[") or line.startswith("![") or line.startswith("[!["):
                continue
            return line[:280]
        return ""

    @property
    def display_id(self) -> str:
        return self.id

    def to_text(self) -> str:
        return render(self.frontmatter, self.body)

    def migration_allowed(self, target: str) -> bool:
        if target not in VALID_STATUSES:
            return False
        return target in ALLOWED_TRANSITIONS.get(self.status, [])


def read_document(path: Path) -> KnowledgeDocument:
    """Parse a knowledge Markdown file into a :class:`KnowledgeDocument`."""
    if not path.exists() or not path.is_file():
        raise _err.KnowledgeError(f"not a knowledge file: {path}")
    text = path.read_text(encoding="utf-8")
    try:
        fm, body = parse(text)
    except FrontmatterError as e:
        raise _err.KnowledgeError(f"bad frontmatter in {path}: {e}") from e
    doc = KnowledgeDocument(path=path, frontmatter=fm, body=body)
    _validate_lite(doc)
    return doc


def _validate_lite(doc: KnowledgeDocument) -> None:
    """Light-touch checks on read.

    Reading a knowledge document must be permissive: if a doc has a bad
    status or category, we surface that in audit later rather than
    refusing to open it. The only fatal read-time issue is a
    frontmatter that isn't a mapping.
    """
    fm = doc.frontmatter
    if not isinstance(fm, dict):
        raise _err.KnowledgeError(f"frontmatter is not an object in {doc.path}")


def new_candidate(
    *,
    title: str,
    body: str = "",
    sources: Optional[List[str]] = None,
    scope: str = "shared",
    project_id: Optional[str] = None,
    tags: Optional[List[str]] = None,
    category: str = "topic",
    confidence: str = "medium",
    volatility: str = "warm",
) -> KnowledgeDocument:
    """Construct a fresh Candidate document (not yet written to disk)."""
    fm: dict = {
        "id": _new_id(title),
        "title": title,
        "status": "candidate",
        "category": category,
        "confidence": confidence,
        "volatility": volatility,
        "sources": sources or [],
        "tags": tags or [],
        "aliases": [],
        "created": today(),
        "updated": today(),
        "scope": _compose_scope(scope, project_id),
    }
    return KnowledgeDocument(path=Path("(unsaved)"), frontmatter=fm, body=body or "")


def _compose_scope(scope: str, project_id: Optional[str]) -> str:
    if scope == "shared":
        return "shared"
    if project_id:
        return f"project:{project_id}"
    return scope


def _slug_from_path(path: Path) -> str:
    stem = path.stem
    stem = re.sub(r"[^a-zA-Z0-9-]+", "-", stem).strip("-").lower()
    return stem or "knowledge"


def _new_id(title: str) -> str:
    """Generate a stable-looking id: ``<slug>-<6 hex>``."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", title).strip("-").lower() or "knowledge"
    # Use the title to seed a short hash so two simultaneous writes of
    # different content get distinct IDs but the same content gets the
    # same ID (helps with reconciliation).
    digest = hashlib.sha1(title.encode("utf-8", errors="ignore")).hexdigest()[:6]
    return f"{slug}-{digest}"


def prepare_promotion(doc: KnowledgeDocument, *, target: str, reviewer: str) -> KnowledgeDocument:
    """Return a copy with `status` and reviewer metadata updated.

    This does not write to disk.
    """
    if target not in VALID_STATUSES:
        raise _err.KnowledgeError(f"invalid target status: {target!r}")
    if not doc.migration_allowed(target):
        raise _err.KnowledgeError(
            f"transition {doc.status!r} -> {target!r} not allowed for {doc.path}"
        )
    new_fm = dict(doc.frontmatter)
    new_fm["status"] = target
    new_fm["updated"] = today()
    new_fm["reviewed_by"] = reviewer
    new_fm["reviewed_at"] = now_iso()
    return KnowledgeDocument(path=doc.path, frontmatter=new_fm, body=doc.body)


def write_document_atomic(doc: KnowledgeDocument, target: Optional[Path] = None) -> Path:
    """Persist a document atomically.

    Writes to a temp file in the same directory, fsyncs, and replaces.
    """
    path = target or doc.path
    if str(path) == "(unsaved)":
        raise _err.KnowledgeError("refusing to write a document without a path")
    path.parent.mkdir(parents=True, exist_ok=True)
    content = doc.to_text()
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
    doc.path = path
    return path


__all__ = [
    "VALID_STATUSES",
    "VALID_CATEGORIES",
    "VALID_VOLATILITY",
    "VALID_CONFIDENCE",
    "ALLOWED_TRANSITIONS",
    "KnowledgeDocument",
    "read_document",
    "new_candidate",
    "prepare_promotion",
    "write_document_atomic",
]
