from __future__ import annotations

import argparse
import sys
from typing import Any

from . import __version__
from .core import analyze_log, load_log, report_to_json


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command != "analyze":
        parser.print_help()
        return 2

    try:
        text = load_log(args.log)
        report = analyze_log(
            text,
            project_root=args.project,
            context_lines=args.context_lines,
            limit=args.limit,
        )
    except OSError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.json:
        print(report_to_json(report))
    else:
        print_human(report.to_dict())
    return 0 if report.diagnostics else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cpp-diagnostic-context",
        description="Extract actionable C/C++ compiler diagnostic context.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command")
    analyze = subparsers.add_parser("analyze", help="analyze compiler log")
    analyze.add_argument("log", help="log file path or '-' for stdin")
    analyze.add_argument("-p", "--project", default=".", help="project root")
    analyze.add_argument("--context-lines", type=int, default=2)
    analyze.add_argument("-n", "--limit", type=int, default=50)
    analyze.add_argument("--json", action="store_true")
    return parser


def print_human(payload: dict[str, Any]) -> None:
    summary = payload["summary"]
    print(
        f"diagnostics: {summary['diagnostics']} "
        f"errors: {summary['errors']} warnings: {summary['warnings']} notes: {summary['notes']}"
    )
    for diagnostic in payload["diagnostics"]:
        location = diagnostic["location"]
        column = f":{location['column']}" if location.get("column") else ""
        print(f"\n{diagnostic['severity']}: {location['path']}:{location['line']}{column}")
        print(diagnostic["message"])
        if diagnostic["include_stack"]:
            print("include stack:")
            for item in diagnostic["include_stack"]:
                print(f"  {item['path']}:{item['line']}")
        if diagnostic["template_stack"]:
            print("template stack:")
            for item in diagnostic["template_stack"]:
                print(f"  {item}")
        if diagnostic["snippet"]:
            print("source:")
            print(diagnostic["snippet"])
        for note in diagnostic["notes"]:
            note_location = note["location"]
            print(f"note: {note_location['path']}:{note_location['line']} {note['message']}")


if __name__ == "__main__":
    raise SystemExit(main())
