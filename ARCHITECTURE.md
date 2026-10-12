# ccw-knowledge Architecture

> Knowledge Layer for AI Coding Agents. 设计目标是**基础设施**, 不是开发控制器.

## 0. 边界声明 (Boundaries)

**ccw-knowledge 必须不做的:**
- 不定义 Intent / Spec / Architecture / Implementation 的工作流.
- 不修改项目中的 Intent / Spec / Architecture 文件.
- 不自动发布知识 (Candidate 默认不升级到 Reviewed).
- 不在 attach 时扫描项目代码.
- 不取代 cc-workflow 任何 Skill 的决策权限.
- 不假设 Obsidian 必须运行; 不假设必须后台进程.
- 不引入向量数据库 / Embedding / 云服务 / MCP Server.

**ccw-knowledge 负责:**
- 把外部研究和工程经验沉淀为长期 Markdown 知识.
- 在 Agent 需要时, 按 Quick / Standard / Deep 三档检索结构化证据.
- 强制 Update first, create second.
- 强制 Candidate → Reviewed 的审查流程.
- 提供可重建的本地索引.
- 与 cc-workflow 协调调用, 不侵入各层决策.

---

## 1. 顶层结构

```
ccw-knowledge/
    ccw_knowledge/                # Python package (CLI + 库)
        __init__.py
        __main__.py               # `python -m ccw_knowledge`
        cli.py                    # argparse-based CLI
        config.py                 # 全局配置路径解析
        vault.py                  # Vault 初始化, 项目空间管理
        project.py                # 项目身份 + 附件 (attach/detach)
        knowledge.py              # 知识文档模型
        frontmatter.py            # YAML frontmatter 解析与写入 (stdlib)
        index.py                  # 可重建的内存索引
        search.py                 # Quick / Standard / Deep 三档检索
        capture.py                # 候选知识采集 (本地 Markdown / 文本)
        reconcile.py              # 新旧知识合并 (Update-first)
        review.py                 # 审查流程 (结构 / 内容代理)
        audit.py                  # 健康检查
        scope.py                  # 路径权限/作用域
        pathutil.py               # 跨平台路径工具
        errors.py                 # 统一异常

    plugin/                       # Claude Code Plugin 形式
        .claude-plugin/
            plugin.json
        skills/
            knowledge-context/
                SKILL.md          # 只读检索 Skill (auto-invocable)
                references/
                    retrieval-protocol.md
                    evidence-format.md
            knowledge-capture/
                SKILL.md          # 用户触发型, 创建候选
            knowledge-review/
                SKILL.md          # 审查/发布
            knowledge-audit/
                SKILL.md          # 健康检查
            knowledge-bootstrap/
                SKILL.md          # 项目初始知识提取

    adapters/cc-workflow/
        README.md                 # 集成说明
        INTEGRATION.md            # 集成点 (引用而不修改上游)

    tests/
        unit/
            test_frontmatter.py
            test_knowledge.py
            test_search.py
            test_reconcile.py
            test_review.py
            test_scope.py
            test_project.py
            test_vault.py
            test_cli.py
        e2e/
            test_init_attach_detach.py
            test_search_flow.py
            test_reconcile_flow.py
            test_concurrency_safety.py
            test_agent_simulation.py
        fixtures/
            sample-vault/         # 用于 E2E 的 Vault 模板

    pyproject.toml                # 打包
    README.md
    ARCHITECTURE.md               # 本文件
    CHANGELOG.md
```

---

## 2. 数据模型

### 2.1 全局配置 (`~/.ccw-knowledge/config.json`)

```json
{
  "version": 1,
  "vault": "/absolute/path/to/ObsidianVault",
  "engine_version": "1.0.0"
}
```

> Vault 绝对路径只存于本机配置; 永远不写入项目级配置.

### 2.2 项目注册 (`~/.ccw-knowledge/projects/<id>.json`)

```json
{
  "version": 1,
  "project_id": "lp2",
  "project_root": "/absolute/path/to/project",
  "registered_at": "2026-01-15T10:00:00Z",
  "scopes": ["project:lp2", "shared"],
  "config_path": "<project>/.ccw-knowledge.json"
}
```

