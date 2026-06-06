---
name: cpp-type-inspector
description: Use this skill when an agent needs exact C/C++ type information for an expression, variable, function return, method, template, pointer, reference, or declaration using clangd hover/typeDefinition. Also use when AI code generation needs to avoid guessing C++ types. Supports C++ 类型查看、表达式类型、变量类型、返回类型、模板类型分析。
license: MIT
metadata:
  short-description: Inspect C++ types through clangd
  compatibility:
    - codex-cli
    - opencode
---

# cpp-type-inspector

Use `cpp-type-inspector` to inspect exact C/C++ type information through clangd hover, definition, and typeDefinition.

Start `cpp-clangd-service` for the target project before repeated queries. This CLI uses that service by default; pass `--direct` only for fallback/debugging.

## Quick Workflow

```bash
PROJECT_ROOT=/path/to/cpp/project
TOOL=/path/to/cpp-symbol-scout/skills/cpp-type-inspector
```

Inspect by source position:

```bash
PYTHONPATH="$TOOL/src" python3 -B -m cpp_type_inspector at path/to/file.cpp \
  --line 120 --column 18 --project "$PROJECT_ROOT" --json
```

Inspect by symbol name:

```bash
PYTHONPATH="$TOOL/src" python3 -B -m cpp_type_inspector find 'Namespace::Class::method' \
  --project "$PROJECT_ROOT" --json
```

Prefer `at` when possible because exact positions avoid overload ambiguity.

## Command Reference For Agents

- `at FILE --line L --column C --project ROOT [--json]`: inspect hover text, definition, and type definition at an exact 1-based source position.
- `find SYMBOL --project ROOT [--json]`: resolve a symbol by name, then inspect the resolved position. Use only when no exact source position is available.
- Shared options: `--compile-commands-dir DIR`, `--no-compile-db` for degraded fallback, `--timeout SECONDS`, `--service-timeout SECONDS`, and `--direct` for debugging without `cpp-clangd-service`.

## JSON Output

The JSON payload has `query`, `symbol`, `position`, `hover`, `type_summary`, `definitions`, and `type_definitions`.

- `position` is the inspected location and includes a one-line `snippet`.
- `hover.text` is clangd's raw hover text; `type_summary.display` is the first compact type-like line extracted from hover text.
- `definitions` and `type_definitions` are location arrays with `path`, `relative_path`, 1-based `line` and `column`, LSP `range`, and `snippet`.

## Failure Handling And Boundaries

- Empty `hover.text` or empty definition arrays usually mean the cursor is not on an inspectable token, clangd lacks compile context, or the symbol is macro/generated.
- For expressions, use `at`; name-based `find` is best for declarations and can choose the wrong overload.
- Treat `type_summary.display` as a compact hint. Use `hover.text` when exact qualifiers, templates, references, or aliases matter.
