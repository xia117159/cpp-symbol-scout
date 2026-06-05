from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .lsp import ClangdClient, LspError
from .models import FUNCTIONLIKE_KINDS, Location, QueryResult, Range, SymbolCandidate
from .paths import ConfigurationError, ProjectConfig, runtime_paths
from .snippets import extract_source


class DaemonError(RuntimeError):
    """Raised for daemon protocol or lifecycle errors."""


@dataclass(frozen=True)
class QueryOptions:
    limit: int = 5
    timeout: float = 1.0
    resolve_implementation: bool = True


class SymbolDaemon:
    def __init__(self, config: ProjectConfig) -> None:
        self.config = config
        self.paths = runtime_paths(config.project_root)
        self.client = ClangdClient(
            clangd_path=config.clangd_path,
            project_root=config.project_root,
            compile_commands_dir=config.compile_commands_dir,
            log_file=self.paths.log_path,
        )
        self._cache: dict[tuple[str, int, bool], list[QueryResult]] = {}
        self._cache_lock = threading.Lock()
        self._ready_since: float | None = None

    def start(self) -> None:
        self.client.start()
        self._ready_since = time.monotonic()

    def stop(self) -> None:
        self.client.stop()

    def status(self) -> dict[str, Any]:
        return {
            "project_root": str(self.config.project_root),
            "clangd": self.config.clangd_path,
            "compile_commands_dir": str(self.config.compile_commands_dir)
            if self.config.compile_commands_dir
            else None,
            "socket": str(self.paths.socket_path),
            "tcp": f"{self.paths.host}:{self.paths.port}",
            "log": str(self.paths.log_path),
            "ready": self._ready_since is not None,
            "uptime_seconds": round(time.monotonic() - self._ready_since, 3)
            if self._ready_since
            else 0,
            "cache_entries": len(self._cache),
        }

    def query(self, symbol: str, options: QueryOptions) -> list[QueryResult]:
        started = time.perf_counter()
        deadline = started + options.timeout
        cache_key = (symbol, options.limit, options.resolve_implementation)
        with self._cache_lock:
            cached = self._cache.get(cache_key)
        if cached is not None:
            elapsed = (time.perf_counter() - started) * 1000
            return [_replace_elapsed(result, elapsed) for result in cached]

        workspace_budget = max(0.01, min(options.timeout * 0.65, deadline - time.perf_counter()))
        results = query_with_client(
            client=self.client,
            project_root=self.config.project_root,
            symbol=symbol,
            options=options,
            started=started,
            deadline=deadline,
            workspace_budget=workspace_budget,
        )
        if not results and time.perf_counter() < deadline:
            results = document_symbol_query(
                client=self.client,
                project_root=self.config.project_root,
                files=candidate_source_files(self.config.project_root, symbol),
                symbol=symbol,
                options=QueryOptions(
                    limit=options.limit,
                    timeout=max(0.01, deadline - time.perf_counter()),
                    resolve_implementation=False,
                ),
            )

        with self._cache_lock:
            self._cache[cache_key] = results
        elapsed = (time.perf_counter() - started) * 1000
        return [_replace_elapsed(result, elapsed) for result in results]


def run_daemon(args: argparse.Namespace) -> int:
    try:
        config = ProjectConfig.discover(
            args.project,
            clangd=args.clangd,
            compile_commands_dir=args.compile_commands_dir,
            require_compile_db=not args.allow_missing_compile_db,
        )
    except ConfigurationError as exc:
        print(f"cpp-symbol-scout daemon configuration error: {exc}", file=sys.stderr)
        return 2

    daemon = SymbolDaemon(config)
    paths = daemon.paths

    if _endpoint_responds(paths.host, paths.port):
        print(f"cpp-symbol-scout daemon already running: {paths.host}:{paths.port}", file=sys.stderr)
        return 0
    if paths.socket_path.exists():
        paths.socket_path.unlink()

    try:
        daemon.start()
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
            except TimeoutError:
                continue
            except socket.timeout:
                continue
            thread = threading.Thread(
                target=_handle_connection,
                args=(daemon, conn, stop_event),
                daemon=True,
            )
            thread.start()
    finally:
        server.close()
        daemon.stop()
        paths.socket_path.unlink(missing_ok=True)
        paths.pid_path.unlink(missing_ok=True)
    return 0


