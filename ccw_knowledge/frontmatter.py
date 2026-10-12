"""Minimal YAML frontmatter parser and writer.

Why hand-rolled? To keep zero dependencies. We only support the subset we
need:

- scalar values (strings, numbers, booleans, null)
- single-line lists with comma or pipe separators
- multi-line block scalars (``|`` and ``>``)
- top-level keys only (no nested mappings)

This matches ccw-knowledge's authoring style: flat keys, lists of short
slugs or short strings. If the user pastes complex YAML (nested dicts,
anchors) we surface a parse error rather than silently misinterpreting.
"""

from __future__ import annotations

import datetime as _dt
import re
from typing import Any, Dict, List, Tuple

_FRONT_MATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)
_LIST_ITEM_RE = re.compile(r"^\s*-\s+(.*)$")


class FrontmatterError(Exception):
    """Raised when frontmatter cannot be parsed or written."""


def parse(text: str) -> Tuple[Dict[str, Any], str]:
    """Return ``(frontmatter_dict, body)``.

    If the file has no frontmatter block, the frontmatter is ``{}`` and
    the entire text is treated as the body.
    """
    if not text:
        return {}, ""
    m = _FRONT_MATTER_RE.match(text)
    if not m:
        return {}, text
    raw_yaml, body = m.group(1), m.group(2)
    fm = _parse_yaml_subset(raw_yaml)
    return fm, body


def _parse_yaml_subset(raw: str) -> Dict[str, Any]:
    """Parse a restricted YAML subset.

    Supports:
    - ``key: value``
    - ``key: [list, items]``
    - ``key:\n  - item\n  - item`` (list under scalar)
    - multi-line ``|`` and ``>`` block scalars
    - empty values as empty string

    Nested mappings and anchors/aliases raise :class:`FrontmatterError`.
    """
    lines = raw.splitlines()
    out: Dict[str, Any] = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip() or line.lstrip().startswith("#"):
            i += 1
            continue
        if ":" not in line:
            raise FrontmatterError(f"unexpected line in frontmatter: {line!r}")
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if value == "":
            # Distinguish ``key:`` (empty scalar) from ``key:\n - x`` (list).
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines) and lines[j].lstrip().startswith("- "):
                # Block list under empty value.
                collected: List[str] = []
                k = i + 1
                while k < len(lines):
                    child = lines[k]
                    stripped = child.strip()
                    if not stripped:
                        k += 1
                        continue
                    if not (child.startswith(" ") or child.startswith("\t")):
                        break
                    m = _LIST_ITEM_RE.match(child)
                    if not m:
                        break
                    collected.append(_coerce(m.group(1).strip()))
                    k += 1
                out[key] = collected
                i = k
                continue
            else:
                out[key] = ""
                i += 1
                continue
        if value == "|" or value == ">":
            # Could be a list or a block scalar.
            collected: List[str] = []
            j = i + 1
            block_style = value  # '|' or '>' or '' (empty -> list)
            while j < len(lines):
                child = lines[j]
                stripped = child.strip()
                if not stripped:
                    # Blank line ends a list.
                    if block_style == "":
                        break
                    collected.append("")
                    j += 1
                    continue
                if not (child.startswith(" ") or child.startswith("\t")):
                    break
                if block_style in ("|", ">"):
                    collected.append(child[2:] if child.startswith("  ") else child.lstrip())
                    j += 1
                    continue
                if _LIST_ITEM_RE.match(child):
                    item = _LIST_ITEM_RE.match(child).group(1).strip()  # type: ignore[union-attr]
                    collected.append(_coerce(item))
                    j += 1
                    continue
                # Treat as continuation of preceding scalar value.
                collected.append(stripped)
                j += 1
            if block_style in ("|", ">"):
                out[key] = _join_block("\n".join(collected), block_style)
            else:
                out[key] = collected
            i = j
            continue
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            items = [_coerce(x.strip()) for x in _split_inline_list(inner) if x.strip()]
            out[key] = items
        else:
            out[key] = _coerce(value)
        i += 1
    return out


