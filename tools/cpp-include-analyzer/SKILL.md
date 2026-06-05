---
name: cpp-include-analyzer
description: Use this skill when an agent needs to analyze C/C++ include dependencies, fan-in/fan-out, include coupling, duplicate includes, unresolved includes, include cycles, or build-cost risk in a large C++ project. Also use before include refactoring or when reviewing header dependency impact. Supports C++ include 图分析、耦合分析、编译成本风险。
license: MIT
metadata:
  short-description: Analyze C++ include graphs
  compatibility:
    - codex-cli
    - opencode
---

# cpp-include-analyzer

Use `cpp-include-analyzer` to inspect C/C++ include graphs and identify coupling or build-cost risks. It is a standalone Python CLI and does not depend on clangd, `cpp-symbol-scout`, or `cpp-include-finder`.

## When To Use

- The user asks about include coupling, fan-in/fan-out, or header dependency cost.
- You are reviewing whether adding an include may affect a large part of a project.
- You need to inspect who includes a file or what a file includes.
- You are looking for duplicate includes, unresolved includes, or include cycles.

Do not use it to prove an include is removable; that requires compile validation or an include-cleaner style tool.

## Quick Workflow

Set paths explicitly:

```bash
PROJECT_ROOT=/path/to/cpp/project
ANALYZER=/path/to/cpp-symbol-scout/tools/cpp-include-analyzer
```

Analyze a project:

```bash
PYTHONPATH="$ANALYZER/src" python3 -B -m include_analyzer analyze \
  --project "$PROJECT_ROOT" --limit 20
```

JSON summary for automation:

```bash
PYTHONPATH="$ANALYZER/src" python3 -B -m include_analyzer analyze \
  --project "$PROJECT_ROOT" --limit 20 --json
```

Inspect one file:

```bash
PYTHONPATH="$ANALYZER/src" python3 -B -m include_analyzer file path/to/file.h \
  --project "$PROJECT_ROOT" --json
```

If `compile_commands.json` is noisy, unavailable, or too slow to process, add `--no-compile-commands`.

## Output Interpretation

- `fan_in`: project files that include the target; high values indicate broad rebuild impact.
- `fan_out`: project headers included by the target; high values indicate dependency surface.
- `unresolved_edges`: includes that were not resolved against the project and include roots.
- `duplicate_include_files`: files with repeated include directives.
- `cycles`: strongly connected include components.
- `hotspots`: files ranked by `fan_in * 3 + fan_out`.

For code review, report concrete file paths and counts rather than broad conclusions. Recommend compile validation before removing or rewriting includes.

## Boundaries

This tool performs static include graph analysis. It does not run the preprocessor and does not know whether an include is semantically necessary.

