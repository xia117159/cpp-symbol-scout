from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from . import __version__
from .core import ProjectConfig, ToolError, find_references_at, find_references_by_symbol
from .service_client import ServiceClientError, request as service_request


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.direct:
        try:
            payload = build_service_payload(args)
            response = service_request(args.project, payload, timeout=args.service_timeout)
            result_payload = response["result"]
            if args.json:
                print(json.dumps(result_payload, ensure_ascii=False, indent=2))
            else:
                print_human(result_payload)
            return 0
        except (OSError, ServiceClientError) as exc:
            print(
                f"cpp-clangd-service is not available: {exc}. "
                "Start it with cpp-clangd-service start or pass --direct.",
                file=sys.stderr,
            )
            return 1
    try:
        config = ProjectConfig.discover(
            args.project,
            clangd=args.clangd,
            compile_commands_dir=args.compile_commands_dir,
            require_compile_db=not args.no_compile_db,
        )
        if args.command == "find":
            result = find_references_by_symbol(
                args.symbol,
                config,
                include_declaration=args.include_declaration,
                limit=args.limit,
                timeout=args.timeout,
            )
        elif args.command == "at":
            result = find_references_at(
                args.file,
                args.line,
                args.column,
                config,
                include_declaration=args.include_declaration,
                limit=args.limit,
                timeout=args.timeout,
            )
        else:
            parser.print_help()
            return 2
    except ToolError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    payload = result.to_dict(config.project_root)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print_human(payload)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cpp-reference-finder",
        description="Find semantic C/C++ symbol references through clangd.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command")

    find = subparsers.add_parser("find", help="find references by symbol name")
    add_common_args(find)
    find.add_argument("symbol", help="symbol name, for example Node::add_child")

    at = subparsers.add_parser("at", help="find references at a source position")
    add_common_args(at)
    at.add_argument("file", help="source file path, absolute or relative to project")
    at.add_argument("--line", type=int, required=True, help="1-based line")
    at.add_argument("--column", type=int, required=True, help="1-based column")

    return parser


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("-p", "--project", default=".", help="project root")
    parser.add_argument("--clangd", default="clangd", help="clangd executable")
    parser.add_argument("--compile-commands-dir", help="directory containing compile_commands.json")
    parser.add_argument("--no-compile-db", action="store_true", help="allow missing compile database")
    parser.add_argument("--include-declaration", action="store_true", help="include declaration in references")
    parser.add_argument("-n", "--limit", type=int, default=50, help="maximum references to print")
    parser.add_argument("--timeout", type=float, default=10.0, help="clangd request timeout")
    parser.add_argument(
        "--service-timeout",
        type=float,
        default=60.0,
        help="client-side timeout when waiting for cpp-clangd-service",
    )
    parser.add_argument("--json", action="store_true", help="print JSON")
    parser.add_argument("--direct", action="store_true", help="run without cpp-clangd-service")


def build_service_payload(args: argparse.Namespace) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "command": "references",
        "include_declaration": args.include_declaration,
        "limit": args.limit,
        "timeout": args.timeout,
    }
    if args.command == "find":
        payload["symbol"] = args.symbol
    elif args.command == "at":
        payload.update({"file": args.file, "line": args.line, "column": args.column})
    else:
        raise ServiceClientError(f"unknown command: {args.command}")
    return payload


def print_human(payload: dict[str, Any]) -> None:
    symbol = payload.get("symbol")
    if symbol:
        print(f"symbol: {symbol['kind_name']} {symbol['full_name']}")
        print(f"definition: {format_location(symbol['location'])}")
    else:
        print(f"position: {format_location(payload['position'])}")
    print(f"references: {payload['reference_count']}")
    for item in payload["references"]:
        print(f"- {format_location(item)}")
        if item.get("snippet"):
            print(f"  {item['snippet']}")


def format_location(item: dict[str, Any]) -> str:
    path = item.get("relative_path") or item["path"]
    return f"{path}:{item['line']}:{item['column']}"


if __name__ == "__main__":
    raise SystemExit(main())
