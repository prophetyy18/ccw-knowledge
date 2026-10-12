"""Permission/scope enforcement.

This is *logical* permission. The CLI rejects writes or reads of paths
outside the requested scopes. It cannot, on its own, prevent a process
with raw filesystem access from reading every file under the Vault. The
README documents this honestly.

.. warning::

   Logical scope != OS sandbox. See ARCHITECTURE.md §6.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from .errors import ScopeError
from .pathutil import is_within, strictly_within
from .vault import (
    KNOWLEDGE_DIR,
    CANDIDATES_DIR,
    SOURCES_DIR,
    VaultLayout,
)


@dataclass(frozen=True)
class ScopeSet:
    """A non-empty collection of allowed scopes.

    Each scope is one of:
    - ``"shared"``
    - ``"project:<id>"``
    """

    scopes: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.scopes:
            raise ValueError("ScopeSet requires at least one scope")
        for s in self.scopes:
            if s != "shared" and not s.startswith("project:"):
                raise ValueError(f"invalid scope: {s!r}")
            if s.startswith("project:") and len(s) <= len("project:"):
                raise ValueError(f"invalid scope: {s!r}")

    @classmethod
    def parse(cls, raw: Iterable[str] | str) -> "ScopeSet":
        if isinstance(raw, str):
            raw = [s.strip() for s in raw.split(",") if s.strip()]
        items = list(raw)
        if not items:
            return cls(("project:default",))  # never empty; caller can override
        return cls(tuple(items))

    def contains(self, scope: str) -> bool:
        return scope in self.scopes or (
            scope.startswith("project:") and scope in self.scopes
        )

    def to_list(self) -> list[str]:
        return list(self.scopes)


@dataclass(frozen=True)
class ScopeRoots:
    """Concrete directories each scope is allowed to read/write."""

    # Map: scope-name -> bucket -> absolute Path.
    buckets: dict[str, dict[str, Path]]

    @classmethod
    def from_vault(cls, vault: VaultLayout, scopes: ScopeSet) -> "ScopeRoots":
        out: dict[str, dict[str, Path]] = {}
        for scope in scopes.scopes:
            if scope == "shared":
                out[scope] = {
                    SOURCES_DIR: vault.shared_sources,
                    CANDIDATES_DIR: vault.shared_candidates,
                    KNOWLEDGE_DIR: vault.shared_knowledge,
                }
            elif scope.startswith("project:"):
                pid = scope[len("project:"):]
                space = vault.project_space(pid)
                out[scope] = {
                    SOURCES_DIR: space.sources,
                    CANDIDATES_DIR: space.candidates,
                    KNOWLEDGE_DIR: space.knowledge,
                }
        return cls(buckets=out)


def resolve_target_path(
    roots: ScopeRoots, scope: str, bucket: str, rel_path: str
) -> Path:
    """Resolve ``rel_path`` under the (scope, bucket) root with traversal rejection.

    Raises :class:`ScopeError` if the path escapes its bucket root.
    """
    if scope not in roots.buckets:
        raise ScopeError(f"scope {scope!r} not in registered scopes")
    bucket_dirs = roots.buckets[scope]
    if bucket not in bucket_dirs:
        raise ScopeError(f"bucket {bucket!r} not in scope {scope!r}")
    base = bucket_dirs[bucket]
    rel = rel_path.strip().lstrip("/\\")
    if rel == "":
        raise ScopeError("empty path")
    # Reject ``..`` and absolute-prefix escapes before joining.
    parts = [p for p in rel.replace("\\", "/").split("/") if p not in ("", ".")]
    if ".." in parts:
        raise ScopeError(f"path traversal not allowed: {rel_path!r}")
    candidate = base.joinpath(*parts)
    candidate = candidate.resolve()
    if not strictly_within(candidate, base):
        raise ScopeError(f"path escapes its bucket: {rel_path!r}")
    return candidate


def list_known_buckets() -> tuple[str, ...]:
    return (SOURCES_DIR, CANDIDATES_DIR, KNOWLEDGE_DIR)


__all__ = [
    "ScopeSet",
    "ScopeRoots",
    "resolve_target_path",
    "list_known_buckets",
]