### 2.3 项目配置 `<project>/.ccw-knowledge.json`

```yaml
version: 1
project_id: lp2

knowledge:
  enabled: true
  scopes:
    - project:lp2
    - shared

retrieval:
  default_depth: standard
  context_budget: 2000    # 上下文 token 预算

capture:
  enabled: true
  automatic_publication: false
```

### 2.4 Vault 布局

```
<vault>/
  shared/
    sources/             # 原始资料 (raw 不可变)
    candidates/          # 候选知识
    knowledge/           # 已审查通过的共享知识
    _meta.json
  projects/
    <id>/
      sources/
      candidates/
      knowledge/
      _meta.json
```

### 2.5 知识文档 frontmatter

```yaml
---
id: <slug>-<version>
title: ...
status: candidate | reviewed | stale | superseded
confidence: high | medium | low
volatility: hot | warm | cold
category: concept | topic | reference
sources: [<raw-source-paths>]
tags: [...]
aliases: [...]
created: YYYY-MM-DD
updated: YYYY-MM-DD
reviewed_by: <agent-name | user>
reviewed_at: <iso8601>
supersedes: <id>
superseded_by: <id>
scope: shared | project:<id>
---
```

---

## 3. CLI 表面

```
ccw-knowledge init --vault <path> [--force]
ccw-knowledge attach [<project_dir>] [--project-id <id>] [--vault <path>]
ccw-knowledge detach [<project_dir>] [--keep-vault]
ccw-knowledge bootstrap --project <id> [--scope <dir>...] [--budget <int>]

ccw-knowledge search <query>
        [--depth quick|standard|deep]
        [--project <id>]
        [--scope shared|project:<id>]
        [--budget <tokens>]
        [--json|--text]

ccw-knowledge capture --project <id>
        (--file <path> | --text <text>)
        [--title <title>]
        [--sources <comma-paths>]

ccw-knowledge propose-update --knowledge <id> --file <path> [--reason <text>]

ccw-knowledge review
        (--candidate <id> | --all)
        [--action approve|reject|defer]
        [--notes <text>]

ccw-knowledge audit [--fix] [--json]

ccw-knowledge status [--project <id>]
ccw-knowledge config show|set <key> <value>
ccw-knowledge install-skills [--target user|project] [--project <path>]
ccw-knowledge uninstall
```

---

## 4. 检索协议

### 4.1 三档

| 深度 | 输入字段 | 行为 |
|---|---|---|
| quick | title / alias / tag / ID | 命中即返回, 仅返回标题 + 摘要 + 路径 |
| standard | query + surrounding context | 命中后读全文, 检查引用, 输出证据包 |
| deep | query + impact scope | 多次查询, 反例搜索, 跨项目比对, 引用原文 |

### 4.2 Knowledge Evidence Pack (结构化输出, JSON)

```json
{
  "query": "...",
  "depth": "standard",
  "scope": "project:lp2",
  "matches": [
    {
      "id": "...",
      "title": "...",
      "status": "reviewed",
      "confidence": "high",
      "summary": "...",
      "path": "...",
      "sources": ["..."],
      "excerpt": "..."
    }
  ],
  "supporting_evidence": ["<raw-source-paths>"],
  "conflicting_evidence": ["..."],
  "unknowns": ["..."],
  "search_limits": {
    "budget_used": 1234,
    "scanned_files": 42,
    "queries_run": 3
  }
}
```

### 4.3 上下文预算

- 默认标准检索预算 2000 tokens (可配置).
- 超预算截断, 提示 `truncated: true`.
- 检索结果中, 优先返回 ID + summary + path, 让 Agent 决定是否展开全文.

---

## 5. 生命周期

```
Candidate
    |
    v
Reviewed
    |
    +---> Stale (时间衰减触发, 需重新验证)
    |
    +---> Superseded (有新版替代)
```

- Candidate 由 capture / propose-update 创建.
- Reviewed 由 review 子命令显式提升.
- Stale 由 audit 自动标记 (volatile + 时间).
- Superseded 由 propose-update + review 创建新版时自动记录旧版.

---

## 6. 安全模型 (重要)

> 必须诚实区分以下三个层次.

### 6.1 CLI 内部路径检查

