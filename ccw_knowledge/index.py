"""In-memory knowledge index.

The index is rebuilt from disk on startup and on demand. It does not
persist to a separate file (avoids concurrency between index and
sources). The structure is:

- A flat list of ``KnowledgeDocument`` objects.
- A bag-of-words index per document (tokens -> doc id sets).
- A tag index and an alias index for exact lookups.

Trade-offs:
- No fuzzy ranking. We rely on field-level prioritisation: title > alias
  > tags > id > body. Ranking is a future extension point.
- No full-text scoring. ``Standard`` mode reads matched docs' bodies;
  ``Deep`` mode does a wider scan including sources.
"""

from __future__ import annotations

import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from . import errors as _err
from .knowledge import (
    KnowledgeDocument,
    VALID_CATEGORIES,
    VALID_STATUSES,
    read_document,
)
from .scope import ScopeRoots, ScopeSet
from .vault import (
    CANDIDATES_DIR,
    KNOWLEDGE_DIR,
    SOURCES_DIR,
    VaultLayout,
    list_project_knowledge_roots,
    resolve_vault,
)


WORD_RE = re.compile(r"[\wÀ-￿][\wÀ-￿-]{1,}")
# Lightweight English stoplist. Non-English is left intact.
_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "for", "is", "in", "on",
    "with", "as", "be", "this", "that", "by", "from",
}


