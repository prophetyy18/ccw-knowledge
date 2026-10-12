"""Command-line interface for ccw-knowledge.

The CLI is the single, deterministic entry point. All non-LLM work
goes through here so that skills, hooks, and tests share one
implementation.

Subcommands are split into three groups:

- Lifecycle: ``init``, ``attach``, ``detach``, ``bootstrap``.
- Knowledge: ``search``, ``capture``, ``propose-update``, ``review``,
  ``audit``.
- Meta: ``status``, ``config``, ``install-skills``, ``uninstall``,
  ``version``.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import textwrap
from pathlib import Path
from typing import List, Optional, Sequence

from . import __version__
from . import errors as _err
from . import (
    audit as audit_mod,
    bootstrap as bootstrap_mod,
    capture as capture_mod,
    knowledge as km,
    project as proj,
    review as review_mod,
    scope as scope_mod,
    vault as vault_mod,
)
from .config import (
    GlobalConfig,
    ensure_initialised,
    global_config_path,
    load_global_config,
    save_global_config,
)
from .index import KnowledgeIndex
from .search import EvidencePack, VALID_DEPTHS, render_pack, search

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _emit_json(payload, *, code: int = 0) -> int:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False))
    sys.stdout.write("\n")
    return code


def _emit_text(payload: str, *, code: int = 0) -> int:
    sys.stdout.write(payload)
    if not payload.endswith("\n"):
        sys.stdout.write("\n")
    return code


def _errprint(msg: str) -> None:
    sys.stderr.write(f"ccw-knowledge: {msg}\n")


def _load_index(vault, scopes, roots, *, include_sources: bool = False) -> KnowledgeIndex:
    return KnowledgeIndex.build(
        vault=vault,
        scopes=scopes,
        roots=roots,
        include_sources=include_sources,
    )


# ---------------------------------------------------------------------------
# Argparse plumbing
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ccw-knowledge",
        description="Knowledge Layer for AI Coding Agents.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(
            """\
            Examples:
              ccw-knowledge init --vault ~/Documents/ObsidianVault
              ccw-knowledge attach ~/code/lp2
              ccw-knowledge search "why does X exist" --depth standard
              ccw-knowledge capture --project lp2 --text "..." --title "..."
              ccw-knowledge review --candidate <id> --action approve
            """
        ),
    )
    p.add_argument("--version", action="version", version=f"ccw-knowledge {__version__}")
    p.add_argument(
        "--quiet", action="store_true", help="suppress non-error output"
    )

    sub = p.add_subparsers(dest="command", metavar="<command>")

    # init
    sub.add_parser("init", help="initialise the global engine and connect a Vault").add_argument(
        "--vault", required=True, help="absolute path to the Vault directory"
    )

    # attach / detach
    attach_p = sub.add_parser("attach", help="register a project")
    attach_p.add_argument(
        "project_dir",
        nargs="?",
        default=None,
        help="project root directory (default: current directory)",
    )
    attach_p.add_argument("--project-id", default=None)
    attach_p.add_argument("--vault", default=None)
    attach_p.add_argument("--scopes", default="project:{id},shared")
    attach_p.add_argument(
        "--update-claude-md",
        action="store_true",
        help="insert a marked ccw-knowledge section into CLAUDE.md/AGENTS.md if present",
    )

    detach_p = sub.add_parser("detach", help="unregister a project")
    detach_p.add_argument("project_dir", nargs="?", default=None)
    detach_p.add_argument("--project-id", default=None)
    detach_p.add_argument("--keep-local-config", action="store_true")
    detach_p.add_argument("--keep-claude-md-section", action="store_true")

    # bootstrap
    boot_p = sub.add_parser("bootstrap", help="explicit initial knowledge extraction")
    boot_p.add_argument("project_dir", nargs="?", default=None)
    boot_p.add_argument("--project", required=True, help="project id (registered)")
    boot_p.add_argument("--scope", action="append", default=[])
    boot_p.add_argument("--max-files", type=int, default=200)
    boot_p.add_argument("--max-chars", type=int, default=4000)
    boot_p.add_argument("--exclude", action="append", default=[])
    boot_p.add_argument("--dry-run", action="store_true")

    # search
    search_p = sub.add_parser("search", help="search knowledge")
    search_p.add_argument("query", help="search query")
    search_p.add_argument(
        "--depth", default="standard", choices=VALID_DEPTHS,
    )
    search_p.add_argument("--project", default=None)
    search_p.add_argument("--scope", default=None)
    search_p.add_argument("--budget", type=int, default=2000)
    search_p.add_argument("--limit", type=int, default=25)
    search_p.add_argument("--include-sources", action="store_true")
    search_p.add_argument("--text", action="store_true")

    # capture
    cap_p = sub.add_parser("capture", help="capture knowledge into the candidates bucket")
    cap_p.add_argument("--project", required=True)
    cap_p.add_argument("--file", default=None)
    cap_p.add_argument("--text", default=None)
    cap_p.add_argument("--title", default=None)
    cap_p.add_argument("--sources", default=None, help="comma-separated source paths")
    cap_p.add_argument("--tags", default=None)
    cap_p.add_argument("--category", default="topic")
    cap_p.add_argument("--confidence", default="medium")
    cap_p.add_argument("--volatility", default="warm")

    # propose-update
    pu_p = sub.add_parser("propose-update", help="submit an update proposal against existing knowledge")
    pu_p.add_argument("--knowledge", required=True, help="id of the existing knowledge document")
    pu_p.add_argument("--project", required=True)
    pu_p.add_argument("--file", required=True)
    pu_p.add_argument("--reason", default=None)

    # review
    rev_p = sub.add_parser("review", help="review a candidate")
    rev_p.add_argument("--candidate", default=None)
    rev_p.add_argument("--all", action="store_true")
    rev_p.add_argument("--project", required=True)
    rev_p.add_argument(
        "--action", required=True, choices=["approve", "reject", "defer"]
    )
    rev_p.add_argument("--reviewer", default="human")
    rev_p.add_argument("--notes", default=None)
    rev_p.add_argument("--audit-only", action="store_true")

    # audit
    aud_p = sub.add_parser("audit", help="audit the Vault")
    aud_p.add_argument("--project", default=None)
    aud_p.add_argument("--scope", default=None)
    aud_p.add_argument("--fix", action="store_true")

    # status
    status_p = sub.add_parser("status", help="show engine state")
    status_p.add_argument("--project", default=None)

    # config
    cfg_p = sub.add_parser("config", help="manage global configuration")
    cfg_sub = cfg_p.add_subparsers(dest="config_command", required=True)
    cfg_sub.add_parser("show")
    set_p = cfg_sub.add_parser("set")
    set_p.add_argument("key")
    set_p.add_argument("value")

    # install-skills
    inst_p = sub.add_parser("install-skills", help="copy the Knowledge Skills into a target")
    inst_p.add_argument("--target", default="user", choices=["user", "project"])
    inst_p.add_argument("--project-dir", default=None)

    sub.add_parser("uninstall", help="remove engine state")

    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    if argv is None:
        argv = sys.argv[1:]
    # Allow --help at top level.
    if not argv:
        parser.print_help()
        return EXIT_USAGE
    argv = list(argv)
    json_flag = False
    quiet_flag = False
    # Pull top-level --json / --quiet out so they can appear anywhere.
    if "--json" in argv:
        argv.remove("--json")
        json_flag = True
    if "--quiet" in argv:
        argv.remove("--quiet")
        quiet_flag = True
    args = parser.parse_args(argv)
    # Top-level flags were pre-extracted. Subcommands don't carry them
    # in argparse, so we set them on the Namespace if missing.
    if not hasattr(args, "json"):
        args.json = json_flag
    if not hasattr(args, "quiet"):
        args.quiet = quiet_flag
    if not args.command:
        parser.print_help()
        return EXIT_USAGE
    handler = _DISPATCH.get(args.command)
    if handler is None:
        parser.print_help()
        return EXIT_USAGE
    try:
        code = handler(args)
        if isinstance(code, int):
            return code
        return EXIT_OK
    except _err.CCWError as e:
        _errprint(str(e))
        return e.exit_code
    except KeyboardInterrupt:
        _errprint("interrupted")
        return 130


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


def cmd_init(args: argparse.Namespace) -> int:
    """Initialise the global engine."""
    cfg_path = global_config_path()
    existing = load_global_config(cfg_path) if cfg_path.exists() else None
    if existing and existing.is_initialised() and not _bool(args, "force", False):
        # Already initialised — be idempotent unless asked to override.
        _emit_text(
            f"engine already initialised; vault = {existing.vault}\n"
            f"(pass --force via config subcommand to re-init)"
        )
        return EXIT_OK
    layout = vault_mod.init_vault(args.vault)
    return _emit_text(
        f"engine initialised.\n"
        f"  vault: {layout.root}\n"
        f"  shared: {layout.shared_sources.parent}\n"
        f"  projects: {layout.projects_root}\n"
    )


def _bool(args: argparse.Namespace, name: str, default: bool) -> bool:
    return bool(getattr(args, name, default))


def cmd_attach(args: argparse.Namespace) -> int:
    cfg = ensure_initialised()
    vault = vault_mod.resolve_vault(cfg)
    project_root = Path(args.project_dir or os.getcwd()).expanduser().resolve()
    if not project_root.exists() or not project_root.is_dir():
        _errprint(f"project directory not found: {project_root}")
        return EXIT_USAGE
    pid = args.project_id
    raw_scopes = args.scopes
    if raw_scopes and "{id}" in raw_scopes:
        # We compute id again later, but we need a placeholder.
        # Use a derived id first.
        derived_id = proj.derive_project_id(project_root, pid)
        raw_scopes = raw_scopes.replace("{id}", derived_id)
    scopes = scope_mod.ScopeSet.parse(raw_scopes)
    rec = proj.attach(
        project_root=project_root,
        vault=vault,
        project_id=pid,
        scopes=scopes.to_list(),
        update_claude_md=args.update_claude_md,
    )
    if args.json:
        return _emit_json(rec.to_dict())
    return _emit_text(
        f"project attached.\n"
        f"  id: {rec.project_id}\n"
        f"  root: {rec.project_root}\n"
        f"  scopes: {', '.join(rec.scopes)}\n"
        f"  config file: {rec.config_path}\n"
    )


def cmd_detach(args: argparse.Namespace) -> int:
    ensure_initialised()
    project_root = Path(args.project_dir or os.getcwd()).expanduser().resolve()
    rec = proj.detach(
        project_root=project_root,
        project_id=args.project_id,
        keep_local_config=args.keep_local_config,
        remove_claude_md_section=not args.keep_claude_md_section,
    )
    if rec is None:
        return _emit_text("project was not registered.\n")
    return _emit_text(
        f"project detached.\n"
        f"  id: {rec.project_id}\n"
        f"  root: {rec.project_root}\n"
    )


def cmd_bootstrap(args: argparse.Namespace) -> int:
    cfg = ensure_initialised()
    vault = vault_mod.resolve_vault(cfg)
    scopes = scope_mod.ScopeSet.parse([f"project:{args.project}", "shared"])
    roots = scope_mod.ScopeRoots.from_vault(vault, scopes)
    project_root = Path(args.project_dir or os.getcwd()).expanduser().resolve()
    if not project_root.exists() or not project_root.is_dir():
        _errprint(f"project directory not found: {project_root}")
        return EXIT_USAGE
    bcfg = bootstrap_mod.BootstrapConfig(
        project_id=args.project,
        project_root=project_root,
        include_globs=args.scope if args.scope else [],
        max_files=args.max_files,
        max_chars_per_file=args.max_chars,
        exclude_dirs=args.exclude,
        dry_run=args.dry_run,
    )
    idx = _load_index(vault, scopes, roots)
    rep = bootstrap_mod.bootstrap(bcfg, vault=vault, scopes=scopes, roots=roots, index=idx)
    if args.json:
        return _emit_json(rep.to_dict())
    return _emit_text(
        f"bootstrap complete (dry_run={args.dry_run}).\n"
        f"  scanned: {rep.scanned_files}\n"
        f"  candidates created: {rep.candidates_created}\n"
        f"  candidates skipped: {rep.candidates_skipped}\n"
        f"  findings: {len(rep.findings)}\n"
        f"\nfindings:\n" + "\n".join(f"  - {x}" for x in rep.findings) + "\n"
        + "\ncandidates:\n" + "\n".join(f"  - {x}" for x in rep.candidates) + "\n"
    )


def _resolve_search_scope(vault, args) -> tuple:
    cfg_scopes: list[str] = []
    if args.project:
        cfg_scopes.append(f"project:{args.project}")
    if args.scope and args.scope != "shared":
        cfg_scopes.append(args.scope)
    if not cfg_scopes:
        cfg_scopes = ["shared"]
    scopes = scope_mod.ScopeSet.parse(cfg_scopes)
    roots = scope_mod.ScopeRoots.from_vault(vault, scopes)
    return scopes, roots


def cmd_search(args: argparse.Namespace) -> int:
    cfg = ensure_initialised()
    vault = vault_mod.resolve_vault(cfg)
    scopes, roots = _resolve_search_scope(vault, args)
    idx = _load_index(vault, scopes, roots, include_sources=args.include_sources)
    pack: EvidencePack = search(
        args.query,
        index=idx,
        vault=vault,
        scopes=scopes,
        roots=roots,
        depth=args.depth,
        context_budget=args.budget,
        limit=args.limit,
        include_sources=args.include_sources,
    )
    if args.json:
        return _emit_json(pack.to_dict())
    if args.text or not args.json:
        # Default text mode for skill/agent consumption: use render_pack
        # so it always includes evidence pointers.
        return _emit_text(render_pack(pack, mode="text"))
    return EXIT_OK


def cmd_capture(args: argparse.Namespace) -> int:
    cfg = ensure_initialised()
    vault = vault_mod.resolve_vault(cfg)
    project_id = args.project
    scopes = scope_mod.ScopeSet.parse([f"project:{project_id}", "shared"])
    roots = scope_mod.ScopeRoots.from_vault(vault, scopes)
    sources = _split_csv(args.sources)
    tags = _split_csv(args.tags)
    if args.file:
        doc = capture_mod.capture_file(
            vault=vault,
            scopes=scopes,
            roots=roots,
            project_id=project_id,
            source_path=Path(args.file).expanduser().resolve(),
            title=args.title,
            tags=tags,
            category=args.category,
            confidence=args.confidence,
            volatility=args.volatility,
        )
    elif args.text is not None:
        if not args.title:
            _errprint("--title is required when using --text")
            return EXIT_USAGE
        doc = capture_mod.capture_text(
            vault=vault,
            scopes=scopes,
            roots=roots,
            project_id=project_id,
            title=args.title,
            body=args.text,
            sources=sources,
            tags=tags,
            category=args.category,
            confidence=args.confidence,
            volatility=args.volatility,
        )
    else:
        _errprint("either --file or --text is required")
        return EXIT_USAGE
    payload = {
        "id": doc.id,
        "title": doc.title,
        "status": doc.status,
        "path": str(doc.path),
        "scope": f"project:{project_id}",
    }
    if args.json:
        return _emit_json(payload)
    return _emit_text(
        f"candidate captured.\n"
        f"  id: {doc.id}\n"
        f"  title: {doc.title}\n"
        f"  path: {doc.path}\n"
        f"  status: {doc.status} (awaits review)\n"
    )


def cmd_propose_update(args: argparse.Namespace) -> int:
    """Submit an update proposal as a new Candidate pointing at the
    existing knowledge document with ``supersedes: <existing_id>``.

    Auto-publication is *always* false. The reviewer must approve to
    demote the existing knowledge to ``superseded`` and elevate the
    new Candidate.
    """
    cfg = ensure_initialised()
    vault = vault_mod.resolve_vault(cfg)
    project_id = args.project
    scopes = scope_mod.ScopeSet.parse([f"project:{project_id}", "shared"])
    roots = scope_mod.ScopeRoots.from_vault(vault, scopes)

    source_path = Path(args.file).expanduser().resolve()
    if not source_path.exists() or not source_path.is_file():
        _errprint(f"proposal file not found: {source_path}")
        return EXIT_USAGE
    title = args.reason or f"Update to {args.knowledge}"
    body = source_path.read_text(encoding="utf-8", errors="ignore")
    body += (
        f"\n\n---\nsupersedes: {args.knowledge}\n"
    )
    doc = capture_mod.capture_text(
        vault=vault,
        scopes=scopes,
        roots=roots,
        project_id=project_id,
        title=title,
        body=body,
        sources=[str(source_path)],
        tags=["update-proposal"],
        category="reference",
        confidence="medium",
        volatility="warm",
    )
    payload = {
        "id": doc.id,
        "supersedes": args.knowledge,
        "path": str(doc.path),
        "note": "auto-publication is disabled; run review to promote",
    }
    if args.json:
        return _emit_json(payload)
    return _emit_text(
        f"update proposal captured.\n"
        f"  proposed: {doc.id}\n"
        f"  supersedes: {args.knowledge}\n"
        f"  path: {doc.path}\n"
        f"  next: run `ccw-knowledge review --candidate {doc.id} --action approve ...`\n"
    )


def cmd_review(args: argparse.Namespace) -> int:
    """Approve / reject / defer one or all pending candidates.

    ``--audit-only`` runs the structural review without applying any
    status change.
    """
    cfg = ensure_initialised()
    vault = vault_mod.resolve_vault(cfg)
    project_id = args.project
    scopes = scope_mod.ScopeSet.parse([f"project:{project_id}", "shared"])
    roots = scope_mod.ScopeRoots.from_vault(vault, scopes)
    if not args.candidate and not args.all:
        _errprint("either --candidate <id> or --all is required")
        return EXIT_USAGE
    if args.audit_only:
        # Inspect without mutating.
        if not args.candidate:
            _errprint("--audit-only requires --candidate <id>")
            return EXIT_USAGE
        from . import review as rv
        path = rv._find_document_path_in_bucket(
            roots, f"project:{project_id}", "candidates", args.candidate
        )
        if path is None:
            _errprint(f"candidate {args.candidate} not found")
            return EXIT_USAGE
        doc = km.read_document(path)
        rep = rv.structural_review(doc, vault_root=vault.root)
        if args.json:
            return _emit_json(rep.to_dict())
        return _emit_text(
            f"audit-only report for {args.candidate}:\n"
            f"  critical: {rep.critical_count}\n"
            + "\n".join(f"  - [{f.severity}] {f.code}: {f.message}" for f in rep.findings)
            + "\n"
        )
    if args.action == "approve":
        doc, rep = review_mod.approve_candidate(
            vault=vault, scopes=scopes, roots=roots,
            project_id=project_id,
            candidate_id=args.candidate,
            reviewer=args.reviewer,
            note=args.notes,
        )
    elif args.action == "reject":
        doc = review_mod.reject_candidate(
            vault=vault, scopes=scopes, roots=roots,
            project_id=project_id, candidate_id=args.candidate,
            reviewer=args.reviewer, note=args.notes,
        )
        rep = None
    elif args.action == "defer":
        doc = review_mod.defer_candidate(
            vault=vault, scopes=scopes, roots=roots,
            project_id=project_id, candidate_id=args.candidate,
            reviewer=args.reviewer, note=args.notes,
        )
        rep = None
    else:
        _errprint(f"unknown action: {args.action}")
        return EXIT_USAGE
    out = {
        "id": doc.id,
        "status": doc.status,
        "path": str(doc.path),
        "reviewer": args.reviewer,
    }
    if rep is not None:
        out["structural"] = rep.to_dict()
    if args.json:
        return _emit_json(out)
    return _emit_text(
        f"review complete.\n"
        f"  candidate: {doc.id}\n"
        f"  status: {doc.status}\n"
        f"  path: {doc.path}\n"
    )


def cmd_audit(args: argparse.Namespace) -> int:
    cfg = ensure_initialised()
    vault = vault_mod.resolve_vault(cfg)
    if args.project:
        scopes = scope_mod.ScopeSet.parse([f"project:{args.project}", "shared"])
    else:
        # audit everything we know about
        scopes = scope_mod.ScopeSet.parse(["shared"] + [
            f"project:{pid}" for pid in vault.known_project_ids()
        ])
    roots = scope_mod.ScopeRoots.from_vault(vault, scopes)
    idx = _load_index(vault, scopes, roots)
    rep = audit_mod.audit(
        vault=vault, scopes=scopes, roots=roots, index=idx, fix=bool(args.fix)
    )
    if args.json:
        return _emit_json(rep.to_dict())
    return _emit_text(
        f"audit complete.\n"
        f"  findings: {len(rep.findings)}\n"
        f"  auto-fixed: {len(rep.auto_fixed)}\n"
        + (("\nfindings:\n" + "\n".join(
            f"  - [{f.severity}] {f.code}: {f.message}"
            + (f"  ({f.file})" if f.file else "")
            for f in rep.findings)) if rep.findings else "\n")
        + (("\nauto-fixed:\n" + "\n".join(f"  - {p}" for p in rep.auto_fixed)) if rep.auto_fixed else "")
        + "\n"
    )


def cmd_status(args: argparse.Namespace) -> int:
    cfg_path = global_config_path()
    cfg = load_global_config(cfg_path)
    payload = {
        "engine_version": __version__,
        "config_path": str(cfg_path),
        "initialised": cfg.is_initialised(),
        "vault": cfg.vault,
    }
    if cfg.is_initialised():
        try:
            vault = vault_mod.resolve_vault(cfg)
        except _err.VaultError as e:
            payload["vault_error"] = str(e)
        else:
            projects = vault.known_project_ids()
            payload["shared_knowledge_root"] = str(vault.shared_knowledge)
            payload["shared_candidates_root"] = str(vault.shared_candidates)
            payload["projects"] = projects
    if args.json:
        return _emit_json(payload)
    return _emit_text(
        "\n".join(f"{k}: {v}" for k, v in payload.items()) + "\n"
    )


def cmd_config(args: argparse.Namespace) -> int:
    cfg = load_global_config()
    if args.config_command == "show":
        if args.json:
            return _emit_json(cfg.__dict__)
        return _emit_text(json.dumps(cfg.__dict__, indent=2, sort_keys=True))
    # set
    if args.key == "vault":
        new_vault = Path(args.value).expanduser().resolve()
        cfg.vault = str(new_vault)
        save_global_config(cfg)
        return _emit_text(f"vault = {cfg.vault}\n")
    _errprint(f"unknown config key: {args.key}")
    return EXIT_USAGE


def cmd_install_skills(args: argparse.Namespace) -> int:
    """Copy or symlink the plugin's skills into the requested target."""
    target = args.target
    src_dir = Path(__file__).resolve().parent.parent / "plugin" / "skills"
    if not src_dir.exists():
        _errprint(f"plugin skills not found at {src_dir}")
        return EXIT_ERROR
    if target == "user":
        from .pathutil import global_config_root
        dst_root = global_config_root() / "skills"
        dst_root.mkdir(parents=True, exist_ok=True)
        n = _copy_skills(src_dir, dst_root, prefer_symlink=True)
        return _emit_text(f"installed {n} skills to {dst_root}\n")
    # project
    project_dir = Path(args.project_dir or os.getcwd()).expanduser().resolve()
    if not project_dir.exists():
        _errprint(f"project dir not found: {project_dir}")
        return EXIT_USAGE
    dst_root = project_dir / ".claude" / "skills"
    dst_root.mkdir(parents=True, exist_ok=True)
    n = _copy_skills(src_dir, dst_root, prefer_symlink=True)
    return _emit_text(f"installed {n} skills to {dst_root}\n")