def query_with_client(
    *,
    client: ClangdClient,
    project_root: Path,
    symbol: str,
    options: QueryOptions,
    started: float | None = None,
    deadline: float | None = None,
    workspace_budget: float | None = None,
) -> list[QueryResult]:
    started = time.perf_counter() if started is None else started
    deadline = started + options.timeout if deadline is None else deadline
    workspace_budget = (
        max(0.01, min(options.timeout * 0.65, deadline - time.perf_counter()))
        if workspace_budget is None
        else workspace_budget
    )
    candidates = client.workspace_symbol(
        symbol,
        limit=max(options.limit * 4, 20),
        timeout=workspace_budget,
    )
    selected = _dedupe_candidates(candidates, limit=options.limit)
    results: list[QueryResult] = []

    for candidate in selected:
        if time.perf_counter() >= deadline:
            break
        result = _result_for_candidate(
            client=client,
            project_root=project_root,
            candidate=candidate,
            query=symbol,
            deadline=deadline,
            resolve_implementation=options.resolve_implementation,
        )
        if result is not None:
            elapsed = (time.perf_counter() - started) * 1000
            results.append(_replace_elapsed(result, elapsed))
    return results


def _result_for_candidate(
    *,
    client: ClangdClient,
    project_root: Path,
    candidate: SymbolCandidate,
    query: str,
    deadline: float,
    resolve_implementation: bool,
) -> QueryResult | None:
    location = candidate.location
    resolution = "workspace-symbol"

    if resolve_implementation and candidate.kind in FUNCTIONLIKE_KINDS:
        implementation = None
        definition = None
        try:
            request_timeout = _remaining_request_timeout(deadline)
            implementation = _first_project_location(
                client.implementation(
                    location.path,
                    location.range.start,
                    timeout=request_timeout,
                ),
                project_root,
            )
        except LspError:
            implementation = None
        if implementation is not None:
            location = implementation
            resolution = "implementation"
        elif time.perf_counter() < deadline:
            try:
                request_timeout = _remaining_request_timeout(deadline)
                definition = _first_project_location(
                    client.definition(
                        location.path,
                        location.range.start,
                        timeout=request_timeout,
                    ),
                    project_root,
                )
            except LspError:
                definition = None
            if definition is not None:
                location = definition
                resolution = "definition"

    if not location.path.exists():
        return None

    snippet = extract_source(
        location.path,
        location.range.start,
        symbol_name=candidate.full_name or query,
        kind=candidate.kind,
        preferred_range=location.range,
    )
    return QueryResult(
        name=candidate.name,
        full_name=candidate.full_name,
        kind=candidate.kind,
        location=location,
        source=snippet.source,
        source_range=snippet.range,
        resolution=resolution,
        elapsed_ms=0.0,
    )


def client_request(
    *,
    project: str | os.PathLike[str],
    payload: dict[str, Any],
    timeout: float = 2.0,
) -> dict[str, Any]:
    project_root = Path(project).expanduser().resolve()
    paths = runtime_paths(project_root)
    if not _endpoint_responds(paths.host, paths.port):
        raise DaemonError(
            f"daemon is not running for {project_root}. Start it with: "
            f"cpp-symbol-scout start --project {project_root}"
        )

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as conn:
        conn.settimeout(timeout)
        conn.connect((paths.host, paths.port))
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        conn.sendall(len(body).to_bytes(4, byteorder="big") + body)
        header = _recv_exact(conn, 4)
        size = int.from_bytes(header, byteorder="big")
        response = _recv_exact(conn, size)
    decoded = json.loads(response.decode("utf-8"))
    if not isinstance(decoded, dict):
        raise DaemonError("daemon returned an invalid response")
    if not decoded.get("ok", False):
        raise DaemonError(str(decoded.get("error") or "daemon request failed"))
    return decoded