class KnowledgeIndex:
    """In-memory index of knowledge and candidate documents.

    Build with :meth:`build` or :meth:`refresh`. The instance is single-
    threaded; rely on the process boundary for safety.
    """

    def __init__(self) -> None:
        self._docs: dict[str, KnowledgeDocument] = {}
        self._by_title_token: dict[str, set[str]] = defaultdict(set)
        self._by_tag: dict[str, set[str]] = defaultdict(set)
        self._by_alias: dict[str, set[str]] = defaultdict(set)
        self._by_id: dict[str, str] = {}
        self._paths: dict[str, Path] = {}
        # Track mtimes per path for refresh().
        self._mtimes: dict[str, float] = {}

    @property
    def all_ids(self) -> List[str]:
        return list(self._docs.keys())

    def get(self, doc_id: str) -> Optional[KnowledgeDocument]:
        return self._docs.get(doc_id)

    def all_documents(self) -> Iterable[KnowledgeDocument]:
        return list(self._docs.values())

    # ------------------------------------------------------------------
    # Build / refresh
    # ------------------------------------------------------------------

    @classmethod
    def build(
        cls,
        vault: VaultLayout,
        scopes: ScopeSet,
        roots: ScopeRoots,
        include_sources: bool = False,
    ) -> "KnowledgeIndex":
        idx = cls()
        idx._ingest(vault, scopes, roots, include_sources=include_sources)
        return idx

    def refresh(
        self,
        vault: VaultLayout,
        scopes: ScopeSet,
        roots: ScopeRoots,
        include_sources: bool = False,
    ) -> None:
        self._ingest(vault, scopes, roots, include_sources=include_sources)

    def _ingest(
        self,
        vault: VaultLayout,
        scopes: ScopeSet,
        roots: ScopeRoots,
        include_sources: bool,
    ) -> None:
        self._docs.clear()
        self._by_title_token.clear()
        self._by_tag.clear()
        self._by_alias.clear()
        self._by_id.clear()
        self._paths.clear()
        self._mtimes.clear()

        directories: list[Path] = []
        for scope in scopes.scopes:
            if scope not in roots.buckets:
                continue
            bucket_dirs = roots.buckets[scope]
            for bucket_name, base in bucket_dirs.items():
                if bucket_name == SOURCES_DIR and not include_sources:
                    continue
                directories.append(base)

        for base in sorted(set(directories)):
            if not base.exists():
                continue
            for path in sorted(base.rglob("*.md")):
                if path.name == "_meta.json" or path.name.startswith("."):
                    continue
                try:
                    doc = read_document(path)
                except _err.KnowledgeError:
                    # Skip unreadable docs during indexing; audit picks them up.
                    continue
                self._register(doc)

    def _register(self, doc: KnowledgeDocument) -> None:
        # Use a synthetic key: id is the primary, but the index also
        # de-duplicates by absolute path.
        key = doc.id or str(doc.path.resolve())
        self._docs[key] = doc
        self._by_id[doc.id] = key
        self._paths[key] = doc.path

        # Title tokens.
        for tok in _tokenise(doc.title):
            self._by_title_token[tok].add(key)

        # Tags exact.
        for tag in doc.tags:
            t = tag.lower()
            self._by_tag[t].add(key)

        # Aliases exact.
        for alias in doc.aliases:
            self._by_alias[alias.lower()].add(key)
        # Title also contributes as alias.
        self._by_alias[doc.title.lower()].add(key)

        try:
            self._mtimes[key] = doc.path.stat().st_mtime
        except OSError:
            pass

    def lookup_by_id(self, doc_id: str) -> Optional[KnowledgeDocument]:
        key = self._by_id.get(doc_id)
        if key is None:
            return None
        return self._docs.get(key)

    def lookup_by_title(self, title: str) -> List[KnowledgeDocument]:
        tokens = _tokenise(title)
        if not tokens:
            return []
        matched: set[str] = set()
        first = True
        for t in tokens:
            bucket = self._by_title_token.get(t, set())
            if first:
                matched = set(bucket)
                first = False
            else:
                matched &= bucket
            if not matched:
                # Fallback: OR for partial matches (rare).
                matched.update(bucket)
        return [self._docs[k] for k in matched]

    def lookup_by_tag(self, tag: str) -> List[KnowledgeDocument]:
        return [self._docs[k] for k in self._by_tag.get(tag.lower(), set())]

    def lookup_by_alias(self, alias: str) -> List[KnowledgeDocument]:
        return [self._docs[k] for k in self._by_alias.get(alias.lower(), set())]

    # ------------------------------------------------------------------
    # Generic scoring
    # ------------------------------------------------------------------

    def search_tokens(self, query: str, limit: int = 50) -> List[Tuple[str, int]]:
        """Return ``(doc_key, score)`` pairs sorted by descending score.

        Scoring weights:
        - title token match: 5
        - alias exact: 5
        - tag exact: 4
        - id substring: 3
        - body token hit (handled in search.py via per-doc scan)
        """
        query_tokens = _tokenise(query)
        if not query_tokens:
            return []
        scores: dict[str, int] = defaultdict(int)
        # Title
        for tok in query_tokens:
            for key in self._by_title_token.get(tok, set()):
                scores[key] += 5
        # Alias exact
        if query.lower() in self._by_alias:
            for key in self._by_alias[query.lower()]:
                scores[key] += 5
        # Tag exact
        if query.lower() in self._by_tag:
            for key in self._by_tag[query.lower()]:
                scores[key] += 4
        # Id substring (cheap fallback)
        for key, doc in self._docs.items():
            for tok in query_tokens:
                if tok in doc.id.lower():
                    scores[key] += 3
                    break
        # Body (token hit)
        for key, doc in self._docs.items():
            body_tokens = _tokenise(doc.body) if doc.body else []
            body_token_set = set(body_tokens)
            for tok in query_tokens:
                if tok in body_token_set:
                    scores[key] += 1
        # Apply simple ordering: prefer reviewed, then confidence, then score.
        ranked = sorted(
            scores.items(),
            key=lambda kv: (
                -kv[1],
                _status_rank(self._docs[kv[0]].status),
                -_confidence_rank(self._docs[kv[0]]),
            ),
        )
        return ranked[:limit]

    def search_by_candidate(self, candidate: dict) -> List[KnowledgeDocument]:
        """Lookup documents that might satisfy a candidate merge.

        Heuristic:
        - Same id-slug prefix.
        - Any shared tags.
        - Title contains candidate title (or vice-versa).
        """
        title = candidate.get("title", "")
        ctags = {str(t).lower() for t in candidate.get("tags", [])}
        cslug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        candidates: set[str] = set()
        # Alias/title hits.
        candidates.update(self.lookup_by_title(title) and [d.id for d in self.lookup_by_title(title)])
        # Tag overlaps.
        for t in ctags:
            candidates.update(d.id for d in self.lookup_by_tag(t))
        # Slug prefix.
        for doc in self._docs.values():
            if cslug and cslug in doc.id.lower():
                candidates.add(doc.id)
            elif cslug and doc.title and cslug in re.sub(
                r"[^a-z0-9]+", "-", doc.title.lower()
            ):
                candidates.add(doc.id)
        return [self._docs[i] for i in candidates if i in self._docs]


def _tokenise(text: str) -> List[str]:
    out: List[str] = []
    if not text:
        return out
    for raw in WORD_RE.findall(text.lower()):
        if raw in _STOPWORDS:
            continue
        if len(raw) <= 1:
            continue
        out.append(raw)
    return out


def _status_rank(status: str) -> int:
    order = {"reviewed": 0, "candidate": 1, "stale": 2, "superseded": 3}
    return order.get(status, 9)


def _confidence_rank(doc: KnowledgeDocument) -> int:
    order = {"high": 3, "medium": 2, "low": 1}
    return order.get(doc.confidence, 0)


__all__ = [
    "KnowledgeIndex",
]
