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
from .daemon import (
    DaemonError,
    QueryOptions,
    candidate_source_files,
    client_request,
    document_symbol_query,
    query_with_client,
    run_daemon,
)
from .lsp import ClangdClient
from .paths import ConfigurationError, ProjectConfig, runtime_paths


DEFAULT_PROJECT = "."


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "daemon":
        return run_daemon(args)
    if args.command == "start":
        return command_start(args)
    if args.command == "status":
        return command_status(args)
    if args.command == "stop":
        return command_stop(args)
    if args.command == "query":
        return command_query(args)

    parser.print_help()
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cpp-symbol-scout",
        description="Fast C++ symbol lookup CLI backed by a persistent clangd daemon.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    subparsers = parser.add_subparsers(dest="command")

    start = subparsers.add_parser("start", help="start the clangd-backed daemon")
    _add_project_args(start)
    start.add_argument("--foreground", action="store_true", help="run daemon in the foreground")
    start.add_argument("--wait", action="store_true", help="wait until the daemon answers status")
    start.add_argument("--wait-timeout", type=float, default=15.0, help="seconds to wait with --wait")

    daemon = subparsers.add_parser("daemon", help="run the daemon process")
    _add_project_args(daemon)

    status = subparsers.add_parser("status", help="show daemon status")
    _add_client_project_arg(status)
    status.add_argument("--json", action="store_true", help="print JSON")

    stop = subparsers.add_parser("stop", help="stop the daemon")
    _add_client_project_arg(stop)

    query = subparsers.add_parser("query", help="query a class, function, method, or other symbol")
    _add_client_project_arg(query)
    query.add_argument("symbol", help="symbol name, for example Node or EditorNode::save_scene")
    query.add_argument("-n", "--limit", type=int, default=5, help="maximum number of candidates")
    query.add_argument("--timeout", type=float, default=1.0, help="daemon-side query timeout in seconds")
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
        help="run one query directly through clangd instead of using the daemon",
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

    return parser


def command_start(args: argparse.Namespace) -> int:
    if args.foreground:
        return run_daemon(args)

    try:
        config = ProjectConfig.discover(
            args.project,
            clangd=args.clangd,
            compile_commands_dir=args.compile_commands_dir,
            require_compile_db=not args.allow_missing_compile_db,
        )
    except ConfigurationError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2

    paths = runtime_paths(config.project_root)
    if paths.socket_path.exists():
        try:
            response = client_request(
                project=config.project_root,
                payload={"command": "status"},
                timeout=0.3,
            )
            status = response["status"]
            print(f"daemon already running: {status['tcp']}")
            return 0
        except Exception:
            paths.socket_path.unlink(missing_ok=True)

    command = [
        sys.executable,
        "-m",
        "cpp_symbol_scout",
        "daemon",
        "--project",
        str(config.project_root),
        "--clangd",
        config.clangd_path,
    ]
    if config.compile_commands_dir is not None:
        command.extend(["--compile-commands-dir", str(config.compile_commands_dir)])
    if args.allow_missing_compile_db:
        command.append("--allow-missing-compile-db")

    log = paths.log_path.open("ab")
    proc = subprocess.Popen(
        command,
        cwd=Path.cwd(),
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=log,
        start_new_session=True,
    )
    paths.pid_path.write_text(str(proc.pid), encoding="ascii")

    if args.wait:
        deadline = time.monotonic() + args.wait_timeout
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                response = client_request(
                    project=config.project_root,
                    payload={"command": "status"},
                    timeout=0.5,
                )
                status = response["status"]
                print(f"daemon ready: {status['tcp']}")
                return 0
            except Exception as exc:
                last_error = exc
                time.sleep(0.25)
        print(f"daemon did not become ready within {args.wait_timeout:.1f}s", file=sys.stderr)
        if last_error is not None:
            print(f"last error: {last_error}", file=sys.stderr)
        print(f"log: {paths.log_path}", file=sys.stderr)
        return 1

    print(f"daemon starting: {paths.host}:{paths.port}")
    print(f"log: {paths.log_path}")
    return 0


def command_status(args: argparse.Namespace) -> int:
    try:
        response = client_request(
            project=args.project,
            payload={"command": "status"},
            timeout=2.0,
        )
    except DaemonError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    status = response["status"]
    if args.json:
        print(json.dumps(status, indent=2, ensure_ascii=False))
    else:
        print(f"project: {status['project_root']}")
        print(f"clangd: {status['clangd']}")
        print(f"compile_commands_dir: {status['compile_commands_dir']}")
        print(f"socket: {status['socket']}")
        print(f"tcp: {status['tcp']}")
        print(f"log: {status['log']}")
        print(f"ready: {status['ready']}")
        print(f"uptime_seconds: {status['uptime_seconds']}")
        print(f"cache_entries: {status['cache_entries']}")
    return 0


def command_stop(args: argparse.Namespace) -> int:
    try:
        client_request(project=args.project, payload={"command": "stop"}, timeout=2.0)
    except DaemonError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print("daemon stopped")
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
            "command": "query",
            "symbol": args.symbol,
            "limit": args.limit,
            "timeout": args.timeout,
            "resolve_implementation": not args.no_implementation,
        }
        try:
            response = client_request(project=args.project, payload=payload, timeout=args.timeout + 1.0)
        except DaemonError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        results = response.get("results") or []
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
    config = ProjectConfig.discover(
        args.project,
        clangd=args.clangd,
        compile_commands_dir=args.compile_commands_dir,
        require_compile_db=not args.allow_missing_compile_db,
    )
    client = ClangdClient(
        clangd_path=config.clangd_path,
        project_root=config.project_root,
        compile_commands_dir=config.compile_commands_dir,
    )
    client.start()
    try:
        warmed_files = _warm_direct_query(client, config.project_root, args.symbol)
        results = query_with_client(
            client=client,
            project_root=config.project_root,
            symbol=args.symbol,
            options=QueryOptions(
                limit=args.limit,
                timeout=args.timeout,
                resolve_implementation=not args.no_implementation,
            ),
        )
        if not results:
            results = document_symbol_query(
                client=client,
                project_root=config.project_root,
                files=warmed_files,
                symbol=args.symbol,
                options=QueryOptions(
                    limit=args.limit,
                    timeout=args.timeout,
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