def _handle_connection(daemon: SymbolDaemon, conn: socket.socket, stop_event: threading.Event) -> None:
    with conn:
        try:
            header = _recv_exact(conn, 4)
            size = int.from_bytes(header, byteorder="big")
            if size <= 0 or size > 32 * 1024 * 1024:
                raise DaemonError("invalid request size")
            payload = json.loads(_recv_exact(conn, size).decode("utf-8"))
            if not isinstance(payload, dict):
                raise DaemonError("request must be a JSON object")

            command = payload.get("command")
            if command == "status":
                response = {"ok": True, "status": daemon.status()}
            elif command == "stop":
                stop_event.set()
                response = {"ok": True}
            elif command == "query":
                symbol = str(payload.get("symbol") or "").strip()
                if not symbol:
                    raise DaemonError("query symbol is empty")
                options = QueryOptions(
                    limit=int(payload.get("limit") or 5),
                    timeout=float(payload.get("timeout") or 1.0),
                    resolve_implementation=bool(payload.get("resolve_implementation", True)),
                )
                if options.limit <= 0:
                    raise DaemonError("limit must be positive")
                if options.timeout <= 0:
                    raise DaemonError("timeout must be positive")
                results = daemon.query(symbol, options)
                response = {"ok": True, "results": [result.to_dict() for result in results]}
            else:
                raise DaemonError(f"unknown command: {command}")
        except Exception as exc:
            response = {"ok": False, "error": str(exc)}
        _send_response(conn, response)


