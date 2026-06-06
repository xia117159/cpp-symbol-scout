---
name: cpp-diagnostic-context
description: Use this skill when an agent needs to parse C/C++ compiler output, build logs, Clang/GCC diagnostics, template instantiation traces, include stacks, error locations, warning locations, or source snippets for fixing C++ build failures. Supports C++ 编译错误上下文、模板错误栈、include 栈、构建日志分析。
license: MIT
metadata:
  short-description: Extract C++ compiler error context
  compatibility:
    - codex-cli
    - opencode
---

# cpp-diagnostic-context

Use `cpp-diagnostic-context` to turn noisy C/C++ compiler logs into actionable diagnostic context for AI repair.

## Quick Workflow

```bash
PROJECT_ROOT=/path/to/cpp/project
TOOL=/path/to/cpp-symbol-scout/skills/cpp-diagnostic-context
```

Analyze a build log:

```bash
PYTHONPATH="$TOOL/src" python3 -B -m cpp_diagnostic_context analyze build.log \
  --project "$PROJECT_ROOT" --json
```

Read from stdin:

```bash
make 2>&1 | PYTHONPATH="$TOOL/src" python3 -B -m cpp_diagnostic_context analyze - \
  --project "$PROJECT_ROOT"
```

Use the output to identify exact failing files, compressed include stacks, template instantiation chains, and nearby source snippets before editing.

## Command Reference For Agents

- `analyze LOG --project ROOT [--context-lines N] [-n N] [--json]`: parse a saved Clang/GCC-style compiler log.
- `analyze - --project ROOT [--json]`: read a compiler log from stdin.
- Use `--context-lines` to control source snippet size and `--limit`/`-n` to cap primary diagnostics for AI context.

## JSON Output

The JSON payload has `summary` and `diagnostics`. `summary` includes `diagnostics`, `errors`, `warnings`, and `notes`.

Each diagnostic has `location`, `severity`, `message`, `include_stack`, `template_stack`, `notes`, and `snippet`. Notes are attached to the previous primary diagnostic when possible.

## Failure Handling And Boundaries

- Exit code `1` with no diagnostics means the log did not match supported Clang/GCC diagnostic patterns; inspect raw output for nonstandard build tool formatting.
- The tool extracts primary warnings/errors/fatal errors and nearby context; it does not compile code or validate a fix.
- Relative paths are resolved against `--project` when the source file exists; otherwise they are left as log paths.
