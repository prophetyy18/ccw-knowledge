# Changelog

All notable changes to `ccw-knowledge` are documented here. The
format follows [Keep a Changelog](https://keepachangelog.com/).

## [1.0.0] — 2026-10-12

### Added

- `init`, `attach`, `detach`, `bootstrap` lifecycle commands.
- `search` with `quick`/`standard`/`deep` depths and structured
  Evidence Pack output.
- `capture` / `propose-update` / `review` / `audit` for the
  knowledge lifecycle.
- `Knowledge Reconcile` (Update first, create second).
- Claude Code plugin with five Skills:
  `knowledge-context`, `knowledge-capture`, `knowledge-review`,
  `knowledge-audit`, `knowledge-bootstrap`.
- Cross-platform support (Windows + Linux), zero Python dependencies.
- Comprehensive unit and end-to-end tests.

### Notes for operators

- V1 ships `ccw-knowledge install-skills --target user` to install
  the Skills into `~/.claude/skills/`, and `--target project` to
  install them into `<project>/.claude/skills/`.
- The engine's home directory is `~/.ccw-knowledge/` (override with
  `CCW_HOME` / `CCW_CONFIG_DIR`).
- The Vault absolute path lives in `~/.ccw-knowledge/config.json`
  only and never in project files.
