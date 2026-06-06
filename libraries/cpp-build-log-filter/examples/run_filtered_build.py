#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from pathlib import Path


REPO_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_DIR / "src"
DEFAULT_PROJECT = REPO_DIR / "examples" / "simple-make-project"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from cpp_build_log_filter import FilterOptions, filter_build_log_result  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    project_dir = args.project.resolve()
    if not project_dir.is_dir():
        print(f"project directory does not exist: {project_dir}", file=sys.stderr)
        return 2

    if args.clean:
        clean_result = _run_command(["make", "clean"], project_dir)
        if args.show_raw and clean_result.stdout:
            print("== raw clean output ==")
            print(clean_result.stdout.rstrip())
            print()
        if clean_result.returncode != 0:
            print(f"clean command failed with exit code {clean_result.returncode}", file=sys.stderr)
            return clean_result.returncode if args.preserve_exit_code else 1

    build_result = _run_command(args.command, project_dir)
    options = FilterOptions(
        keep_warnings=args.keep_warnings,
        warning_files=tuple(args.warning_file),
        max_warnings=args.max_warnings,
        include_summary=args.summary,
    )
    filtered = filter_build_log_result(build_result.stdout, options)

    print("== build command ==")
    print(f"cwd: {project_dir}")
    print(f"cmd: {shlex.join(args.command)}")
    print(f"exit code: {build_result.returncode}")
    print()

    if args.show_raw:
        print("== raw build output ==")
        print(build_result.stdout.rstrip() or "<empty>")
        print()

    print("== filtered build output ==")
    print(filtered.text or "<empty>")
    print()

    print("== filter stats ==")
    print(
        "input_lines={input_lines}, output_lines={output_lines}, "
        "errors={errors}, warnings={warnings}, dropped_lines={dropped_lines}".format(
            input_lines=filtered.stats.input_lines,
            output_lines=filtered.stats.output_lines,
            errors=filtered.stats.errors,
            warnings=filtered.stats.warnings,
            dropped_lines=filtered.stats.dropped_lines,
        )
    )

    if args.preserve_exit_code:
        return build_result.returncode
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a C++ build command and print cpp-build-log-filter output.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--project",
        type=Path,
        default=DEFAULT_PROJECT,
        help="Project directory used as the build command cwd.",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Run 'make clean' in the project directory before the build command.",
    )
    warning_group = parser.add_mutually_exclusive_group()
    warning_group.add_argument(
        "--keep-warnings",
        dest="keep_warnings",
        action="store_true",
        help="Keep warning diagnostics in the filtered output.",
    )
    warning_group.add_argument(
        "--drop-warnings",
        dest="keep_warnings",
        action="store_false",
        help="Drop warning diagnostics even when --warning-file is provided.",
    )
    parser.set_defaults(keep_warnings=None)
    parser.add_argument(
        "--warning-file",
        action="append",
        default=[],
        help="Keep warnings only when the diagnostic file basename/path suffix matches this value.",
    )
    parser.add_argument(
        "--max-warnings",
        type=int,
        default=10,
        help="Maximum number of warning diagnostics to keep.",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print cpp-build-log-filter summary before filtered diagnostics.",
    )
    parser.add_argument(
        "--show-raw",
        action="store_true",
        help="Also print the raw captured build output.",
    )
    parser.add_argument(
        "--preserve-exit-code",
        action="store_true",
        help="Exit with the build command exit code.",
    )
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="Build command after '--'. Defaults to 'make'.",
    )
    args = parser.parse_args(argv)
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]
    if not args.command:
        args.command = ["make"]
    return args


def _run_command(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
        check=False,
    )


if __name__ == "__main__":
    raise SystemExit(main())
