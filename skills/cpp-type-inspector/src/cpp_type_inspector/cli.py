from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from . import __version__
from .core import ProjectConfig, ToolError, inspect_at, inspect_by_symbol
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
            payload = inspect_by_symbol(args.symbol, config, timeout=args.timeout)
        elif args.command == "at":
            payload = inspect_at(args.file, args.line, args.column, config, timeout=args.timeout)
        else:
            parser.print_help()
            return 2
    except ToolError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print_human(payload)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cpp-type-inspector",
        description="Inspect C/C++ expression and symbol types through clangd.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command")

    find = subparsers.add_parser("find", help="inspect by symbol name")
    add_common_args(find)
    find.add_argument("symbol")

    at = subparsers.add_parser("at", help="inspect at a source position")
    add_common_args(at)
    at.add_argument("file")
    at.add_argument("--line", type=int, required=True)
    at.add_argument("--column", type=int, required=True)
    return parser


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("-p", "--project", default=".")
    parser.add_argument("--clangd", default="clangd")
    parser.add_argument("--compile-commands-dir")
    parser.add_argument("--no-compile-db", action="store_true")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--service-timeout", type=float, default=60.0)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--direct", action="store_true", help="run without cpp-clangd-service")


def build_service_payload(args: argparse.Namespace) -> dict[str, Any]:
    payload: dict[str, Any] = {"command": "type_inspect", "timeout": args.timeout}
    if args.command == "find":
        payload["symbol"] = args.symbol
    elif args.command == "at":
        payload.update({"file": args.file, "line": args.line, "column": args.column})
    else:
        raise ServiceClientError(f"unknown command: {args.command}")
    return payload


def print_human(payload: dict[str, Any]) -> None:
    position = payload["position"]
    print(f"position: {format_location(position)}")
    display = payload.get("type_summary", {}).get("display")
    if display:
        print(f"type: {display}")
    hover = payload.get("hover", {}).get("text")
    if hover:
        print("\nHover:")
        print(hover)
    if payload["definitions"]:
        print("\nDefinitions:")
        for item in payload["definitions"]:
            print(f"- {format_location(item)} {item.get('snippet', '')}")
    if payload["type_definitions"]:
        print("\nType definitions:")
        for item in payload["type_definitions"]:
            print(f"- {format_location(item)} {item.get('snippet', '')}")


def format_location(item: dict[str, Any]) -> str:
    path = item.get("relative_path") or item["path"]
    return f"{path}:{item['line']}:{item['column']}"


if __name__ == "__main__":
    raise SystemExit(main())