CLI 在读写 Vault 文件时强制检查:
- 路径前缀必须在 `registered_scopes` 之内.
- 拒绝 `..` 穿越.
- 拒绝符号链接指向 Scope 外.

### 6.2 操作系统层

- 推荐: Vault 目录普通用户/Agent 不可被无关进程修改.
- Linux: 使用普通用户权限, 不用 sudo 启动 Claude Code.
- Git: 知识文件可纳入 git, 提供版本追溯.

### 6.3 Prompt 层 (信任度最低)

- Skill 描述里写的约束只是"建议", Agent 可能不遵循.
- 我们不把任何安全边界建在 Prompt 上.

**警告文档:** README 中明确告知用户: 任何拥有 Vault 文件系统访问权的 Agent 都可以绕过 Scope 逻辑边界. Scope 是"约定级"权限, 不是强制沙箱.

---

## 7. Claude Code 集成

### 7.1 分发

- 仓库根 `plugin/` 目录即为一个 Claude Code Plugin.
- 通过 `claude --plugin-dir ./plugin` 加载 (测试).
- 通过正式安装: 把 `plugin/skills/` 复制到 `~/.claude/skills/` 或者用 `claude plugin install`.

### 7.2 提供的 Skills

| Skill | 自动调用? | 用户调用? | 副作用 |
|---|---|---|---|
| knowledge-context | 是 | 是 (默认) | 无 (只读) |
| knowledge-capture | 否 (描述触发) | 是 | 创建 Candidate |
| knowledge-review | 否 | 是 | 状态迁移 |
| knowledge-audit | 否 | 是 | 标记 Stale |
| knowledge-bootstrap | 否 | 是 | 多文件创建 Candidate |

### 7.3 不做的事

- 不引入全局强制 Hook.
- 不修改 cc-workflow 现有 Skill 文件.
- 不预设规则修改项目 `CLAUDE.md`/`AGENTS.md`; attach 时如必要, 用可识别标记块追加.
- detach 时清除标记块.

---

## 8. 并发与持久化

### 8.1 写安全

- 所有写: 写到 `*.tmp` → fsync → `os.replace` → fsync 目录.
- 失败时 `*.tmp` 残留不破坏, 下次 attach 时清理.

### 8.2 索引

- 进程内内存索引, 启动时扫描构建.
- `reindex` 命令重建.
- 不维护持久化索引文件 (避免并发写冲突).

### 8.3 修改检测

- 文件 mtime 与上次扫描 mtime 比较.
- 不一致时, 仅对受影响目录重建.

---

## 9. 测试策略

- **unit**: frontmatter, search, scope path check, project 识别.
- **e2e**: tmpdir 内建 Vault, 跑完整 `init → attach → search → capture → review → audit` 流程.
- **agent-sim**: 用 `claude --print` 或脚本 wrapper 模拟 Agent 调用 Skill CLI, 验证返回结构.
- **实际 Claude Code 集成**: README 明确标注本机是否实际验证.

---

## 10. 关键取舍记录

1. **不引入数据库** — 提高可重建性, 减少依赖, 但牺牲大规模性能 (V1 可接受).
2. **frontmatter 用手写 YAML 子集** — stdlib, 可控; 失去 YAML 全部特性, 但避免 PyYAML 依赖.
3. **不自动 attach 时扫描** — 严格遵守"attach 轻量"要求.
4. **Knowledge 只读 Skill 默认 auto** — Claude Code 文档明示 description 控制 auto; 实测效果受模型影响, README 会注明局限.
5. **Knowledge 升级必须显式 review** — 不允许 Agent 自批 (避免 "self-approval").

---

## 11. 未来扩展点 (V1 不做, 但留接口)

- Vector 索引 (可作为可选 `--backend`).
- 远端 Vault (e.g., iCloud sync of Obsidian Vault).
- cc-workflow Phase Hooks (PermissionRequest, etc.).
- 知识血缘 (source → compiled chain) 详细 graph.
- 多 Agent 并行审查.

接口预留位置: `ccw_knowledge/search.py` 的 `Backend` 协议; `ccw_knowledge/vault.py` 的 `Storage` 协议; `ccw_knowledge/knowledge.py` 的 `KnowledgeStore` 协议.
