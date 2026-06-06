from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from . import __version__
from .class_members import (
    members_payload_from_symbol_result,
    select_class_symbol_result,
)
from .daemon import (
    DaemonError,
    QueryOptions,
    candidate_source_files,
    document_symbol_query,
    query_with_client,
)
from .lsp import ClangdClient
from .paths import ConfigurationError, ProjectConfig
from .service_client import ServiceClientError, request as service_request


DEFAULT_PROJECT = "."


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "daemon":
        return command_daemon(args)
    if args.command == "start":
        return command_start(args)
    if args.command == "status":
        return command_status(args)
    if args.command == "stop":
        return command_stop(args)
    if args.command == "query":
        return command_query(args)
    if args.command == "members":
        return command_members(args)

    parser.print_help()
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cpp-symbol-scout",
        description="Fast C++ symbol lookup CLI backed by cpp-clangd-service.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    subparsers = parser.add_subparsers(dest="command")

    start = subparsers.add_parser("start", help="start cpp-clangd-service for this project")
    _add_project_args(start)
    start.add_argument("--foreground", action="store_true", help="run service in the foreground")
    start.add_argument("--wait", action="store_true", help="wait until the service answers status")
    start.add_argument("--wait-timeout", type=float, default=15.0, help="seconds to wait with --wait")

    daemon = subparsers.add_parser("daemon", help="run cpp-clangd-service in the foreground")
    _add_project_args(daemon)

    status = subparsers.add_parser("status", help="show cpp-clangd-service status")
    _add_client_project_arg(status)
    status.add_argument("--json", action="store_true", help="print JSON")

    stop = subparsers.add_parser("stop", help="stop cpp-clangd-service")
    _add_client_project_arg(stop)

    query = subparsers.add_parser("query", help="query a class, function, method, or other symbol")
    _add_client_project_arg(query)
    query.add_argument("symbol", help="symbol name, for example Node or EditorNode::save_scene")
    query.add_argument("-n", "--limit", type=int, default=5, help="maximum number of candidates")
    query.add_argument("--timeout", type=float, default=1.0, help="service-side query timeout in seconds")
    query.add_argument(
        "--service-timeout",
        type=float,
        default=60.0,
        help="client-side timeout when waiting for cpp-clangd-service",
    )
    query.add_argument("--json", action="store_true", help="print JSON")
    query.add_argument(
        "--no-implementation",
        action="store_true",
        help="do not resolve function declarations to implementations",
    )
    query.add_argument(
        "--source-only",
        action="store_true",
        help="print only the first result's source snippet",
    )
    query.add_argument(
        "--direct",
        action="store_true",
        help="run one query directly through clangd instead of using cpp-clangd-service",
    )
    query.add_argument("--clangd", default=os.environ.get("CLANGD", "clangd"), help="path to clangd")
    query.add_argument(
        "--compile-commands-dir",
        help="directory containing compile_commands.json or compile_flags.txt",
    )
    query.add_argument(
        "--allow-missing-compile-db",
        action="store_true",
        help="query even when compile_commands.json or compile_flags.txt cannot be found",
    )

    members = subparsers.add_parser("members", help="list class/struct methods, fields, and nested types")
    _add_client_project_arg(members)
    members.add_argument("symbol", help="class or struct name, for example Node or EditorNode")
    members.add_argument("--access", choices=("all", "public", "protected", "private"), default="all")
    members.add_argument("--kind", choices=("all", "method", "field", "type"), default="all")
    members.add_argument("-n", "--limit", type=int, default=200, help="maximum members to print")
    members.add_argument("--candidate-limit", type=int, default=5, help="maximum class candidates to inspect")
    members.add_argument("--timeout", type=float, default=2.0, help="service-side query timeout in seconds")
    members.add_argument(
        "--service-timeout",
        type=float,
        default=60.0,
        help="client-side timeout when waiting for cpp-clangd-service",
    )
    members.add_argument("--json", action="store_true", help="print JSON")
    members.add_argument(
        "--direct",
        action="store_true",
        help="run one query directly through clangd instead of using cpp-clangd-service",
    )
    members.add_argument("--clangd", default=os.environ.get("CLANGD", "clangd"), help="path to clangd")
    members.add_argument(
        "--compile-commands-dir",
        help="directory containing compile_commands.json or compile_flags.txt",
    )
    members.add_argument(
        "--allow-missing-compile-db",
        action="store_true",
        help="query even when compile_commands.json or compile_flags.txt cannot be found",
    )

    return parser


def command_start(args: argparse.Namespace) -> int:
    service_args = _service_project_args("start", args)
    if args.foreground:
        service_args.append("--foreground")
    if args.wait:
        service_args.append("--wait")
    service_args.extend(["--wait-timeout", str(args.wait_timeout)])
    return _run_cpp_clangd_service(service_args)


def command_daemon(args: argparse.Namespace) -> int:
    return _run_cpp_clangd_service(_service_project_args("daemon", args))


