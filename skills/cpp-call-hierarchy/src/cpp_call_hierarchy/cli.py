from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from . import __version__
from .core import ProjectConfig, ToolError, inspect_call_hierarchy_at, inspect_call_hierarchy_by_symbol
from .service_client import ServiceClientError, request as service_request


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    incoming = args.incoming or not args.outgoing
    outgoing = args.outgoing or not args.incoming
    if not args.direct:
        try:
            payload = build_service_payload(args, incoming=incoming, outgoing=outgoing)
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
            payload = inspect_call_hierarchy_by_symbol(
                args.symbol,
                config,
                incoming=incoming,
                outgoing=outgoing,
                limit=args.limit,
                timeout=args.timeout,
            )
        elif args.command == "at":
            payload = inspect_call_hierarchy_at(
                args.file,
                args.line,
                args.column,
                config,
                incoming=incoming,
                outgoing=outgoing,
                limit=args.limit,
                timeout=args.timeout,
            )
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
        prog="cpp-call-hierarchy",
        description="Inspect C/C++ incoming and outgoing calls through clangd.",
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
    parser.add_argument("--incoming", action="store_true", help="show incoming calls")
    parser.add_argument("--outgoing", action="store_true", help="show outgoing calls")
    parser.add_argument("-n", "--limit", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--service-timeout", type=float, default=60.0)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--direct", action="store_true", help="run without cpp-clangd-service")


def build_service_payload(args: argparse.Namespace, *, incoming: bool, outgoing: bool) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "command": "call_hierarchy",
        "incoming": incoming,
        "outgoing": outgoing,
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
    item = payload["item"]
    print(f"item: {item['kind_name']} {item['name']} {format_location(item['location'])}")
    print(f"incoming: {len(payload['incoming'])}")
    for call in payload["incoming"]:
        caller = call["from"]
        print(f"- from {caller['name']} {format_location(caller['location'])}")
        for site in call["call_sites"]:
            print(f"  call site {format_location(site)} {site.get('snippet', '')}")
    print(f"outgoing: {len(payload['outgoing'])}")
    for call in payload["outgoing"]:
        callee = call["to"]
        print(f"- to {callee['name']} {format_location(callee['location'])}")
        for site in call["call_sites"]:
            print(f"  call site {format_location(site)} {site.get('snippet', '')}")


def format_location(item: dict[str, Any]) -> str:
    path = item.get("relative_path") or item["path"]
    return f"{path}:{item['line']}:{item['column']}"


if __name__ == "__main__":
    raise SystemExit(main())
