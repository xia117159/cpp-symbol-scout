---
name: cpp-static-checker
description: Use this skill when an agent needs clang-tidy-backed C/C++ static analysis, changed-file checks, rule diagnostics, warning summaries, fix-it signal detection, or AI-friendly static check reports. Also use before or after C++ edits to catch bugprone, performance, readability, modernize, and project .clang-tidy issues.
license: MIT
metadata:
  short-description: Run clang-tidy static checks
  compatibility:
    - codex-cli
    - opencode
---

# cpp-static-checker

Use `cpp-static-checker` to run `clang-tidy` on selected C/C++ files and return compact diagnostics with source snippets. Prefer it when checking AI-generated C++ edits, validating a refactor, comparing changed files against project rules, or parsing an existing clang-tidy log.

## Operating Rules

- Confirm the C/C++ project root and `compile_commands.json` first. Pass `--compile-commands-dir` when the database is under `build/`, `out/`, or another build directory.
- Prefer `check --changed` for routine AI edits. Use `--file` for targeted checks and `--all` only when the project is small or the user asks for a full scan.
- Keep output compact with `--json -n 50` for AI context. Report concrete file paths, lines, check names, and snippets.
- Do not pass `--fix` unless the user explicitly wants clang-tidy to edit files. First run without fixes, inspect diagnostics, then rerun with `--fix` when appropriate.
- Use `--checks` to narrow noisy projects, for example `bugprone-*,performance-*,modernize-*`.
- If no files are selected by `--changed`, say that no changed C/C++ files were found rather than treating it as a code-quality result.

## Quick Workflow

Set variables explicitly:

```bash
PROJECT_ROOT=/path/to/cpp/project
TOOL=/path/to/cpp-symbol-scout/skills/cpp-static-checker
```

If the CLI is installed:

```bash
cpp-static-checker check --project "$PROJECT_ROOT" --changed --json -n 50
```

If using this skill repository without installing the package:

```bash
PYTHONPATH="$TOOL/src" python3 -B -m cpp_static_checker check \
  --project "$PROJECT_ROOT" --changed --json -n 50
```

Useful variants:

```bash
cpp-static-checker check --project "$PROJECT_ROOT" --file src/foo.cpp --json
cpp-static-checker check --project "$PROJECT_ROOT" --changed --base HEAD~1 --max-files 40
cpp-static-checker check --project "$PROJECT_ROOT" --all --source-only --checks 'bugprone-*,performance-*'
cpp-static-checker check --project "$PROJECT_ROOT" --file src/foo.cpp --fix
cpp-static-checker checks --project "$PROJECT_ROOT" --checks 'modernize-*'
cpp-static-checker explain clang-tidy.log --project "$PROJECT_ROOT" --json
```

## Command Reference For Agents

- `check --project ROOT --changed [--base REV] [--json]`: run clang-tidy on changed C/C++ files. This is the default choice after AI edits.
- `check --project ROOT --file PATH [--file PATH...] [--json]`: run targeted checks on specific files.
- `check --project ROOT --all [--source-only] [--max-files N]`: scan project files; use sparingly on large repos.
- `checks --project ROOT [--checks EXPR] [--json]`: ask clang-tidy which checks are enabled by config and command-line expressions.
- `explain LOG --project ROOT [--json]`: parse an existing clang-tidy log without running clang-tidy.
- Important options: `--compile-commands-dir DIR`, `--checks EXPR`, `--warnings-as-errors EXPR`, `--header-filter REGEX`, `--system-headers`, `--timeout SECONDS`, `--context-lines N`, `--limit N`, and `--fail-on-diagnostics`.

## Output Use

For JSON output, read `summary` first, then inspect `diagnostics`. Each diagnostic includes:

- `location`: absolute and project-relative file path, line, and column.
- `severity`: `warning`, `error`, `fatal error`, or standalone `note`.
- `check_name`: the clang-tidy rule when present.
- `snippet`: nearby source context.
- `notes`: attached clang-tidy notes.
- `has_fixit_hint`: whether the diagnostic text suggests a fix-it is available.

`check --json` also includes `files`, where each item records the checked file, clang-tidy command, exit code, elapsed time, timeout flag, and per-file error message. `summary.diagnostics_truncated` tells you whether `--limit` hid additional diagnostics.

`checks --json` reports enabled checks from clang-tidy. `explain --json` returns the same diagnostic shape as `check`, but without running clang-tidy.

## Failure Handling And Boundaries

- `--changed` selecting zero C/C++ files is not a clean static-analysis result; say no changed C/C++ files were selected.
- A nonzero clang-tidy exit code can mean diagnostics, compiler errors, bad flags, timeout, or tool failure. Check `files[].exit_code`, `files[].timed_out`, and `files[].error_message`.
- Do not use `--fix` or `--fix-errors` unless the user explicitly wants clang-tidy to edit files. Run once without fixes first.
- If compile commands are missing, prefer generating or locating `compile_commands.json`; use `--allow-missing-compile-db` only for degraded fallback.

When combining with other skills:

- Use `$cpp-symbol-scout` to inspect referenced APIs or implementations behind a diagnostic.
- Use `$cpp-type-inspector` when a clang-tidy warning depends on exact C++ type behavior.
- Use `$cpp-reference-finder` or `$cpp-call-hierarchy` before changing public functions flagged by clang-tidy.
- Use `$cpp-diagnostic-context` for compiler/build logs; use this skill for clang-tidy runs or clang-tidy logs.

## Install Or Locate The CLI

When the command is missing, first check whether the current directory is this skill directory. If it is, run through `PYTHONPATH=src`. Otherwise locate the installed skill directory in common Codex/OpenCode locations:

```bash
find ~/.codex/skills ~/.config/opencode/skills ~/.claude/skills ~/.agents/skills \
  -maxdepth 2 -path '*/cpp-static-checker/SKILL.md' 2>/dev/null
```

After locating the skill repository, either use `PYTHONPATH="$TOOL/src"` or install it:

```bash
python3 -m pip install -e "$TOOL"
```
