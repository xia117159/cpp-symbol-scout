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

## Output Use

Report concrete file paths, line numbers, symbol location, and the most relevant reference snippets. Treat empty results as a clangd/indexing or compile database signal before concluding that no references exist.
