from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .core import (
    CheckReport,
    CheckOptions,
    ProjectConfig,
    ToolError,
    changed_files,
    discover_cpp_files,
    enforce_max_files,
    explicit_files,
    list_checks,
    load_text,
    report_from_log,
    report_to_json,
    run_checks,
)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "check":
        return command_check(args)
    if args.command == "checks":
        return command_checks(args)
    if args.command == "explain":
        return command_explain(args)

    parser.print_help()
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cpp-static-checker",
        description="Run clang-tidy static checks and summarize C/C++ diagnostics.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command")

    check = subparsers.add_parser("check", help="run clang-tidy on selected files")
    add_project_args(check)
    target = check.add_mutually_exclusive_group(required=True)
    target.add_argument("--file", action="append", default=None, help="C/C++ file to check; can be repeated")
    target.add_argument("--changed", action="store_true", help="check git-changed C/C++ files")
    target.add_argument("--all", action="store_true", help="check all C/C++ files under the project")
    check.add_argument("--base", default="HEAD", help="git diff base used by --changed")
    check.add_argument("--no-untracked", action="store_true", help="ignore untracked files with --changed")
    check.add_argument("--source-only", action="store_true", help="ignore headers and check only source files")
    check.add_argument("--max-files", type=int, default=0, help="abort if more files are selected; 0 disables")
    check.add_argument("--checks", help="clang-tidy checks expression, for example bugprone-*,modernize-*")
    check.add_argument("--warnings-as-errors", help="clang-tidy warnings-as-errors expression")
    check.add_argument("--header-filter", help="clang-tidy header filter regex")
    check.add_argument("--system-headers", action="store_true", help="show diagnostics from system headers")
    check.add_argument("--fix", action="store_true", help="apply clang-tidy fix-its")
    check.add_argument("--fix-errors", action="store_true", help="apply fix-its even when compiler errors occur")
    check.add_argument("--config-file", help="path to clang-tidy config file")
    check.add_argument("--extra-arg", action="append", default=[], help="pass --extra-arg to clang-tidy")
    check.add_argument(
        "--extra-arg-before",
        action="append",
        default=[],
        help="pass --extra-arg-before to clang-tidy",
    )
    check.add_argument("--timeout", type=float, default=0.0, help="per-file timeout in seconds; 0 disables")
    check.add_argument("--context-lines", type=int, default=2, help="source context lines around diagnostics")
    check.add_argument("-n", "--limit", type=int, default=100, help="maximum diagnostics to print")
    check.add_argument("--no-quiet", action="store_true", help="do not pass --quiet to clang-tidy")
    check.add_argument("--json", action="store_true", help="print JSON")
    check.add_argument(
        "--fail-on-diagnostics",
        action="store_true",
        help="return non-zero when clang-tidy reports any diagnostic",
    )

    checks = subparsers.add_parser("checks", help="list enabled clang-tidy checks")
    checks.add_argument("-p", "--project", default=".", help="project root")
    checks.add_argument(
        "--clang-tidy",
        default=os.environ.get("CLANG_TIDY", "clang-tidy"),
        help="clang-tidy executable",
    )
    checks.add_argument("--checks", default="*", help="checks expression passed to clang-tidy")
    checks.add_argument("--config-file", help="path to clang-tidy config file")
    checks.add_argument("--json", action="store_true", help="print JSON")

    explain = subparsers.add_parser("explain", help="parse an existing clang-tidy log")
    explain.add_argument("log", help="log file path or '-' for stdin")
    explain.add_argument("-p", "--project", default=".", help="project root")
    explain.add_argument("--context-lines", type=int, default=2)
    explain.add_argument("-n", "--limit", type=int, default=100)
    explain.add_argument("--json", action="store_true")

    return parser


def add_project_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("-p", "--project", default=".", help="project root")
    parser.add_argument(
        "--clang-tidy",
        default=os.environ.get("CLANG_TIDY", "clang-tidy"),
        help="clang-tidy executable",
    )
    parser.add_argument("--compile-commands-dir", help="directory containing compile_commands.json")
    parser.add_argument(
        "--allow-missing-compile-db",
        action="store_true",
        help="run without compile_commands.json using clang-tidy fallback flags",
    )


