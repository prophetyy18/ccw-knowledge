"""Knowledge audit.

Health checks run without an LLM. They return *findings* (severity
graded) and a small set of safe auto-fix actions the user can invoke
with ``--fix``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional

from . import errors as _err
from .index import KnowledgeIndex
from .knowledge import (
    VALID_STATUSES,
    KnowledgeDocument,
    read_document,
    write_document_atomic,
)
from .scope import ScopeRoots, ScopeSet
from .vault import VaultLayout


@dataclass
class AuditFinding:
    severity: str  # 'critical' | 'warning' | 'suggestion'
    code: str
    message: str
    file: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "file": self.file,
        }


@dataclass
class AuditReport:
    findings: List[AuditFinding] = field(default_factory=list)
    auto_fixed: List[str] = field(default_factory=list)

    def add(self, finding: AuditFinding) -> None:
        self.findings.append(finding)

    def to_dict(self) -> dict:
        return {
            "findings": [f.to_dict() for f in self.findings],
            "auto_fixed": self.auto_fixed,
        }


_VOLATILITY_DAYS = {"hot": 30, "warm": 180, "cold": 730}


def audit(
    *,
    vault: VaultLayout,
    scopes: ScopeSet,
    roots: ScopeRoots,
    index: KnowledgeIndex,
    fix: bool = False,
    today: Optional[date] = None,
) -> AuditReport:
    today = today or date.today()
    rep = AuditReport()
    seen_ids: dict[str, List[Path]] = {}
    for doc in index.all_documents():
        if doc.id in seen_ids:
            seen_ids[doc.id].append(doc.path)
        else:
            seen_ids[doc.id] = [doc.path]

    for doc in index.all_documents():
        dups = seen_ids.get(doc.id, [])
        if len(dups) > 1:
            rep.add(AuditFinding(
                "critical", "duplicate-id",
                f"id {doc.id!r} used by {len(dups)} documents",
                file=str(doc.path),
            ))
        # Sources reference check (lightweight).
        for src in doc.sources:
            src_path = Path(src)
            if not src_path.is_absolute():
                src_path = vault.root / src
            if not src_path.exists():
                rep.add(AuditFinding(
                    "warning", "missing-source",
                    f"source path does not exist: {src}",
                    file=str(doc.path),
                ))
        # Status / staleness based on volatility.
        updated_at = _parse_date(doc.updated)
        days = (today - updated_at).days if updated_at else 0
        threshold = _VOLATILITY_DAYS.get(doc.volatility, 365)
        if doc.status == "reviewed" and days > threshold and updated_at is not None:
            rep.add(AuditFinding(
                "warning", "stale-by-volatility",
                f"reviewed for {days}d (volatility={doc.volatility}, "
                f"threshold={threshold}d)",
                file=str(doc.path),
            ))
        # Invalid status (defensive; should never happen).
        if doc.status not in VALID_STATUSES:
            rep.add(AuditFinding(
                "critical", "invalid-status",
                f"status {doc.status!r} not recognised",
                file=str(doc.path),
            ))
        # Empty body / very short body.
        body_len = len((doc.body or "").strip())
        if doc.status == "reviewed" and body_len < 80:
            rep.add(AuditFinding(
                "warning", "thin-body",
                f"reviewed doc body is suspiciously short ({body_len} chars)",
                file=str(doc.path),
            ))

    # Auto-fix: only safe moves are handled here. We do NOT change status
    # without explicit operator intent.
    if fix:
        for f in list(rep.findings):
            if f.code == "stale-by-volatility":
                # Auto-mark stale (a status flip; reversible).
                path = Path(f.file) if f.file else None
                if not path or not path.exists():
                    continue
                try:
                    doc = read_document(path)
                except _err.KnowledgeError:
                    continue
                if doc.status != "reviewed":
                    continue
                new_fm = dict(doc.frontmatter)
                new_fm["status"] = "stale"
                new_fm["updated"] = today.isoformat()
                write_document_atomic(KnowledgeDocument(
                    path=doc.path, frontmatter=new_fm, body=doc.body
                ))
                rep.auto_fixed.append(str(path))
                f.severity = "suggestion"  # mark as resolved

    return rep


def _parse_date(value: str) -> Optional[date]:
    if not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


__all__ = [
    "AuditFinding",
    "AuditReport",
    "audit",
]