def _copy_skills(src_dir: Path, dst_root: Path, *, prefer_symlink: bool) -> int:
    n = 0
    for skill_dir in sorted(src_dir.iterdir()):
        if not skill_dir.is_dir():
            continue
        dst = dst_root / skill_dir.name
        if prefer_symlink and not dst.exists():
            try:
                os.symlink(skill_dir.resolve(), dst, target_is_directory=True)
                n += 1
                continue
            except (OSError, NotImplementedError):
                pass
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(skill_dir, dst)
        n += 1
    return n


def cmd_uninstall(args: argparse.Namespace) -> int:
    """Remove the engine's global state. By design this is a no-op on
    the Vault contents and on any project registrations — those must
    be cleaned up explicitly via ``detach`` and ``init --force``.

    The only thing this command does is wipe the engine's home
    directory, which the user must opt into with --yes.
    """
    return _emit_text(
        "refusing to remove engine state automatically. To uninstall:\n"
        "  - run `ccw-knowledge detach` for each registered project\n"
        "  - remove `~/.ccw-knowledge/` manually if you really want to wipe state\n"
        "  - reinstall skills via `ccw-knowledge install-skills` after re-init\n"
    )


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------


_DISPATCH = {
    "init": cmd_init,
    "attach": cmd_attach,
    "detach": cmd_detach,
    "bootstrap": cmd_bootstrap,
    "search": cmd_search,
    "capture": cmd_capture,
    "propose-update": cmd_propose_update,
    "review": cmd_review,
    "audit": cmd_audit,
    "status": cmd_status,
    "config": cmd_config,
    "install-skills": cmd_install_skills,
    "uninstall": cmd_uninstall,
}


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _split_csv(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


if __name__ == "__main__":
    raise SystemExit(main())