def command_check(args: argparse.Namespace) -> int:
    if args.limit <= 0:
        print("--limit must be positive", file=sys.stderr)
        return 2
    if args.timeout < 0:
        print("--timeout cannot be negative", file=sys.stderr)
        return 2
    if args.max_files < 0:
        print("--max-files cannot be negative", file=sys.stderr)
        return 2

    try:
        project_root = Path(args.project).expanduser().resolve()
        if not project_root.exists():
            raise ToolError(f"project path does not exist: {project_root}")
        if not project_root.is_dir():
            raise ToolError(f"project path is not a directory: {project_root}")
        files, mode = select_target_files(args)
        files = enforce_max_files(files, args.max_files)
        if not files:
            report = CheckReport(
                project_root=project_root,
                clang_tidy_path=None,
                compile_commands_dir=None,
                files_requested=0,
                file_results=[],
                diagnostics=[],
                elapsed_ms=0.0,
                mode=mode,
            )
        else:
            config = ProjectConfig.discover(
                args.project,
                clang_tidy=args.clang_tidy,
                compile_commands_dir=args.compile_commands_dir,
                require_compile_db=not args.allow_missing_compile_db,
            )
            options = CheckOptions(
                checks=args.checks,
                warnings_as_errors=args.warnings_as_errors,
                header_filter=args.header_filter,
                system_headers=args.system_headers,
                quiet=not args.no_quiet,
                fix=args.fix,
                fix_errors=args.fix_errors,
                config_file=Path(args.config_file).expanduser().resolve() if args.config_file else None,
                extra_args=tuple(args.extra_arg),
                extra_args_before=tuple(args.extra_arg_before),
                timeout=args.timeout,
                context_lines=args.context_lines,
            )
            report = run_checks(config, files, options=options, mode=mode)
    except ToolError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.json:
        print(report_to_json(report, limit=args.limit))
    else:
        print_human_report(report.to_dict(limit=args.limit))

    summary = report.summary()
    if summary["failed_files"]:
        return 1
    if args.fail_on_diagnostics and summary["diagnostics"]:
        return 1
    return 0


def select_target_files(args: argparse.Namespace) -> tuple[list[Path], str]:
    if args.file:
        return explicit_files(args.project, args.file, source_only=args.source_only), "file"
    if args.changed:
        return (
            changed_files(
                args.project,
                base=args.base,
                include_untracked=not args.no_untracked,
                source_only=args.source_only,
            ),
            "changed",
        )
    if args.all:
        return discover_cpp_files(args.project, source_only=args.source_only), "all"
    raise ToolError("select one of --file, --changed, or --all")


def command_checks(args: argparse.Namespace) -> int:
    try:
        payload = list_checks(
            clang_tidy=args.clang_tidy,
            checks=args.checks,
            project_root=args.project,
            config_file=args.config_file,
        )
    except ToolError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"clang-tidy: {payload['clang_tidy']}")
        print(f"checks expression: {payload['checks_expression']}")
        print(f"enabled checks: {payload['enabled_check_count']}")
        for check_name in payload["enabled_checks"]:
            print(f"  {check_name}")
    return 0


def command_explain(args: argparse.Namespace) -> int:
    if args.limit <= 0:
        print("--limit must be positive", file=sys.stderr)
        return 2
    try:
        text = load_text(args.log)
        report = report_from_log(
            text,
            project_root=args.project,
            context_lines=args.context_lines,
        )
    except OSError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.json:
        print(report_to_json(report, limit=args.limit))
    else:
        print_human_report(report.to_dict(limit=args.limit))
    return 0 if not report.diagnostics else 1


def print_human_report(payload: dict[str, Any]) -> None:
    summary = payload["summary"]
    print(f"project: {payload['project_root']}")
    if payload.get("compile_commands_dir"):
        print(f"compile_commands_dir: {payload['compile_commands_dir']}")
    if payload.get("clang_tidy"):
        print(f"clang-tidy: {payload['clang_tidy']}")
    print(
        f"files checked: {summary['files_checked']} "
        f"diagnostics: {summary['diagnostics']} "
        f"errors: {summary['errors']} warnings: {summary['warnings']} notes: {summary['notes']}"
    )
    if summary["failed_files"]:
        print(f"failed clang-tidy invocations: {summary['failed_files']}")
    if summary["unique_checks"]:
        print("checks:")
        for check_name in summary["unique_checks"]:
            print(f"  {check_name}")

    for diagnostic in payload["diagnostics"]:
        location = diagnostic["location"]
        column = f":{location['column']}" if location.get("column") else ""
        check_name = f" [{diagnostic['check_name']}]" if diagnostic.get("check_name") else ""
        path = location.get("relative_path") or location["path"]
        print(f"\n{diagnostic['severity']}: {path}:{location['line']}{column}{check_name}")
        print(diagnostic["message"])
        if diagnostic.get("snippet"):
            print("source:")
            print(diagnostic["snippet"])
        for note in diagnostic["notes"]:
            note_location = note["location"]
            note_path = note_location.get("relative_path") or note_location["path"]
            print(f"note: {note_path}:{note_location['line']} {note['message']}")

    if summary["diagnostics_truncated"]:
        print(f"\ntruncated: returned {summary['diagnostics_returned']} of {summary['diagnostics']} diagnostics")


if __name__ == "__main__":
    raise SystemExit(main())
