"""Knowledge retrieval.

Three depths: ``quick``, ``standard``, ``deep``.

The structure of this module deliberately keeps "evidence" separate from
"opinion": matches are evidence, the agent/CLI consumer is responsible
for forming a conclusion. We never claim "this proves X" — only that
"this document contains X, with status S, confidence C, sources [...]".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from . import errors as _err
from .index import KnowledgeIndex
from .knowledge import KnowledgeDocument
from .scope import ScopeRoots, ScopeSet
from .vault import (
    SOURCES_DIR,
    VaultLayout,
    list_project_knowledge_roots,
)


VALID_DEPTHS = ("quick", "standard", "deep")


@dataclass
class Match:
    """A single knowledge hit."""

    doc: KnowledgeDocument
    score: int
    excerpt: str = ""
    matched_fields: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.doc.id,
            "title": self.doc.title,
            "status": self.doc.status,
            "confidence": self.doc.confidence,
            "category": self.doc.category,
            "scope": str(self.doc.frontmatter.get("scope") or ""),
            "path": str(self.doc.path),
            "score": self.score,
            "excerpt": self.excerpt,
            "matched_fields": self.matched_fields,
            "tags": self.doc.tags,
            "sources": self.doc.sources,
            "aliases": self.doc.aliases,
            "summary": self.doc.short_summary,
        }


@dataclass
class EvidencePack:
    """Structured, machine-readable response to a search request."""

    query: str
    depth: str
    scope: List[str]
    matches: List[Match] = field(default_factory=list)
    supporting_evidence: List[str] = field(default_factory=list)
    conflicting_evidence: List[str] = field(default_factory=list)
    unknowns: List[str] = field(default_factory=list)
    search_limits: dict = field(default_factory=dict)
    truncated: bool = False

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "depth": self.depth,
            "scope": self.scope,
            "matches": [m.to_dict() for m in self.matches],
            "supporting_evidence": self.supporting_evidence,
            "conflicting_evidence": self.conflicting_evidence,
            "unknowns": self.unknowns,
            "search_limits": self.search_limits,
            "truncated": self.truncated,
        }


def search(
    query: str,
    *,
    index: KnowledgeIndex,
    vault: VaultLayout,
    scopes: ScopeSet,
    roots: ScopeRoots,
    depth: str = "standard",
    context_budget: int = 2000,
    limit: int = 25,
    include_sources: bool = False,
    source_paths: Optional[List[Path]] = None,
) -> EvidencePack:
    """Run a search at the requested depth.

    Budget handling: ``context_budget`` is in *characters* (we approximate
    one token ≈ four characters; the agent can convert if needed). Each
    match excerpt is shaped to a small slice; the total length of all
    excerpts is bounded by ``context_budget``.
    """
    if depth not in VALID_DEPTHS:
        raise _err.ConfigError(
            f"invalid depth {depth!r}; must be one of {VALID_DEPTHS}"
        )
    pack = EvidencePack(query=query, depth=depth, scope=scopes.to_list())
    if not query.strip():
        return pack

    ranked = index.search_tokens(query, limit=max(limit, 50))
    matches: List[Match] = []
    seen_ids: set[str] = set()
    budget_used = 0

    for doc_key, score in ranked:
        doc = index.get(doc_key)
        if doc is None:
            continue
        if doc.id in seen_ids:
            continue
        seen_ids.add(doc.id)
        excerpt = _excerpt_for(doc, query)
        matched_fields = _matched_fields(doc, query)
        if depth == "quick":
            excerpt = ""
        elif depth == "standard":
            excerpt = excerpt[:280]
        # deep mode keeps longer snippets, up to 1200 chars.
        if depth == "deep":
            excerpt = excerpt[:1200]
        budget_used += len(excerpt) + 100  # rough overhead
        if budget_used > context_budget and matches:
            pack.truncated = True
            break
        matches.append(
            Match(doc=doc, score=score, excerpt=excerpt, matched_fields=matched_fields)
        )
        if len(matches) >= limit:
            pack.truncated = True
            break

    pack.matches = matches

    # Supporting evidence: trust the `sources:` field on each match.
    seen_sources: set[str] = set()
    for m in matches:
        for src in m.doc.sources:
            if src not in seen_sources:
                seen_sources.add(src)
                pack.supporting_evidence.append(str(_safe_join(vault, src)))
    # Conflicting evidence: collect status=stale or confidence=low markers.
    for m in matches:
        if m.doc.status == "stale":
            pack.conflicting_evidence.append(
                f"stale: {m.doc.id} ({m.doc.path})"
            )
    if depth == "deep":
        # Cross-check by inspecting project sources directly.
        try:
            cross_evidence = _cross_check_sources(query, vault, source_paths)
            pack.supporting_evidence.extend(
                [str(p) for p in cross_evidence if str(p) not in seen_sources]
            )
        except Exception:
            pack.unknowns.append("deep: source cross-check failed")

    pack.search_limits = {
        "budget_used_chars": budget_used,
        "scanned_documents": len(index.all_ids),
        "queries_run": 1,
        "depth": depth,
        "context_budget_chars": context_budget,
    }
    return pack


def _excerpt_for(doc: KnowledgeDocument, query: str, window: int = 200) -> str:
    body = doc.body or ""
    if not body:
        return ""
    # Find the first occurrence of any query word.
    tokens = [t for t in re.split(r"\s+", query.lower()) if t]
    lower_body = body.lower()
    pos = -1
    matched_token = ""
    for t in tokens:
        idx = lower_body.find(t)
        if idx >= 0 and (pos < 0 or idx < pos):
            pos = idx
            matched_token = t
    if pos < 0:
        return body[:280]
    start = max(0, pos - window // 2)
    end = min(len(body), pos + window // 2)
    snippet = body[start:end]
    if matched_token:
        return _highlight(snippet, matched_token)
    return snippet


def _highlight(text: str, token: str) -> str:
    pattern = re.compile(re.escape(token), re.IGNORECASE)
    # Use a simple prefix/suffix marker (no markdown so we don't break renderers).
    def _sub(m):
        return f"[{m.group(0)}]"

    out = pattern.sub(_sub, text)
    return out


def _matched_fields(doc: KnowledgeDocument, query: str) -> List[str]:
    fields: List[str] = []
    q = query.lower()
    tokens = [t for t in re.split(r"\s+", q) if t]
    if any(t in doc.title.lower() for t in tokens):
        fields.append("title")
    if q in [a.lower() for a in doc.aliases]:
        fields.append("alias")
    if any(t in [tg.lower() for tg in doc.tags] for t in tokens):
        fields.append("tag")
    if any(t in doc.id.lower() for t in tokens):
        fields.append("id")
    body_tokens = set(re.findall(r"[\wÀ-￿-]+", (doc.body or "").lower()))
    if any(t in body_tokens for t in tokens):
        fields.append("body")
    return fields


def _safe_join(vault: VaultLayout, src: str) -> Path:
    """Resolve a ``sources:`` entry to a Path inside the vault, falling
    back to a Path string if outside.

    ``sources:`` entries may be relative or use the project's space
    ``project:<id>/sources/<file>`` style. We don't enforce — we just
    join and report what we'd find.
    """
    p = Path(src)
    if p.is_absolute():
        return p
    return (vault.root / src).resolve()


def _cross_check_sources(
    query: str, vault: VaultLayout, paths: Optional[List[Path]]
) -> List[Path]:
    out: List[Path] = []
    if paths:
        roots = [Path(p) for p in paths if Path(p).exists()]
    else:
        roots: List[Path] = []
        for base in list_project_knowledge_roots(vault):
            if base.name == SOURCES_DIR or "/sources" in str(base):
                roots.append(base)
    tokens = {t for t in re.split(r"\s+", query.lower()) if len(t) > 2}
    for base in roots:
        if not base.exists():
            continue
        for p in base.rglob("*.md"):
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            lower = text.lower()
            if any(t in lower for t in tokens):
                out.append(p)
                if len(out) >= 25:
                    return out
    return out


def render_pack(pack: EvidencePack, *, mode: str = "text") -> str:
    """Render an evidence pack for human consumption."""
    lines: List[str] = []
    lines.append(f"# Knowledge Evidence Pack")
    lines.append("")
    lines.append(f"Query: {pack.query}")
    lines.append(f"Depth: {pack.depth}")
    lines.append(f"Scope: {', '.join(pack.scope)}")
    lines.append(f"Matches: {len(pack.matches)}{' (truncated)' if pack.truncated else ''}")
    lines.append("")
    if not pack.matches:
        lines.append("No knowledge matches found for this query in the permitted scopes.")
        lines.append("")
    for m in pack.matches:
        lines.append(
            f"## {m.doc.title}  ({m.doc.id})"
        )
        lines.append(
            f"- status={m.doc.status} confidence={m.doc.confidence} "
            f"category={m.doc.category} score={m.score}"
        )
        lines.append(f"- path: {m.doc.path}")
        if m.doc.aliases:
            lines.append(f"- aliases: {', '.join(m.doc.aliases)}")
        if m.doc.tags:
            lines.append(f"- tags: {', '.join(m.doc.tags)}")
        if m.matched_fields:
            lines.append(f"- matched fields: {', '.join(m.matched_fields)}")
        if pack.depth != "quick" and m.excerpt:
            lines.append("")
            lines.append("```")
            lines.append(m.excerpt)
            lines.append("```")
        lines.append("")
    if pack.supporting_evidence:
        lines.append("## Supporting evidence (raw sources)")
        for s in pack.supporting_evidence[:10]:
            lines.append(f"- {s}")
        lines.append("")
    if pack.conflicting_evidence:
        lines.append("## Conflicting evidence")
        for s in pack.conflicting_evidence[:10]:
            lines.append(f"- {s}")
        lines.append("")
    if pack.unknowns:
        lines.append("## Important unknowns")
        for s in pack.unknowns:
            lines.append(f"- {s}")
        lines.append("")
    lines.append("---")
    lines.append(f"Search limits: {pack.search_limits}")
    return "\n".join(lines)


__all__ = [
    "Match",
    "EvidencePack",
    "search",
    "render_pack",
    "VALID_DEPTHS",
]