def command_status(args: argparse.Namespace) -> int:
    try:
        response = service_request(
            project=args.project,
            payload={"command": "status"},
            timeout=2.0,
        )
    except (OSError, ServiceClientError) as exc:
        print(_service_unavailable_message(args.project, exc), file=sys.stderr)
        return 1

    status = response["status"]
    if args.json:
        print(json.dumps(status, indent=2, ensure_ascii=False))
    else:
        print(f"project: {status['project_root']}")
        print(f"clangd: {status['clangd']}")
        print(f"compile_commands_dir: {status['compile_commands_dir']}")
        print(f"tcp: {status['tcp']}")
        print(f"pid: {status['pid']}")
        print(f"log: {status['log']}")
        print(f"ready: {status['ready']}")
        print(f"uptime_seconds: {status['uptime_seconds']}")
        print(f"symbol_cache_entries: {status.get('symbol_cache_entries', 0)}")
    return 0


def command_stop(args: argparse.Namespace) -> int:
    try:
        service_request(project=args.project, payload={"command": "stop"}, timeout=2.0)
    except (OSError, ServiceClientError) as exc:
        print(_service_unavailable_message(args.project, exc), file=sys.stderr)
        return 1
    print("service stopped")
    return 0


def command_query(args: argparse.Namespace) -> int:
    if args.limit <= 0:
        print("--limit must be positive", file=sys.stderr)
        return 2
    if args.timeout <= 0:
        print("--timeout must be positive", file=sys.stderr)
        return 2

    if args.direct:
        try:
            results = _direct_query(args)
        except (ConfigurationError, DaemonError, RuntimeError) as exc:
            print(str(exc), file=sys.stderr)
            return 1
    else:
        payload = {
            "command": "symbol_query",
            "symbol": args.symbol,
            "limit": args.limit,
            "timeout": args.timeout,
            "resolve_implementation": not args.no_implementation,
        }
        try:
            response = service_request(project=args.project, payload=payload, timeout=args.service_timeout)
        except (OSError, ServiceClientError) as exc:
            print(_service_unavailable_message(args.project, exc), file=sys.stderr)
            return 1
        result_payload = response.get("result") or {}
        results = result_payload.get("results") or []
    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
        return 0 if results else 1

    if args.source_only:
        if not results:
            return 1
        print(results[0]["source"])
        return 0

    _print_human_results(results)
    return 0 if results else 1


