---
name: cpp-call-hierarchy
description: Use this skill when an agent needs C/C++ call hierarchy, including who calls a function or method, what a function calls, call sites, incoming calls, outgoing calls, and refactoring impact around C++ functions. Uses clangd call hierarchy rather than text search. Supports C++ 调用层级、调用方、被调用方、函数影响面分析。
license: MIT
metadata:
  short-description: Inspect C++ call hierarchy
  compatibility:
    - codex-cli
    - opencode
---

# cpp-call-hierarchy

Use `cpp-call-hierarchy` to inspect incoming and outgoing calls for C/C++ functions or methods through clangd.

Start `cpp-clangd-service` for the target project before repeated queries. This CLI uses that service by default; pass `--direct` only for fallback/debugging.

## Quick Workflow

```bash
PROJECT_ROOT=/path/to/cpp/project
TOOL=/path/to/cpp-symbol-scout/skills/cpp-call-hierarchy
```

By symbol name:

```bash
PYTHONPATH="$TOOL/src" python3 -B -m cpp_call_hierarchy find 'Namespace::Class::method' \
  --project "$PROJECT_ROOT" --incoming --outgoing --json
```

By exact source position:

```bash
PYTHONPATH="$TOOL/src" python3 -B -m cpp_call_hierarchy at path/to/file.cpp \
  --line 120 --column 18 --project "$PROJECT_ROOT" --incoming --json
```

If neither `--incoming` nor `--outgoing` is set, the CLI requests both directions.

## Command Reference For Agents

- `find SYMBOL --project ROOT [--incoming] [--outgoing] [-n N] [--json]`: resolve a function/method by name and inspect its call hierarchy.
- `at FILE --line L --column C --project ROOT [--incoming] [--outgoing] [--json]`: inspect call hierarchy at an exact 1-based source position. Prefer this for overload-heavy code.
- Shared options: `--compile-commands-dir DIR`, `--no-compile-db` for degraded fallback, `--timeout SECONDS`, `--service-timeout SECONDS`, and `--direct` for debugging without `cpp-clangd-service`.

## JSON Output

The JSON payload has `query`, `symbol`, `item`, `incoming`, and `outgoing`. When outgoing lookup falls back to static scanning, `outgoing_resolution` is `fallback-static`; otherwise it is `clangd`.

- `item` is the selected call hierarchy item with `name`, `detail`, `kind_name`, and `location`.
- `incoming` items have `from` and `call_sites`.
- `outgoing` items have `to` and `call_sites`.
- Locations include `path`, `relative_path`, 1-based `line` and `column`, LSP `range`, and a single-line `snippet`.

## Failure Handling And Boundaries

- Use `--limit` to keep call-site output compact.
- Empty incoming or outgoing arrays can mean no calls, an unindexed position, a declaration without a body, or a clangd limitation. Verify the compile database and exact cursor position before concluding there are no calls.
- The outgoing static fallback is a lexical body scan. Treat fallback results as candidates, not guaranteed semantic callees.
