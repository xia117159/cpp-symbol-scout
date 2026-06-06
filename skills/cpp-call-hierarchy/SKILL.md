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

Use `--limit` to keep call-site output compact. Empty output can mean clangd lacks an indexed call hierarchy for that position; verify the compile database before concluding there are no calls.
