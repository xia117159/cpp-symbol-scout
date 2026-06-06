---
name: cpp-include-finder
description: Use this skill when an agent needs to find the correct C/C++ header to include for a type, class, struct, enum, typedef, or using alias in a large C++ project. Also use before adding #include lines, resolving missing type declarations, or helping AI code generation locate declaration headers. Supports C++ 头文件查找、类型声明位置、include 推荐。
license: MIT
metadata:
  short-description: Find C++ declaration headers
  compatibility:
    - codex-cli
    - opencode
---

# cpp-include-finder

Use `cpp-include-finder` to locate likely header files for C/C++ type declarations. It is a standalone Python CLI and does not depend on clangd or `cpp-symbol-scout`.

## When To Use

- The user asks which header should be included for a type.
- You are adding or fixing `#include` lines in C/C++ code.
- A compile error says a class, struct, enum, typedef, or alias is undeclared.
- You need fast header candidates before using deeper semantic tools.

Do not use it for function implementation lookup; use a symbol lookup tool for that.

## Quick Workflow

Set paths explicitly:

```bash
PROJECT_ROOT=/path/to/cpp/project
FINDER=/path/to/cpp-symbol-scout/skills/cpp-include-finder
```

One-off query from this repository:

```bash
PYTHONPATH="$FINDER/src" python3 -B -m include_finder find 'TypeName' --project "$PROJECT_ROOT" -n 5
```

Machine-readable query:

```bash
PYTHONPATH="$FINDER/src" python3 -B -m include_finder find 'Namespace::TypeName' \
  --project "$PROJECT_ROOT" -n 5 --json
```

For repeated queries, build an index first:

```bash
PYTHONPATH="$FINDER/src" python3 -B -m include_finder build-index \
  --project "$PROJECT_ROOT" --output /tmp/include-finder-index.json

PYTHONPATH="$FINDER/src" python3 -B -m include_finder find 'TypeName' \
  --index /tmp/include-finder-index.json --json
```

If declarations live outside headers, add `--all-files`.

## Command Reference For Agents

- `find SYMBOL --project ROOT [-I INCLUDE_ROOT] [-n N] [--json]`: scan headers and return declaration candidates for a type, enum, typedef, or alias.
- `find SYMBOL --index INDEX --json`: reuse a saved index for fast repeated lookups.
- `find SYMBOL --project ROOT --save-index INDEX`: perform a lookup and save the generated index for later queries.
- `build-index --project ROOT -o INDEX [--all-files] [--json]`: pre-scan a project and write a reusable declaration index.
- Use repeated `-I DIR` when project include paths differ from the repository root. Use `--all-files` only when declarations are known to live in `.cpp`, `.ipp`, or `.inl` files.

## JSON Output

`find --json` returns a list of declaration candidates. Each item has `name`, `qualified_name`, `kind`, `path`, `line`, `column`, `include`, `is_definition`, and `snippet`.

`build-index --json` returns `project_root`, `declarations`, and `output`. The index file itself contains `project_root` and a `declarations` array with the same candidate fields.

## Failure Handling

- `find` exits `1` and prints an empty JSON list or "no declarations found" when no candidate matches. Treat that as "not found by static scan", not proof that the type is absent.
- If a likely declaration is missing, rerun with more specific namespace qualification, add `-I` include roots, or add `--all-files`.
- Prefer a result whose `qualified_name` matches the requested type, `is_definition` is true, and `include` is a project-relative quoted include path.

## Output Interpretation

Prefer the first result when:

- `is_definition` is `true`;
- `qualified_name` matches the requested type or namespace-qualified type;
- `include` is project-relative and suitable for a quoted include.

Return the include recommendation and declaration location to the user, for example:

```text
#include "scene/main/node.h"
scene/main/node.h:54
```

## Boundaries

This is a static declaration scanner, not a full C++ compiler. Treat macro-generated declarations and heavy conditional compilation results as candidates that may need compile validation.
