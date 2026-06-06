---
name: cpp-symbol-scout
description: Use this skill when an agent needs fast clangd-backed C/C++ symbol lookup, class member listing, or source retrieval from Codex CLI or OpenCode, including locating class/function/method definitions or implementations, listing class methods/fields by access level, querying by symbol name, using compile_commands.json, and reusing the shared cpp-clangd-service. Also use for C/C++ 符号查询、定义/实现定位、类成员列表、源码片段提取。
license: MIT
metadata:
  short-description: Fast clangd C++ symbol lookup
  compatibility:
    - codex-cli
    - opencode
---

# cpp-symbol-scout

Use `cpp-symbol-scout` to locate C/C++ symbols through clangd and return the definition or implementation location with a complete source snippet. It can also list a class or struct's methods, fields, and nested types without returning method bodies. Prefer it over text search when the user asks for a class, function, method, constructor, destructor, qualified symbol, source implementation, or class member list.

## Operating Rules

- Confirm the C/C++ project root and compile database first. `compile_commands.json` or `compile_flags.txt` is required unless the user explicitly accepts degraded results.
- Use the shared service workflow for repeated queries or performance-sensitive work: start `cpp-clangd-service`, then run `query`.
- `cpp-symbol-scout start/status/stop` forwards to `cpp-clangd-service` for compatibility.
- Use `--direct` only to debug clangd or installation problems; it starts clangd for every query and is not the high-performance path.
- Keep query timeouts small after the service is warm. Use `--timeout 1` for normal lookups and increase only when clangd is still indexing or the symbol is ambiguous.
- Use `members` when the user asks for a class API surface, public methods, fields/properties, or declarations without method implementations.
- Return file paths and line numbers to the user. Include full snippets only when the user asks for source, implementation, or exact code.

## Quick Workflow

Set variables explicitly:

```bash
PROJECT_ROOT=/path/to/cpp/project
SCOUT=/path/to/cpp-symbol-scout/skills/cpp-symbol-scout
SERVICE=/path/to/cpp-symbol-scout/services/cpp-clangd-service
```

If the CLI is installed:

```bash
cpp-clangd-service start --project "$PROJECT_ROOT" --wait
cpp-symbol-scout query 'SymbolName' --project "$PROJECT_ROOT" --timeout 1 -n 1
```

If using this skill repository without installing the package:

```bash
PYTHONPATH="$SERVICE/src" python3 -B -m cpp_clangd_service start --project "$PROJECT_ROOT" --wait
PYTHONPATH="$SCOUT/src" python3 -B -m cpp_symbol_scout query 'SymbolName' --project "$PROJECT_ROOT" --timeout 1 -n 1
```

Useful query variants:

```bash
cpp-symbol-scout query 'ClassName' --project "$PROJECT_ROOT" --source-only
cpp-symbol-scout query 'Namespace::Class::method' --project "$PROJECT_ROOT" --json
cpp-symbol-scout query 'method_name' --project "$PROJECT_ROOT" --timeout 4 -n 3
cpp-symbol-scout members 'ClassName' --project "$PROJECT_ROOT" --access public --json
cpp-symbol-scout members 'ClassName' --project "$PROJECT_ROOT" --kind method
cpp-symbol-scout status --project "$PROJECT_ROOT"
cpp-symbol-scout stop --project "$PROJECT_ROOT"
```

## Command Reference For Agents

- `start --project ROOT [--clangd PATH] [--compile-commands-dir DIR] [--wait]`: start the shared clangd service for repeated queries. Use `--wait` before the first lookup in a large project.
- `status --project ROOT [--json]`: verify service readiness, selected clangd, compile database directory, PID, log path, and cache size.
- `stop --project ROOT`: stop the shared service for that project.
- `query SYMBOL --project ROOT [-n N] [--json] [--source-only] [--no-implementation]`: find symbols and return source snippets. By default, function-like declarations are resolved to implementations when clangd can do it.
- `members SYMBOL --project ROOT [--access all|public|protected|private] [--kind all|method|field|type] [-n N] [--json]`: list members from a class/struct declaration without method bodies.
- Shared clangd options: use `--compile-commands-dir DIR` when the compile database is outside the root, `--allow-missing-compile-db` only for degraded fallback, and `--direct` only when debugging the service path.

## JSON Output

`query --json` returns a list. Each result has `name`, `full_name`, `kind`, `kind_name`, `location`, `source`, `source_range`, `resolution`, and `elapsed_ms`. `location.line` and `location.character` are 1-based for user-facing reporting; nested `range` values are LSP-style 0-based.

`members --json` returns an object with:

- `class`: selected class/struct candidate, including `name`, `full_name`, `kind_name`, `location`, and `source_range`.
- `summary`: `member_count`, `returned_count`, `access_filter`, `kind_filter`, per-kind counts, and `truncated`.
- `members`: items with `name`, `kind` (`method`, `field`, `type`), `access`, `declaration`, and `location`.

## Failure Handling And Boundaries

- Exit code `1` with empty results means no confident clangd result was returned; check service readiness, compile database, symbol qualification, and indexing before concluding the symbol does not exist.
- If the service is unavailable, run `cpp-clangd-service start --project "$PROJECT_ROOT" --wait` or use `cpp-symbol-scout start --project "$PROJECT_ROOT" --wait`.
- `members` inspects the selected class/struct declaration only. It does not expand inherited base-class members, does not return method implementations, and may miss macro-generated or heavily preprocessed members.
- For overloaded or ambiguous names, prefer fully qualified symbols and increase `--candidate-limit` before increasing timeouts.

## Install Or Locate The CLI

When the command is missing, first check whether the current directory is this skill directory. If it is, run through `PYTHONPATH=src`. Otherwise locate the installed skill directory in common Codex/OpenCode locations:

```bash
find ~/.codex/skills ~/.config/opencode/skills ~/.claude/skills ~/.agents/skills \
  -maxdepth 2 -path '*/cpp-symbol-scout/SKILL.md' 2>/dev/null
```

After locating the skill repository, either use `PYTHONPATH="$SCOUT/src"` or install it:

```bash
python3 -m pip install -e "$SCOUT"
```

Read [references/cli-workflow.md](references/cli-workflow.md) when you need compile database examples, service lifecycle details, or output interpretation.

Read [references/integration.md](references/integration.md) when installing or adapting the skill for Codex CLI, OpenCode, or project-local skill folders.

Read [references/troubleshooting.md](references/troubleshooting.md) when clangd is missing, the service is not ready, queries return no results, or performance misses the 1-second target.