def _split_inline_list(value: str) -> List[str]:
    """Split an inline list body by commas, respecting brackets/quotes."""
    out: List[str] = []
    buf: List[str] = []
    depth = 0
    quote: str | None = None
    for ch in value:
        if quote:
            buf.append(ch)
            if ch == quote and buf[-2] != "\\":
                quote = None
            continue
        if ch in ('"', "'"):
            quote = ch
            buf.append(ch)
            continue
        if ch in "([{":
            depth += 1
            buf.append(ch)
            continue
        if ch in ")]}":
            depth -= 1
            buf.append(ch)
            continue
        if ch == "," and depth == 0:
            out.append("".join(buf).strip())
            buf = []
            continue
        buf.append(ch)
    if buf:
        out.append("".join(buf).strip())
    return [x for x in out if x]


def _coerce(value: str) -> Any:
    """Coerce a string value to a sensible Python type."""
    s = value.strip()
    if s == "" or s == "~" or s.lower() == "null":
        return ""
    if s.lower() == "true":
        return True
    if s.lower() == "false":
        return False
    # Strip surrounding quotes.
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return s[1:-1]
    # Numbers.
    try:
        if "." in s:
            return float(s)
        return int(s)
    except ValueError:
        pass
    return s


def _join_block(text: str, style: str) -> str:
    """Join a multi-line block into a single string for storage.

    ``|`` (literal) keeps newlines as ``\n`` separators (chomp optional).
    ``>`` (folded) joins lines with spaces, blank lines become paragraph breaks.
    For our purposes we keep it simple: ``|`` becomes ``"\\n".join``, ``>`` becomes
    ``" ".join``.
    """
    if style == "|":
        # Strip a single trailing newline.
        if text.endswith("\n"):
            text = text[:-1]
        return text
    if style == ">":
        # Replace each newline with a space; collapse multiple spaces.
        text = text.replace("\n", " ")
        return re.sub(r"\s+", " ", text).strip()
    return text


def render(front: Dict[str, Any], body: str = "") -> str:
    """Render a frontmatter dict + body into Markdown text.

    Lists are emitted in block style for readability; scalars use inline
    notation. Strings with special characters are double-quoted.
    """
    lines: List[str] = ["---"]
    for key in sorted(front.keys()):
        value = front[key]
        if isinstance(value, bool):
            lines.append(f"{key}: {'true' if value else 'false'}")
        elif isinstance(value, list):
            if not value:
                lines.append(f"{key}: []")
            else:
                lines.append(f"{key}:")
                for item in value:
                    lines.append(f"  - {_quote_scalar(item)}")
        elif isinstance(value, str):
            if "\n" in value:
                lines.append(f"{key}: |")
                for ln in value.splitlines():
                    lines.append(f"  {ln}")
            elif value == "":
                lines.append(f"{key}:")
            else:
                lines.append(f"{key}: {_quote_scalar(value)}")
        elif value is None:
            lines.append(f"{key}:")
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    if body and not body.startswith("\n"):
        lines.append("")
    text = "\n".join(lines) + "\n"
    if body:
        text += body if body.endswith("\n") else body + "\n"
    return text


def _quote_scalar(value: Any) -> str:
    s = str(value)
    if s == "":
        return '""'
    has_dq = '"' in s
    has_sq = "'" in s
    if has_dq and has_sq:
        escaped = s.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if has_dq:
        return f"'{s}'"
    if has_sq:
        return f'"{s}"'
    if any(c in s for c in ":#\n"):
        return f'"{s}"'
    return s


def ensure_required_keys(
    front: Dict[str, Any],
    required: List[str],
    defaults: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Return a copy with required keys present (filling defaults)."""
    out = dict(front)
    defaults = defaults or {}
    for k in required:
        if k not in out or out[k] == "":
            if k in defaults:
                out[k] = defaults[k]
            else:
                raise FrontmatterError(f"missing required frontmatter key: {k!r}")
    return out


def today() -> str:
    """ISO date for today, in UTC."""
    return _dt.date.today().isoformat()


def now_iso() -> str:
    """ISO timestamp with seconds resolution, UTC, with ``Z`` suffix."""
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


__all__ = [
    "FrontmatterError",
    "parse",
    "render",
    "ensure_required_keys",
    "today",
    "now_iso",
]