def _send_response(conn: socket.socket, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    conn.sendall(len(body).to_bytes(4, byteorder="big") + body)


def _recv_exact(conn: socket.socket, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining > 0:
        chunk = conn.recv(remaining)
        if not chunk:
            raise DaemonError("connection closed while reading daemon response")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _endpoint_responds(host: str, port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as conn:
            conn.settimeout(0.2)
            conn.connect((host, port))
            _send_framed_json(conn, {"command": "status"})
            header = _recv_exact(conn, 4)
            size = int.from_bytes(header, byteorder="big")
            _recv_exact(conn, size)
        return True
    except OSError:
        return False
    except Exception:
        return False


def _dedupe_candidates(candidates: list[SymbolCandidate], *, limit: int) -> list[SymbolCandidate]:
    seen: set[tuple[str, str, int, int]] = set()
    result: list[SymbolCandidate] = []
    for candidate in candidates:
        key = (
            str(candidate.location.path),
            candidate.full_name,
            candidate.location.range.start.line,
            candidate.location.range.start.character,
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(candidate)
        if len(result) >= limit:
            break
    return result


def _first_project_location(locations: list[Location], project_root: Path) -> Location | None:
    for location in locations:
        try:
            location.path.resolve().relative_to(project_root)
            return location
        except ValueError:
            continue
    return locations[0] if locations else None


def _replace_elapsed(result: QueryResult, elapsed_ms: float) -> QueryResult:
    return QueryResult(
        name=result.name,
        full_name=result.full_name,
        kind=result.kind,
        location=result.location,
        source=result.source,
        source_range=result.source_range,
        resolution=result.resolution,
        elapsed_ms=elapsed_ms,
    )


def document_symbol_query(
    *,
    client: ClangdClient,
    project_root: Path,
    files: list[Path],
    symbol: str,
    options: QueryOptions,
) -> list[QueryResult]:
    started = time.perf_counter()
    deadline = started + options.timeout
    leaf = symbol.rsplit("::", 1)[-1].lower()
    candidates: list[SymbolCandidate] = []
    for path in files:
        if time.perf_counter() >= deadline:
            break
        try:
            candidates.extend(
                client.document_symbols(
                    path,
                    query=symbol,
                    timeout=max(0.05, min(2.0, deadline - time.perf_counter())),
                    limit=100,
                )
            )
        except Exception:
            continue

    filtered = [
        candidate
        for candidate in candidates
        if candidate.name.lower() == leaf or candidate.full_name.lower().endswith(f"::{leaf}")
    ]
    if not filtered:
        filtered = candidates
    filtered.sort(key=lambda candidate: _direct_candidate_score(candidate, symbol))

    results: list[QueryResult] = []
    for candidate in filtered[: options.limit]:
        result = _result_for_candidate(
            client=client,
            project_root=project_root,
            candidate=candidate,
            query=symbol,
            deadline=deadline,
            resolve_implementation=options.resolve_implementation,
        )
        if result is not None:
            elapsed = (time.perf_counter() - started) * 1000
            results.append(
                QueryResult(
                    name=result.name,
                    full_name=result.full_name,
                    kind=result.kind,
                    location=result.location,
                    source=result.source,
                    source_range=result.source_range,
                    resolution="document-symbol",
                    elapsed_ms=elapsed,
                )
            )
    return results


def candidate_source_files(project_root: Path, symbol: str) -> list[Path]:
    leaf = symbol.rsplit("::", 1)[-1]
    snake = _camel_to_snake(leaf)
    names = {
        f"{leaf}.h",
        f"{leaf}.hpp",
        f"{leaf}.cpp",
        f"{snake}.h",
        f"{snake}.hpp",
        f"{snake}.cpp",
    }
    result: list[Path] = []
    for root_name in ("core", "scene", "editor", "servers", "main", "modules", "drivers"):
        root = project_root / root_name
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.name in names and path.suffix.lower() in {".h", ".hpp", ".hh", ".cpp", ".cc", ".cxx"}:
                result.append(path)
                if len(result) >= 20:
                    return result
    if not result:
        result.extend(_files_containing_symbol(project_root, leaf, limit=20))
    return result


def _files_containing_symbol(project_root: Path, symbol: str, *, limit: int) -> list[Path]:
    if not symbol:
        return []
    roots = ("core", "scene", "editor", "servers", "main", "modules", "drivers")
    suffixes = {".h", ".hpp", ".hh", ".cpp", ".cc", ".cxx"}
    result: list[Path] = []
    needle = symbol.encode("utf-8", errors="ignore")
    for root_name in roots:
        root = project_root / root_name
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.suffix.lower() not in suffixes:
                continue
            try:
                if needle in path.read_bytes():
                    result.append(path)
                    if len(result) >= limit:
                        return result
            except OSError:
                continue
    return result


def _direct_candidate_score(candidate: SymbolCandidate, symbol: str) -> tuple[int, int, int, int]:
    leaf = symbol.rsplit("::", 1)[-1].lower()
    name = candidate.name.lower()
    full_name = candidate.full_name.lower()
    if name == leaf:
        tier = 0
    elif full_name.endswith(f"::{leaf}"):
        tier = 1
    elif leaf in name:
        tier = 2
    elif leaf in full_name:
        tier = 3
    else:
        tier = 4
    return (tier, len(full_name), candidate.location.range.start.line, candidate.location.range.start.character)


def _camel_to_snake(value: str) -> str:
    chars: list[str] = []
    for index, char in enumerate(value):
        if char.isupper() and index > 0:
            chars.append("_")
        chars.append(char.lower())
    return "".join(chars)


def _remaining_request_timeout(deadline: float) -> float:
    remaining = deadline - time.perf_counter()
    if remaining <= 0:
        return 0.01
    return max(0.01, min(remaining, 0.2))


def _send_framed_json(conn: socket.socket, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    conn.sendall(len(body).to_bytes(4, byteorder="big") + body)
