---
name: cpp-symbol-scout
description: Use this skill when an agent needs fast clangd-backed C/C++ symbol lookup or source retrieval from Codex CLI or OpenCode, including locating class/function/method definitions or implementations, querying by symbol name, using compile_commands.json, and operating the cpp-symbol-scout Python daemon. Also use for C/C++ 符号查询、定义/实现定位、源码片段提取。
license: MIT
metadata:
  short-description: Fast clangd C++ symbol lookup
  compatibility:
    - codex-cli
    - opencode
---

# cpp-symbol-scout

Use `cpp-symbol-scout` to locate C/C++ symbols through clangd and return the definition or implementation location with a complete source snippet. Prefer it over text search when the user asks for a class, function, method, constructor, destructor, qualified symbol, or source implementation.

## Operating Rules

- Confirm the C/C++ project root and compile database first. `compile_commands.json` or `compile_flags.txt` is required unless the user explicitly accepts degraded results.
- Use the daemon workflow for repeated queries or performance-sensitive work: `start`, `query`, `status`, `stop`.
- Use `--direct` only to debug clangd or installation problems; it starts clangd for every query and is not the high-performance path.
- Keep query timeouts small after the daemon is warm. Use `--timeout 1` for normal lookups and increase only when clangd is still indexing or the symbol is ambiguous.
- Return file paths and line numbers to the user. Include full snippets only when the user asks for source, implementation, or exact code.

## Quick Workflow

Set variables explicitly:

```bash
PROJECT_ROOT=/path/to/cpp/project
SCOUT=/path/to/cpp-symbol-scout
```

If the CLI is installed:

```bash
cpp-symbol-scout start --project "$PROJECT_ROOT" --wait
cpp-symbol-scout query 'SymbolName' --project "$PROJECT_ROOT" --timeout 1 -n 1
```

If using this skill repository without installing the package:

```bash
PYTHONPATH="$SCOUT/src" python3 -B -m cpp_symbol_scout start --project "$PROJECT_ROOT" --wait
PYTHONPATH="$SCOUT/src" python3 -B -m cpp_symbol_scout query 'SymbolName' --project "$PROJECT_ROOT" --timeout 1 -n 1
```

Useful query variants:

```bash
cpp-symbol-scout query 'ClassName' --project "$PROJECT_ROOT" --source-only
cpp-symbol-scout query 'Namespace::Class::method' --project "$PROJECT_ROOT" --json
cpp-symbol-scout query 'method_name' --project "$PROJECT_ROOT" --timeout 4 -n 3
cpp-symbol-scout status --project "$PROJECT_ROOT"
cpp-symbol-scout stop --project "$PROJECT_ROOT"
```

## Install Or Locate The CLI

When the command is missing, first check whether this repository is the current directory. If it is, run through `PYTHONPATH=src`. Otherwise locate the installed skill directory in common Codex/OpenCode locations:

```bash
find ~/.codex/skills ~/.config/opencode/skills ~/.claude/skills ~/.agents/skills \
  -maxdepth 2 -path '*/cpp-symbol-scout/SKILL.md' 2>/dev/null
```

After locating the skill repository, either use `PYTHONPATH="$SCOUT/src"` or install it:

```bash
python3 -m pip install -e "$SCOUT"
```

Read [references/cli-workflow.md](references/cli-workflow.md) when you need compile database examples, daemon lifecycle details, or output interpretation.

Read [references/integration.md](references/integration.md) when installing or adapting the skill for Codex CLI, OpenCode, or project-local skill folders.

Read [references/troubleshooting.md](references/troubleshooting.md) when clangd is missing, the daemon is not ready, queries return no results, or performance misses the 1-second target.
