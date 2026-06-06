from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

from . import __version__
from .core import (
    ProjectConfig,
    SemanticService,
    ServiceError,
    endpoint_responds,
    recv_framed,
    runtime_paths,
    send_framed,
    send_request,
)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "start":
        return command_start(args)
    if args.command == "daemon":
        return command_daemon(args)
    if args.command == "status":
        return command_status(args)
    if args.command == "stop":
        return command_stop(args)
    parser.print_help()
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cpp-clangd-service",
        description="Persistent clangd service for C++ AI tooling.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command")

    start = subparsers.add_parser("start", help="start service")
    add_project_args(start)
    start.add_argument("--foreground", action="store_true")
    start.add_argument("--wait", action="store_true")
    start.add_argument("--wait-timeout", type=float, default=20.0)

    daemon = subparsers.add_parser("daemon", help="run service in foreground")
    add_project_args(daemon)

    status = subparsers.add_parser("status", help="show service status")
    status.add_argument("-p", "--project", default=".")
    status.add_argument("--json", action="store_true")

    stop = subparsers.add_parser("stop", help="stop service")
    stop.add_argument("-p", "--project", default=".")

    return parser


def add_project_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("-p", "--project", default=".")
    parser.add_argument("--clangd", default=os.environ.get("CLANGD", "clangd"))
    parser.add_argument("--compile-commands-dir")
    parser.add_argument("--allow-missing-compile-db", action="store_true")


def command_start(args: argparse.Namespace) -> int:
    if args.foreground:
        return command_daemon(args)
    try:
        config = ProjectConfig.discover(
            args.project,
            clangd=args.clangd,
            compile_commands_dir=args.compile_commands_dir,
            require_compile_db=not args.allow_missing_compile_db,
        )
    except ServiceError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2
    if endpoint_responds(config.project_root):
        status = send_request(config.project_root, {"command": "status"}, timeout=1.0)["status"]
        print(f"service already running: {status['tcp']}")
        return 0
    paths = runtime_paths(config.project_root)
    command = [
        sys.executable,
        "-m",
        "cpp_clangd_service",
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
        while time.monotonic() < deadline:
            if endpoint_responds(config.project_root):
                status = send_request(config.project_root, {"command": "status"}, timeout=1.0)["status"]
                print(f"service ready: {status['tcp']}")
                return 0
            time.sleep(0.25)
        print(f"service did not become ready within {args.wait_timeout:.1f}s", file=sys.stderr)
        print(f"log: {paths.log_path}", file=sys.stderr)
        return 1
    print(f"service starting: {paths.host}:{paths.port}")
    print(f"log: {paths.log_path}")
    return 0


def command_daemon(args: argparse.Namespace) -> int:
    try:
        config = ProjectConfig.discover(
            args.project,
            clangd=args.clangd,
            compile_commands_dir=args.compile_commands_dir,
            require_compile_db=not args.allow_missing_compile_db,
        )
    except ServiceError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2
    paths = runtime_paths(config.project_root)
    service = SemanticService(config, paths)
    if endpoint_responds(config.project_root):
        print(f"service already running: {paths.host}:{paths.port}", file=sys.stderr)
        return 0
    try:
        service.start()
    except Exception as exc:
        print(f"failed to start clangd: {exc}", file=sys.stderr)
        return 1
    stop_event = threading.Event()

    def handle_signal(_signum: int, _frame: object) -> None:
        stop_event.set()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((paths.host, paths.port))
        server.listen(32)
        server.settimeout(0.25)
        paths.pid_path.write_text(str(os.getpid()), encoding="ascii")
        while not stop_event.is_set():
            try:
                conn, _ = server.accept()
            except socket.timeout:
                continue
            threading.Thread(target=handle_connection, args=(service, conn, stop_event), daemon=True).start()
    finally:
        server.close()
        service.stop()
        paths.pid_path.unlink(missing_ok=True)
    return 0


def handle_connection(service: SemanticService, conn: socket.socket, stop_event: threading.Event) -> None:
    with conn:
        try:
            payload = recv_framed(conn)
            response = service.handle(payload)
            if payload.get("command") == "stop":
                stop_event.set()
        except Exception as exc:
            response = {"ok": False, "error": str(exc)}
        send_framed(conn, response)


def command_status(args: argparse.Namespace) -> int:
    try:
        response = send_request(args.project, {"command": "status"}, timeout=2.0)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    status = response["status"]
    if args.json:
        print(json.dumps(status, ensure_ascii=False, indent=2))
    else:
        print(f"project: {status['project_root']}")
        print(f"clangd: {status['clangd']}")
        print(f"compile_commands_dir: {status['compile_commands_dir']}")
        print(f"tcp: {status['tcp']}")
        print(f"pid: {status['pid']}")
        print(f"log: {status['log']}")
        print(f"ready: {status['ready']}")
        print(f"uptime_seconds: {status['uptime_seconds']}")
    return 0


def command_stop(args: argparse.Namespace) -> int:
    try:
        send_request(args.project, {"command": "stop"}, timeout=2.0)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print("service stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
