"""Knowledge capture.

Capture produces a Candidate. It refuses to bypass the review queue:

- It does not auto-publish (status stays ``candidate``).
- It records provenance (``sources:`` list) when given.
- It writes to the candidates/ bucket, never directly to knowledge/.
"""

from __future__ import annotations

import datetime
import os
import re
from pathlib import Path
from typing import List, Optional

from . import errors as _err
from .frontmatter import now_iso, today
from .knowledge import (
    KnowledgeDocument,
    VALID_CONFIDENCE,
    VALID_CATEGORIES,
    VALID_VOLATILITY,
    new_candidate,
    write_document_atomic,
)
from .scope import ScopeRoots, ScopeSet, resolve_target_path
from .vault import CANDIDATES_DIR, VaultLayout


def capture_text(
    *,
    vault: VaultLayout,
    scopes: ScopeSet,
    roots: ScopeRoots,
    project_id: str,
    title: str,
    body: str,
    sources: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
    category: str = "topic",
    confidence: str = "medium",
    volatility: str = "warm",
) -> KnowledgeDocument:
    """Capture free-form text into the project's candidate bucket."""
    if category not in VALID_CATEGORIES:
        raise _err.KnowledgeError(f"invalid category {category!r}")
    if confidence not in VALID_CONFIDENCE:
        raise _err.KnowledgeError(f"invalid confidence {confidence!r}")
    if volatility not in VALID_VOLATILITY:
        raise _err.KnowledgeError(f"invalid volatility {volatility!r}")
    if not title.strip():
        raise _err.KnowledgeError("title is required for capture")
    scope = f"project:{project_id}"
    if scope not in scopes.scopes:
        raise _err.ScopeError(f"capture requires scope {scope}, got {scopes.scopes}")

    doc = new_candidate(
        title=title,
        body=body,
        sources=sources or [],
        scope="project",
        project_id=project_id,
        tags=tags or [],
        category=category,
        confidence=confidence,
        volatility=volatility,
    )
    slug = _slugify(title)
    target_path = resolve_target_path(
        roots, scope, CANDIDATES_DIR, f"{slug}-{_today_safe()}.md"
    )
    target_path.parent.mkdir(parents=True, exist_ok=True)
    write_document_atomic(doc, target_path)
    doc.path = target_path
    return doc


def capture_file(
    *,
    vault: VaultLayout,
    scopes: ScopeSet,
    roots: ScopeRoots,
    project_id: str,
    source_path: Path,
    title: Optional[str] = None,
    tags: Optional[List[str]] = None,
    category: str = "reference",
    confidence: str = "medium",
    volatility: str = "warm",
) -> KnowledgeDocument:
    """Read a local Markdown file, wrap into a Candidate, store under candidates/.

    If the source file is large we keep it under ``sources/`` and write a
    slimmer Candidate pointing at it via ``sources:``.
    """
    if not source_path.exists() or not source_path.is_file():
        raise _err.KnowledgeError(f"capture source not found: {source_path}")
    text = source_path.read_text(encoding="utf-8", errors="ignore")
    body = text.strip()
    title = title or source_path.stem
    scope = f"project:{project_id}"
    if scope not in scopes.scopes:
        raise _err.ScopeError(f"capture requires scope {scope}, got {scopes.scopes}")

    # Decide whether to copy file or reference it.
    src_in_vault = _safe_within(vault, source_path)
    sources: List[str] = []
    if src_in_vault:
        sources.append(str(source_path))
        candidate_body = body
    else:
        # Copy into sources/ for provenance.
        target_sources = resolve_target_path(
            roots, scope, "sources", f"{source_path.name}"
        )
        if target_sources != source_path:
            target_sources.parent.mkdir(parents=True, exist_ok=True)
            if target_sources.exists():
                # Avoid overwriting; append a numeric suffix.
                target_sources = _unique_path(target_sources)
            target_sources.write_text(body, encoding="utf-8")
        sources.append(str(target_sources))
        candidate_body = body

    return capture_text(
        vault=vault,
        scopes=scopes,
        roots=roots,
        project_id=project_id,
        title=title,
        body=candidate_body,
        sources=sources,
        tags=tags,
        category=category,
        confidence=confidence,
        volatility=volatility,
    )


def _safe_within(vault: VaultLayout, path: Path) -> bool:
    try:
        path.resolve().relative_to(vault.root.resolve())
        return True
    except ValueError:
        return False


def _unique_path(path: Path) -> Path:
    """Append numeric suffix until the path does not exist."""
    base = path
    stem, suffix = path.stem, path.suffix
    i = 1
    while path.exists():
        path = base.with_name(f"{stem}-{i}{suffix}")
        i += 1
        if i > 1000:
            raise _err.KnowledgeError(f"too many copies for {base}")
    return path


def _slugify(value: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9-]+", "-", value).strip("-").lower()
    return s or "candidate"


def _today_safe() -> str:
    """Like ``today()`` but filesystem-safe (it already is)."""
    return datetime.date.today().isoformat()


__all__ = [
    "capture_text",
    "capture_file",
]
