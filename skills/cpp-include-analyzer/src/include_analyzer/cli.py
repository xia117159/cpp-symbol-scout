from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from . import __version__
from .analyzer import analyze_project, file_report, summarize_analysis


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "analyze":
        return command_analyze(args)
    if args.command == "file":
        return command_file(args)

    parser.print_help()
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="include-analyzer",
        description="Analyze C++ include graph coupling and build-cost risk.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command")

    analyze = subparsers.add_parser("analyze", help="analyze the project include graph")
    add_project_args(analyze)
    analyze.add_argument("--limit", type=int, default=20, help="number of top results to print")
    analyze.add_argument("--json", action="store_true", help="print JSON")

    file_parser = subparsers.add_parser("file", help="show include details for one file")
    add_project_args(file_parser)
    file_parser.add_argument("file", help="file path, absolute or relative to project root")
    file_parser.add_argument("--json", action="store_true", help="print JSON")

    return parser


def add_project_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("-p", "--project", default=".", help="project root")
    parser.add_argument(
        "-I",
        "--include-root",
        action="append",
        default=[],
        help="include root used to resolve includes; can be repeated",
    )
    parser.add_argument(
        "--no-compile-commands",
        action="store_true",
        help="do not infer include roots from compile_commands.json",
    )


def command_analyze(args: argparse.Namespace) -> int:
    if args.limit <= 0:
        print("--limit must be positive", file=sys.stderr)
        return 2
    analysis = analyze_project(
        args.project,
        include_roots=args.include_root,
        use_compile_commands=not args.no_compile_commands,
    )
    if args.json:
        payload = analysis.to_dict()
        payload["summary"] = summarize_analysis(analysis, limit=args.limit)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print_summary(analysis, limit=args.limit)
    return 0


def command_file(args: argparse.Namespace) -> int:
    analysis = analyze_project(
        args.project,
        include_roots=args.include_root,
        use_compile_commands=not args.no_compile_commands,
    )
    report = file_report(analysis, args.file)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_file_report(report)
    return 0


def print_summary(analysis: Any, *, limit: int) -> None:
    summary = summarize_analysis(analysis, limit=limit)
    print(f"project: {analysis.project_root}")
    print(f"files scanned: {summary['files_scanned']}")
    print(f"include edges: {summary['include_edges']}")
    print(f"resolved edges: {summary['resolved_edges']}")
    print(f"unresolved edges: {summary['unresolved_edges']}")
    print(f"duplicate include files: {summary['duplicate_include_files']}")
    print(f"cycles: {summary['cycles']}")

    print("\nTop fan-in:")
    for item in summary["top_fan_in"]:
        print(f"  {item['count']:5d}  {item['path']}")

    print("\nTop fan-out:")
    for item in summary["top_fan_out"]:
        print(f"  {item['count']:5d}  {item['path']}")

    print("\nHotspots:")
    for item in summary["hotspots"]:
        print(
            f"  score={item['score']:5d} fan_in={item['fan_in']:4d} "
            f"fan_out={item['fan_out']:4d}  {item['path']}"
        )


def print_file_report(report: dict[str, Any]) -> None:
    print(f"file: {report['file']}")
    print(f"fan_in: {report['fan_in']}")
    print(f"fan_out: {report['fan_out']}")

    print("\nIncludes:")
    for edge in report["includes"]:
        resolved = edge["resolved"] or "unresolved"
        marker = "<>" if edge["is_system"] else '""'
        print(f"  line {edge['line']:4d} {marker} {edge['include']} -> {resolved}")

    print("\nIncluded by:")
    for edge in report["included_by"]:
        print(f"  {edge['source']}:{edge['line']}")

    if report["duplicate_includes"]:
        print("\nDuplicate includes:")
        for duplicate in report["duplicate_includes"]:
            lines = ", ".join(str(line) for line in duplicate["lines"])
            print(f"  {duplicate['include']} at lines {lines}")