def command_members(args: argparse.Namespace) -> int:
    if args.limit <= 0:
        print("--limit must be positive", file=sys.stderr)
        return 2
    if args.candidate_limit <= 0:
        print("--candidate-limit must be positive", file=sys.stderr)
        return 2
    if args.timeout <= 0:
        print("--timeout must be positive", file=sys.stderr)
        return 2

    try:
        if args.direct:
            results = _direct_symbol_query(
                project=args.project,
                symbol=args.symbol,
                limit=args.candidate_limit,
                timeout=args.timeout,
                resolve_implementation=False,
                clangd=args.clangd,
                compile_commands_dir=args.compile_commands_dir,
                allow_missing_compile_db=args.allow_missing_compile_db,
            )
        else:
            payload = {
                "command": "symbol_query",
                "symbol": args.symbol,
                "limit": args.candidate_limit,
                "timeout": args.timeout,
                "resolve_implementation": False,
            }
            response = service_request(args.project, payload=payload, timeout=args.service_timeout)
            result_payload = response.get("result") or {}
            results = result_payload.get("results") or []
        selected = select_class_symbol_result(results)
        if selected is None:
            print(f"no class or struct definition found for {args.symbol}", file=sys.stderr)
            return 1
        payload = members_payload_from_symbol_result(
            selected,
            project_root=args.project,
            access=args.access,
            member_kind=args.kind,
            limit=args.limit,
        )
    except (OSError, ConfigurationError, DaemonError, RuntimeError, ServiceClientError, ValueError) as exc:
        if not args.direct and isinstance(exc, (OSError, ServiceClientError)):
            print(_service_unavailable_message(args.project, exc), file=sys.stderr)
        else:
            print(str(exc), file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        _print_human_members(payload)
    return 0 if payload["members"] else 1


def _print_human_results(results: list[dict[str, Any]]) -> None:
    if not results:
        print("no results")
        return

    for index, result in enumerate(results, start=1):
        location = result["location"]
        print(
            f"[{index}] {result['kind_name']} {result['full_name']} "
            f"({result['resolution']}, {result['elapsed_ms']:.1f} ms)"
        )
        print(f"    {location['path']}:{location['line']}:{location['character']}")
        source = result.get("source") or ""
        if source:
            print(_indent_source(source.rstrip()))
        if index != len(results):
            print()


def _indent_source(source: str) -> str:
    return "\n".join(f"    {line}" if line else "" for line in source.splitlines())


def _direct_query(args: argparse.Namespace) -> list[dict[str, Any]]:
    return _direct_symbol_query(
        project=args.project,
        symbol=args.symbol,
        limit=args.limit,
        timeout=args.timeout,
        resolve_implementation=not args.no_implementation,
        clangd=args.clangd,
        compile_commands_dir=args.compile_commands_dir,
        allow_missing_compile_db=args.allow_missing_compile_db,
    )


def _direct_symbol_query(
    *,
    project: str,
    symbol: str,
    limit: int,
    timeout: float,
    resolve_implementation: bool,
    clangd: str,
    compile_commands_dir: str | None,
    allow_missing_compile_db: bool,
) -> list[dict[str, Any]]:
    config = ProjectConfig.discover(
        project,
        clangd=clangd,
        compile_commands_dir=compile_commands_dir,
        require_compile_db=not allow_missing_compile_db,
    )
    client = ClangdClient(
        clangd_path=config.clangd_path,
        project_root=config.project_root,
        compile_commands_dir=config.compile_commands_dir,
    )
    client.start()
    try:
        warmed_files = _warm_direct_query(client, config.project_root, symbol)
        results = query_with_client(
            client=client,
            project_root=config.project_root,
            symbol=symbol,
            options=QueryOptions(
                limit=limit,
                timeout=timeout,
                resolve_implementation=resolve_implementation,
            ),
        )
        if not results:
            results = document_symbol_query(
                client=client,
                project_root=config.project_root,
                files=warmed_files,
                symbol=symbol,
                options=QueryOptions(
                    limit=limit,
                    timeout=timeout,
                    resolve_implementation=False,
                ),
            )
        return [result.to_dict() for result in results]
    finally:
        client.stop()


def _warm_direct_query(client: ClangdClient, project_root: Path, symbol: str) -> list[Path]:
    opened: list[Path] = []
    for path in candidate_source_files(project_root, symbol):
        try:
            client.open_document(path)
            opened.append(path)
        except Exception:
            continue
    return opened


def _print_human_members(payload: dict[str, Any]) -> None:
    class_info = payload["class"]
    location = class_info["location"]
    class_path = location.get("relative_path") or location["path"]
    print(f"class: {class_info.get('kind_name')} {class_info.get('full_name') or class_info.get('name')}")
    print(f"definition: {class_path}:{location['line']}:{location.get('column') or location.get('character')}")
    summary = payload["summary"]
    print(
        f"members: {summary['returned_count']}/{summary['member_count']} "
        f"methods={summary['methods']} fields={summary['fields']} types={summary['types']} "
        f"access={summary['access_filter']} kind={summary['kind_filter']}"
    )

    last_access = None
    for member in payload["members"]:
        if member["access"] != last_access:
            last_access = member["access"]
            print(f"\n{last_access}:")
        print(f"  - {member['kind']} {member['name']}: {member['declaration']}")


def _service_project_args(command: str, args: argparse.Namespace) -> list[str]:
    service_args = [
        command,
        "--project",
        str(Path(args.project).expanduser()),
        "--clangd",
        args.clangd,
    ]
    if args.compile_commands_dir:
        service_args.extend(["--compile-commands-dir", args.compile_commands_dir])
    if args.allow_missing_compile_db:
        service_args.append("--allow-missing-compile-db")
    return service_args


def _run_cpp_clangd_service(args: list[str]) -> int:
    env = os.environ.copy()
    service_src = _service_source_path()
    if service_src is not None:
        existing = env.get("PYTHONPATH")
        env["PYTHONPATH"] = str(service_src) if not existing else f"{service_src}{os.pathsep}{existing}"
    command = [sys.executable, "-B", "-m", "cpp_clangd_service", *args]
    completed = subprocess.run(command, env=env)
    if completed.returncode != 0 and service_src is None:
        print(
            "cpp-clangd-service is not importable. Install services/cpp-clangd-service "
            "or run it from this repository.",
            file=sys.stderr,
        )
    return completed.returncode


def _service_source_path() -> Path | None:
    repo_root = Path(__file__).resolve().parents[4]
    candidate = repo_root / "services" / "cpp-clangd-service" / "src"
    return candidate if candidate.is_dir() else None


def _service_unavailable_message(project: str, exc: BaseException) -> str:
    project_root = Path(project).expanduser().resolve()
    return (
        f"cpp-clangd-service is not available for {project_root}: {exc}. "
        f"Start it with: cpp-clangd-service start --project {project_root} --wait "
        f"or cpp-symbol-scout start --project {project_root} --wait. "
        "Pass --direct for one-off debugging."
    )


def _add_project_args(parser: argparse.ArgumentParser) -> None:
    _add_client_project_arg(parser)
    parser.add_argument("--clangd", default=os.environ.get("CLANGD", "clangd"), help="path to clangd")
    parser.add_argument(
        "--compile-commands-dir",
        help="directory containing compile_commands.json or compile_flags.txt",
    )
    parser.add_argument(
        "--allow-missing-compile-db",
        action="store_true",
        help="start even when compile_commands.json or compile_flags.txt cannot be found",
    )


def _add_client_project_arg(parser: argparse.ArgumentParser) -> None:
    default_project = os.environ.get("CPP_CLANGD_PROJECT", DEFAULT_PROJECT)
    parser.add_argument(
        "-p",
        "--project",
        default=default_project,
        help=f"project root, default: {default_project}",
    )
