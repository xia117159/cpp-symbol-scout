from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .finder import build_index, find_declarations, load_index, save_index


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "build-index":
        return command_build_index(args)
    if args.command == "find":
        return command_find(args)

    parser.print_help()
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="include-finder",
        description="Find likely C++ header files for type declarations.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command")

    build = subparsers.add_parser("build-index", help="scan a project and write a declaration index")
    add_project_args(build)
    build.add_argument("-o", "--output", required=True, help="index JSON output path")
    build.add_argument("--json", action="store_true", help="print index summary as JSON")

    find = subparsers.add_parser("find", help="find declarations for a type or alias")
    add_project_args(find)
    find.add_argument("symbol", help="type name, for example Node or std::string")
    find.add_argument("--index", help="read a previously generated index JSON")
    find.add_argument("--save-index", help="write the generated index JSON")
    find.add_argument("-n", "--limit", type=int, default=10, help="maximum number of results")
    find.add_argument("--json", action="store_true", help="print JSON results")

    return parser


def add_project_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("-p", "--project", default=".", help="project root")
    parser.add_argument(
        "-I",
        "--include-root",
        action="append",
        default=[],
        help="include root used to derive #include paths; can be repeated",
    )
    parser.add_argument(
        "--all-files",
        action="store_true",
        help="scan source files as well as headers",
    )


def command_build_index(args: argparse.Namespace) -> int:
    index = build_index(
        args.project,
        include_roots=args.include_root,
        all_files=args.all_files,
    )
    save_index(index, args.output)
    summary = {
        "project_root": index.project_root,
        "declarations": len(index.declarations),
        "output": str(Path(args.output).expanduser().resolve()),
    }
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"indexed {summary['declarations']} declarations")
        print(f"wrote {summary['output']}")
    return 0


def command_find(args: argparse.Namespace) -> int:
    if args.limit <= 0:
        print("--limit must be positive", file=sys.stderr)
        return 2

    if args.index:
        index = load_index(args.index)
    else:
        index = build_index(
            args.project,
            include_roots=args.include_root,
            all_files=args.all_files,
        )
        if args.save_index:
            save_index(index, args.save_index)

    results = find_declarations(index, args.symbol, limit=args.limit)
    if args.json:
        print(json.dumps([item.to_dict() for item in results], ensure_ascii=False, indent=2))
    else:
        print_human(args.symbol, results)
    return 0 if results else 1


def print_human(symbol: str, results: list[Any]) -> None:
    if not results:
        print(f"no declarations found for {symbol}")
        return
    for index, result in enumerate(results, start=1):
        definition = "definition" if result.is_definition else "declaration"
        print(f"[{index}] {result.kind} {result.qualified_name} ({definition})")
        print(f"    #include \"{result.include}\"")
        print(f"    {result.path}:{result.line}:{result.column}")
        if result.snippet:
            first_line = result.snippet.splitlines()[0].strip()
            print(f"    {first_line}")

