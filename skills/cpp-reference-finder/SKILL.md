---
name: cpp-reference-finder
description: Use this skill when an agent needs semantic C/C++ references for a class, function, method, variable, enum, or macro-like symbol using clangd instead of text search. Also use before refactoring, renaming, deleting, or changing a C++ symbol to inspect real reference locations. Supports C++ 引用查找、调用点定位、符号影响面分析。
license: MIT
metadata:
  short-description: Find semantic C++ references
  compatibility:
    - codex-cli
    - opencode
---

# cpp-reference-finder

Use `cpp-reference-finder` to locate semantic C/C++ references through clangd. Prefer it over `rg` when the task needs real symbol references rather than textual matches.

Start `cpp-clangd-service` for the target project before repeated queries. This CLI uses that service by default; pass `--direct` only for fallback/debugging.

## Quick Workflow

```bash
PROJECT_ROOT=/path/to/cpp/project
TOOL=/path/to/cpp-symbol-scout/skills/cpp-reference-finder
```

Query by symbol name:

```bash
PYTHONPATH="$TOOL/src" python3 -B -m cpp_reference_finder find 'Namespace::Class::method' \
  --project "$PROJECT_ROOT" --json
```

Query at an exact source position:

```bash
PYTHONPATH="$TOOL/src" python3 -B -m cpp_reference_finder at path/to/file.cpp \
  --line 120 --column 18 --project "$PROJECT_ROOT" --json
```

Use `--include-declaration` when the declaration should be included in the result set. Use `--limit` to keep output compact for AI context.

## Command Reference For Agents

- `find SYMBOL --project ROOT [--include-declaration] [-n N] [--json]`: resolve a symbol by name, then ask clangd for semantic references.
- `at FILE --line L --column C --project ROOT [--json]`: query references at an exact 1-based source position. Prefer this when the edit location is known.
- Shared options: `--compile-commands-dir DIR`, `--no-compile-db` for degraded fallback, `--timeout SECONDS`, `--service-timeout SECONDS`, and `--direct` for debugging without `cpp-clangd-service`.

## JSON Output

The JSON payload has `query`, `symbol`, `position`, `include_declaration`, `reference_count`, and `references`.

- `symbol` is present for `find` and includes `name`, `full_name`, `kind_name`, and definition `location`.
- `position` is the source position used for the clangd reference request.
- Each reference has `path`, `relative_path`, 1-based `line` and `column`, LSP `range`, and `snippet`.

## Failure Handling And Boundaries

- Empty `references` means clangd returned no semantic references for that position. First verify compile database, service readiness, indexing, and whether the cursor position names the intended symbol.
- Name-based `find` can pick the wrong overload or similarly named symbol. Use `at` or a fully qualified symbol when correctness matters.
- This is semantic reference lookup, not text search. It can miss macro-generated uses, inactive preprocessor branches, or files outside the compile database.

## Output Use

Report concrete file paths, line numbers, symbol location, and the most relevant reference snippets. Treat empty results as a clangd/indexing or compile database signal before concluding that no references exist.
