"""Knowledge reconciliation.

The "Update first, create second" principle. Before a candidate is
written (or, if the caller forgot, before it is committed to the
published bucket) we check whether existing knowledge already covers
the same fact. If so, we return a *reconciliation plan*:

- MERGE: append the candidate's new evidence into the existing doc and
  bump ``updated``.
- SUPERSEDE: mark the existing doc as ``superseded`` with a pointer to
  the new doc; the new doc inherits the lineage.
- NEW: no overlap; create as planned.

The reconciliation function is *advisory only*. It returns the plan;
the caller decides what to do.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional

from .index import KnowledgeIndex
from .knowledge import (
    KnowledgeDocument,
    VALID_STATUSES,
    new_candidate,
)


@dataclass
class ReconciliationPlan:
    """The outcome of comparing a candidate to existing knowledge."""

    action: str  # 'new' | 'merge' | 'supersede' | 'defer'
    matched_documents: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "matched_documents": self.matched_documents,
            "notes": self.notes,
        }


def reconcile_candidate(
    candidate: KnowledgeDocument,
    *,
    index: KnowledgeIndex,
    threshold: float = 0.4,
) -> ReconciliationPlan:
    """Return a reconciliation plan for the candidate.

    Heuristics (kept simple and conservative):

    1. If a reviewed doc has the same id-slug prefix and overlapping
       tags, action = merge.
    2. If two or more reviewed docs share at least 50% of the candidate's
       tags, the candidate may be a duplicate — defer (return 'defer').
    3. If a reviewed doc's title is *almost* identical (slug form equal)
       and confidence >= medium, action = supersede.
    4. Otherwise, action = new.
    """
    candidates = index.search_by_candidate(candidate.frontmatter)
    if not candidates:
        return ReconciliationPlan(action="new", notes=["no overlap detected"])

    title_slug = _slug_of(candidate.title)
    aliases = {a.lower() for a in candidate.aliases}
    tags = {t.lower() for t in candidate.tags}

    # Same slug and same scope — strongest signal.
    near_duplicates: List[KnowledgeDocument] = []
    for d in candidates:
        dslug = _slug_of(d.title)
        if dslug == title_slug:
            near_duplicates.append(d)
            continue
        d_aliases = {a.lower() for a in d.aliases}
        if aliases & d_aliases:
            near_duplicates.append(d)
            continue

    high_overlap: List[KnowledgeDocument] = []
    if tags:
        for d in candidates:
            d_tags = {t.lower() for t in d.tags}
            share = len(tags & d_tags) / max(1, len(tags | d_tags))
            if share >= 0.5:
                high_overlap.append(d)

    if near_duplicates:
        same_scope = [d for d in near_duplicates if d.status != "superseded"]
        if same_scope and same_scope[0].status in ("reviewed", "candidate"):
            target = same_scope[0]
            if target.status == "reviewed":
                return ReconciliationPlan(
                    action="merge",
                    matched_documents=[target.id],
                    notes=[
                        f"near-duplicate of reviewed knowledge {target.id}; "
                        "consider merging instead of creating new."
                    ],
                )
            return ReconciliationPlan(
                action="merge",
                matched_documents=[target.id],
                notes=[
                    f"near-duplicate of existing candidate {target.id}; "
                    "merge into the older one rather than publish separately."
                ],
            )
        return ReconciliationPlan(
            action="supersede",
            matched_documents=[d.id for d in near_duplicates[:3]],
            notes=[
                "near-duplicate exists but is superseded/stale; this candidate may "
                "become the new canonical version."
            ],
        )

    if len(high_overlap) >= 2:
        return ReconciliationPlan(
            action="defer",
            matched_documents=[d.id for d in high_overlap[:5]],
            notes=[
                f"{len(high_overlap)} overlapping docs share significant tags; "
                "manual decision required to merge vs. fresh entry."
            ],
        )

    if candidates:
        # Some matched docs but no strong signal — note them but treat as new.
        return ReconciliationPlan(
            action="new",
            matched_documents=[d.id for d in candidates[:5]],
            notes=[
                f"loose overlap with {len(candidates)} documents; tagging helps disambiguate."
            ],
        )

    return ReconciliationPlan(action="new", notes=["no overlap detected"])


def _slug_of(text: str) -> str:
    import re as _re
    return _re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


__all__ = [
    "ReconciliationPlan",
    "reconcile_candidate",
]
