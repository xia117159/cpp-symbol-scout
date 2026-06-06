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
