"""Domain-specific exceptions for ccw-knowledge.

All exceptions are designed to be safe to surface in CLI output and to
agent-facing structured responses (exit code 2 for blocking errors so
that hooks can recognise them).
"""

from __future__ import annotations


class CCWError(Exception):
    """Base class for all ccw-knowledge errors."""

    exit_code = 1


class ConfigError(CCWError):
    """Raised when configuration is missing, malformed, or inconsistent."""

    exit_code = 2


class VaultError(CCWError):
    """Raised for vault-level structural problems."""

    exit_code = 2


class ScopeError(CCWError):
    """Raised when an operation targets a path outside the registered scopes.

    This is an instruction-level boundary, NOT an OS-level sandbox. Callers
    are responsible for combining this with filesystem permissions.
    """

    exit_code = 2


class NotInitialized(CCWError):
    """Raised when ccw-knowledge has not been initialised on this machine."""

    exit_code = 2


class ProjectError(CCWError):
    """Raised when project operations fail (registration, attach, detach)."""

    exit_code = 2


class KnowledgeError(CCWError):
    """Raised when a knowledge document cannot be parsed, validated, or written."""

    exit_code = 2


class ConcurrencyError(CCWError):
    """Raised when a concurrent modification is detected and recovery is required."""

    exit_code = 2
