from __future__ import annotations

import hashlib
import json
import os
import queue
import re
import shutil
import socket
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse


SYMBOL_KINDS: dict[int, str] = {
    1: "File",
    2: "Module",
    3: "Namespace",
    4: "Package",
    5: "Class",
    6: "Method",
    7: "Property",
    8: "Field",
    9: "Constructor",
    10: "Enum",
    11: "Interface",
    12: "Function",
    13: "Variable",
    14: "Constant",
    15: "String",
    16: "Number",
    17: "Boolean",
    18: "Array",
    19: "Object",
    20: "Key",
    21: "Null",
    22: "EnumMember",
    23: "Struct",
    24: "Event",
    25: "Operator",
    26: "TypeParameter",
}
CLASSLIKE_KINDS = {5, 10, 11, 23}
FUNCTIONLIKE_KINDS = {6, 9, 12, 20, 25}
SOURCE_SUFFIXES = {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx", ".ipp", ".inl"}
SOURCE_ROOTS = (
    "src",
    "include",
    "lib",
    "source",
    "core",
    "scene",
    "servers",
    "editor",
    "modules",
    "drivers",
    "platform",
    "main",
)
SKIPPED_SOURCE_DIRS = {
    ".cache",
    ".git",
    ".hg",
    ".runtime",
    ".svn",
    "__pycache__",
    "build",
    "cmake-build-debug",
    "cmake-build-release",
    "node_modules",
    "out",
    "thirdparty",
    "vendor",
}


class ServiceError(RuntimeError):
    pass


@dataclass(frozen=True)
class Position:
    line: int
    character: int

    @classmethod
    def from_lsp(cls, value: dict[str, Any]) -> "Position":
        return cls(int(value["line"]), int(value["character"]))

    def to_lsp(self) -> dict[str, int]:
        return {"line": self.line, "character": self.character}


@dataclass(frozen=True)
class Range:
    start: Position
    end: Position

    @classmethod
    def from_lsp(cls, value: dict[str, Any]) -> "Range":
        return cls(Position.from_lsp(value["start"]), Position.from_lsp(value["end"]))

    def to_lsp(self) -> dict[str, dict[str, int]]:
        return {"start": self.start.to_lsp(), "end": self.end.to_lsp()}


@dataclass(frozen=True)
class Location:
    path: Path
    range: Range

    @classmethod
    def from_lsp(cls, value: dict[str, Any]) -> "Location":
        if "targetUri" in value:
            uri = str(value["targetUri"])
            range_value = value.get("targetSelectionRange") or value["targetRange"]
        else:
            uri = str(value["uri"])
            range_value = value["range"]
        return cls(uri_to_path(uri), Range.from_lsp(range_value))

    def to_dict(self, project_root: Path, *, snippet: bool = False) -> dict[str, Any]:
        payload = {
            "path": str(self.path),
            "relative_path": relative_path(self.path, project_root),
            "line": self.range.start.line + 1,
            "column": self.range.start.character + 1,
            "range": self.range.to_lsp(),
        }
        if snippet:
            payload["snippet"] = source_line(self.path, self.range.start.line)
        return payload


@dataclass(frozen=True)
class SymbolCandidate:
    name: str
    container_name: str
    kind: int
    location: Location
    score: tuple[int, int, int]

    @property
    def full_name(self) -> str:
        return f"{self.container_name}::{self.name}" if self.container_name else self.name

    @property
    def kind_name(self) -> str:
        return SYMBOL_KINDS.get(self.kind, f"Kind{self.kind}")

    def to_dict(self, project_root: Path) -> dict[str, Any]:
        return {
            "name": self.name,
            "full_name": self.full_name,
            "kind": self.kind,
            "kind_name": self.kind_name,
            "location": self.location.to_dict(project_root, snippet=True),
        }


@dataclass(frozen=True)
class SourceSnippet:
    source: str
    range: Range


@dataclass(frozen=True)
class SymbolQueryResult:
    name: str
    full_name: str
    kind: int
    location: Location
    source: str
    source_range: Range | None
    resolution: str
    elapsed_ms: float

    def to_dict(self, project_root: Path) -> dict[str, Any]:
        return {
            "name": self.name,
            "full_name": self.full_name,
            "kind": self.kind,
            "kind_name": SYMBOL_KINDS.get(self.kind, f"Kind{self.kind}"),
            "location": symbol_location_to_dict(self.location, project_root),
            "source": self.source,
            "source_range": self.source_range.to_lsp() if self.source_range else None,
            "resolution": self.resolution,
            "elapsed_ms": round(self.elapsed_ms, 3),
        }


@dataclass(frozen=True)
class RuntimePaths:
    base_dir: Path
    pid_path: Path
    log_path: Path
    project_id: str
    host: str
    port: int


@dataclass(frozen=True)
class ProjectConfig:
    project_root: Path
    clangd_path: str
    compile_commands_dir: Path | None

    @classmethod
    def discover(
        cls,
        project: str | os.PathLike[str],
        *,
        clangd: str = "clangd",
        compile_commands_dir: str | os.PathLike[str] | None = None,
        require_compile_db: bool = True,
    ) -> "ProjectConfig":
        project_root = Path(project).expanduser().resolve()
        if not project_root.is_dir():
            raise ServiceError(f"project path is not a directory: {project_root}")
        clangd_path = resolve_clangd(clangd)
        if not clangd_path:
            raise ServiceError("clangd was not found. Install clangd or pass --clangd.")
        if compile_commands_dir is None:
            db_dir = find_compile_commands_dir(project_root)
        else:
            db_dir = Path(compile_commands_dir).expanduser().resolve()
            if not db_dir.is_dir() or not has_compile_database(db_dir):
                raise ServiceError(f"invalid compile commands directory: {db_dir}")
        if require_compile_db and db_dir is None:
            raise ServiceError("no compile_commands.json or compile_flags.txt found")
        return cls(project_root, clangd_path, db_dir)


class ClangdClient:
    def __init__(self, config: ProjectConfig, *, log_file: Path | None = None) -> None:
        self.config = config
        self.log_file = log_file
        self._proc: subprocess.Popen[bytes] | None = None
        self._stderr_file: Any = None
        self._next_id = 1
        self._pending: dict[int, queue.Queue[dict[str, Any]]] = {}
        self._pending_lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._opened: set[Path] = set()
        self._opened_lock = threading.Lock()

    def start(self, *, timeout: float = 30.0) -> None:
        if self._proc is not None:
            return
        args = [
            self.config.clangd_path,
            "--background-index",
            "--clang-tidy=false",
            "--header-insertion=never",
            "--completion-style=detailed",
        ]
        if self.config.compile_commands_dir is not None:
            args.append(f"--compile-commands-dir={self.config.compile_commands_dir}")
        stderr_target: Any = subprocess.DEVNULL
        if self.log_file is not None:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            self._stderr_file = self.log_file.open("ab")
            stderr_target = self._stderr_file
        self._proc = subprocess.Popen(
            args,
            cwd=self.config.project_root,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=stderr_target,
        )
        threading.Thread(target=self._read_loop, daemon=True).start()
        result = self.request(
            "initialize",
            {
                "processId": None,
                "rootUri": path_to_uri(self.config.project_root),
                "workspaceFolders": [
                    {"uri": path_to_uri(self.config.project_root), "name": self.config.project_root.name}
                ],
                "capabilities": {
                    "workspace": {"symbol": {"resolveSupport": {"properties": ["location.range"]}}},
                    "textDocument": {
                        "documentSymbol": {"hierarchicalDocumentSymbolSupport": True},
                        "references": {},
                        "definition": {"linkSupport": True},
                        "implementation": {"linkSupport": True},
                        "typeDefinition": {"linkSupport": True},
                        "hover": {"contentFormat": ["markdown", "plaintext"]},
                        "callHierarchy": {"dynamicRegistration": False},
                    },
                },
            },
            timeout=timeout,
        )
        if not isinstance(result, dict):
            raise ServiceError("clangd initialize failed")
        self.notify("initialized", {})

    def stop(self) -> None:
        if self._proc is None:
            return
        try:
            self.request("shutdown", None, timeout=5.0)
            self.notify("exit", None)
        except Exception:
            self._proc.terminate()
        try:
            self._proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            self._proc.kill()
            self._proc.wait(timeout=5.0)
        if self._stderr_file is not None:
            self._stderr_file.close()
            self._stderr_file = None
        self._proc = None

    def request(self, method: str, params: Any, *, timeout: float = 10.0) -> Any:
        if self._proc is None or self._proc.stdin is None:
            raise ServiceError("clangd is not running")
        request_id = self._allocate_id()
        response_queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)
        with self._pending_lock:
            self._pending[request_id] = response_queue
        try:
            self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
            message = response_queue.get(timeout=timeout)
        except queue.Empty as exc:
            raise ServiceError(f"clangd request timed out: {method}") from exc
        finally:
            with self._pending_lock:
                self._pending.pop(request_id, None)
        if "error" in message:
            raise ServiceError(f"clangd {method} error: {message['error']}")
        return message.get("result")

    def notify(self, method: str, params: Any) -> None:
        if self._proc is None or self._proc.stdin is None:
            raise ServiceError("clangd is not running")
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def open_document(self, path: Path) -> None:
        path = path.resolve()
        with self._opened_lock:
            if path in self._opened:
                return
            text = path.read_text(encoding="utf-8", errors="replace")
            self.notify(
                "textDocument/didOpen",
                {
                    "textDocument": {
                        "uri": path_to_uri(path),
                        "languageId": language_id(path),
                        "version": 1,
                        "text": text,
                    }
                },
            )
            self._opened.add(path)

    def workspace_symbol(self, query: str, *, limit: int = 20, timeout: float = 10.0) -> list[SymbolCandidate]:
        result = self.request("workspace/symbol", {"query": query}, timeout=timeout)
        if not isinstance(result, list):
            return []
        candidates: list[SymbolCandidate] = []
        for item in result:
            if not isinstance(item, dict) or "location" not in item:
                continue
            try:
                location = Location.from_lsp(item["location"])
            except Exception:
                continue
            name = str(item.get("name") or "")
            container = str(item.get("containerName") or "")
            candidates.append(
                SymbolCandidate(
                    name=name,
                    container_name=container,
                    kind=int(item.get("kind") or 0),
                    location=location,
                    score=score_candidate(query, name, container),
                )
            )
        candidates.sort(key=lambda item: item.score)
        return candidates[:limit]

    def references(self, path: Path, position: Position, *, include_declaration: bool, timeout: float) -> list[Location]:
        self.open_document(path)
        result = self.request(
            "textDocument/references",
            {
                "textDocument": {"uri": path_to_uri(path)},
                "position": position.to_lsp(),
                "context": {"includeDeclaration": include_declaration},
            },
            timeout=timeout,
        )
        return locations_from_result(result)

    def definition(self, path: Path, position: Position, *, timeout: float) -> list[Location]:
        return self._location_request("textDocument/definition", path, position, timeout=timeout)

    def implementation(self, path: Path, position: Position, *, timeout: float) -> list[Location]:
        return self._location_request("textDocument/implementation", path, position, timeout=timeout)

    def type_definition(self, path: Path, position: Position, *, timeout: float) -> list[Location]:
        return self._location_request("textDocument/typeDefinition", path, position, timeout=timeout)

    def document_symbols(
        self,
        path: Path,
        *,
        query: str = "",
        timeout: float = 4.0,
        limit: int = 20,
    ) -> list[SymbolCandidate]:
        self.open_document(path)
        result = self.request(
            "textDocument/documentSymbol",
            {"textDocument": {"uri": path_to_uri(path)}},
            timeout=timeout,
        )
        candidates: list[SymbolCandidate] = []
        if isinstance(result, list):
            for item in result:
                if not isinstance(item, dict):
                    continue
                if "selectionRange" in item:
                    candidates.extend(document_symbol_candidates(path, item, query=query))
                elif "location" in item:
                    try:
                        location = Location.from_lsp(item["location"])
                    except Exception:
                        continue
                    name = str(item.get("name") or "")
                    container = str(item.get("containerName") or "")
                    kind = int(item.get("kind") or 0)
                    candidates.append(
                        SymbolCandidate(
                            name=name,
                            container_name=container,
                            kind=kind,
                            location=location,
                            score=score_candidate(query, name, container),
                        )
                    )
        candidates.sort(key=lambda candidate: candidate.score)
        return candidates[:limit]

    def hover(self, path: Path, position: Position, *, timeout: float) -> dict[str, Any] | None:
        self.open_document(path)
        result = self.request(
            "textDocument/hover",
            {"textDocument": {"uri": path_to_uri(path)}, "position": position.to_lsp()},
            timeout=timeout,
        )
        return result if isinstance(result, dict) else None

    def prepare_call_hierarchy(self, path: Path, position: Position, *, timeout: float) -> list[dict[str, Any]]:
        self.open_document(path)
        result = self.request(
            "textDocument/prepareCallHierarchy",
            {"textDocument": {"uri": path_to_uri(path)}, "position": position.to_lsp()},
            timeout=timeout,
        )
        return result if isinstance(result, list) else []

    def incoming_calls(self, item: dict[str, Any], *, timeout: float) -> list[dict[str, Any]]:
        result = self.request("callHierarchy/incomingCalls", {"item": item}, timeout=timeout)
        return result if isinstance(result, list) else []

    def outgoing_calls(self, item: dict[str, Any], *, timeout: float) -> list[dict[str, Any]]:
        result = self.request("callHierarchy/outgoingCalls", {"item": item}, timeout=timeout)
        return result if isinstance(result, list) else []

    def _location_request(self, method: str, path: Path, position: Position, *, timeout: float) -> list[Location]:
        self.open_document(path)
        result = self.request(
            method,
            {"textDocument": {"uri": path_to_uri(path)}, "position": position.to_lsp()},
            timeout=timeout,
        )
        return locations_from_result(result)

    def _allocate_id(self) -> int:
        with self._pending_lock:
            request_id = self._next_id
            self._next_id += 1
        return request_id

    def _send(self, payload: dict[str, Any]) -> None:
        assert self._proc is not None and self._proc.stdin is not None
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        with self._write_lock:
            self._proc.stdin.write(header + body)
            self._proc.stdin.flush()

    def _read_loop(self) -> None:
        assert self._proc is not None and self._proc.stdout is not None
        stdout = self._proc.stdout
        while True:
            try:
                headers: dict[str, str] = {}
                while True:
                    line = stdout.readline()
                    if not line:
                        return
                    if line in {b"\r\n", b"\n"}:
                        break
                    name, _, value = line.decode("ascii", errors="replace").partition(":")
                    headers[name.strip().lower()] = value.strip()
                length = int(headers.get("content-length", "0"))
                if length <= 0:
                    continue
                message = json.loads(stdout.read(length).decode("utf-8"))
            except Exception:
                return
            if "id" not in message:
                continue
            with self._pending_lock:
                response_queue = self._pending.get(int(message["id"]))
            if response_queue is not None:
                response_queue.put(message)


class SemanticService:
    def __init__(self, config: ProjectConfig, paths: RuntimePaths) -> None:
        self.config = config
        self.paths = paths
        self.client = ClangdClient(config, log_file=paths.log_path)
        self.ready_since: float | None = None
        self.cache_lock = threading.Lock()
        self.symbol_cache: dict[tuple[str, int, bool], list[SymbolQueryResult]] = {}

    def start(self) -> None:
        self.client.start()
        self.ready_since = time.monotonic()

    def stop(self) -> None:
        self.client.stop()

    def status(self) -> dict[str, Any]:
        return {
            "project_root": str(self.config.project_root),
            "clangd": self.config.clangd_path,
            "compile_commands_dir": str(self.config.compile_commands_dir) if self.config.compile_commands_dir else None,
            "tcp": f"{self.paths.host}:{self.paths.port}",
            "pid": str(self.paths.pid_path),
            "log": str(self.paths.log_path),
            "ready": self.ready_since is not None,
            "uptime_seconds": round(time.monotonic() - self.ready_since, 3) if self.ready_since else 0,
            "symbol_cache_entries": self.symbol_cache_size(),
        }

    def handle(self, payload: dict[str, Any]) -> dict[str, Any]:
        command = str(payload.get("command") or "")
        if command == "status":
            return {"ok": True, "status": self.status()}
        if command == "references":
            return {"ok": True, "result": self.references(payload)}
        if command == "symbol_query":
            return {"ok": True, "result": self.symbol_query(payload)}
        if command == "type_inspect":
            return {"ok": True, "result": self.type_inspect(payload)}
        if command == "call_hierarchy":
            return {"ok": True, "result": self.call_hierarchy(payload)}
        if command == "stop":
            return {"ok": True}
        raise ServiceError(f"unknown command: {command}")

    def symbol_cache_size(self) -> int:
        with self.cache_lock:
            return len(self.symbol_cache)

    def references(self, payload: dict[str, Any]) -> dict[str, Any]:
        symbol, path, position = self._resolve_target(payload)
        include_declaration = bool(payload.get("include_declaration", False))
        limit = int(payload.get("limit") or 50)
        timeout = float(payload.get("timeout") or 10.0)
        refs = dedupe_locations(
            self.client.references(path, position, include_declaration=include_declaration, timeout=timeout)
        )[:limit]
        return {
            "query": payload.get("symbol") or f"{path}:{position.line + 1}:{position.character + 1}",
            "symbol": symbol.to_dict(self.config.project_root) if symbol else None,
            "position": Location(path, Range(position, position)).to_dict(self.config.project_root, snippet=True),
            "include_declaration": include_declaration,
            "reference_count": len(refs),
            "references": [location.to_dict(self.config.project_root, snippet=True) for location in refs],
        }

    def symbol_query(self, payload: dict[str, Any]) -> dict[str, Any]:
        symbol = str(payload.get("symbol") or "").strip()
        if not symbol:
            raise ServiceError("query symbol is empty")
        limit = int(payload.get("limit") or 5)
        timeout = float(payload.get("timeout") or 1.0)
        resolve_implementation = bool(payload.get("resolve_implementation", True))
        if limit <= 0:
            raise ServiceError("limit must be positive")
        if timeout <= 0:
            raise ServiceError("timeout must be positive")

        started = time.perf_counter()
        cache_key = (symbol, limit, resolve_implementation)
        with self.cache_lock:
            cached = self.symbol_cache.get(cache_key)
        if cached is not None:
            elapsed = (time.perf_counter() - started) * 1000
            results = [replace_symbol_elapsed(result, elapsed) for result in cached]
        else:
            deadline = started + timeout
            workspace_budget = max(0.01, min(timeout * 0.65, deadline - time.perf_counter()))
            results = symbol_query_with_client(
                client=self.client,
                project_root=self.config.project_root,
                symbol=symbol,
                limit=limit,
                timeout=timeout,
                resolve_implementation=resolve_implementation,
                started=started,
                deadline=deadline,
                workspace_budget=workspace_budget,
            )
            if not results and time.perf_counter() < deadline:
                results = document_symbol_query(
                    client=self.client,
                    project_root=self.config.project_root,
                    files=symbol_candidate_source_files(self.config.project_root, symbol),
                    symbol=symbol,
                    limit=limit,
                    timeout=max(0.01, deadline - time.perf_counter()),
                    resolve_implementation=False,
                )
            if results:
                with self.cache_lock:
                    self.symbol_cache[cache_key] = results
            elapsed = (time.perf_counter() - started) * 1000
            results = [replace_symbol_elapsed(result, elapsed) for result in results]
        return {
            "query": symbol,
            "result_count": len(results),
            "results": [result.to_dict(self.config.project_root) for result in results],
        }

    def type_inspect(self, payload: dict[str, Any]) -> dict[str, Any]:
        symbol, path, position = self._resolve_target(payload)
        timeout = float(payload.get("timeout") or 10.0)
        hover = self.client.hover(path, position, timeout=timeout)
        definitions = self.client.definition(path, position, timeout=timeout)
        type_definitions = self.client.type_definition(path, position, timeout=timeout)
        return {
            "query": payload.get("symbol") or f"{path}:{position.line + 1}:{position.character + 1}",
            "symbol": symbol.to_dict(self.config.project_root) if symbol else None,
            "position": {
                "path": str(path),
                "relative_path": relative_path(path, self.config.project_root),
                "line": position.line + 1,
                "column": position.character + 1,
                "snippet": source_line(path, position.line),
            },
            "hover": normalize_hover(hover),
            "type_summary": extract_type_summary(normalize_hover(hover).get("text", "")),
            "definitions": [item.to_dict(self.config.project_root, snippet=True) for item in definitions],
            "type_definitions": [item.to_dict(self.config.project_root, snippet=True) for item in type_definitions],
        }

    def call_hierarchy(self, payload: dict[str, Any]) -> dict[str, Any]:
        symbol, path, position = self._resolve_target(payload)
        timeout = float(payload.get("timeout") or 10.0)
        limit = int(payload.get("limit") or 20)
        incoming = bool(payload.get("incoming", True))
        outgoing = bool(payload.get("outgoing", True))
        items = self.client.prepare_call_hierarchy(path, position, timeout=timeout)
        if not items:
            raise ServiceError("clangd did not return call hierarchy items")
        item = items[0]
        result: dict[str, Any] = {
            "query": payload.get("symbol") or f"{path}:{position.line + 1}:{position.character + 1}",
            "symbol": symbol.to_dict(self.config.project_root) if symbol else None,
            "item": call_item_to_dict(item, self.config.project_root),
            "incoming": [],
            "outgoing": [],
        }
        if incoming:
            result["incoming"] = [
                incoming_to_dict(call, self.config.project_root)
                for call in self.client.incoming_calls(item, timeout=timeout)[:limit]
            ]
        if outgoing:
            try:
                result["outgoing"] = [
                    outgoing_to_dict(call, self.config.project_root)
                    for call in self.client.outgoing_calls(item, timeout=timeout)[:limit]
                ]
                result["outgoing_resolution"] = "clangd"
            except ServiceError:
                result["outgoing"] = static_outgoing_calls(item, self.config.project_root, limit=limit)
                result["outgoing_resolution"] = "fallback-static"
        return result

    def _resolve_target(self, payload: dict[str, Any]) -> tuple[SymbolCandidate | None, Path, Position]:
        if payload.get("symbol"):
            symbol = self._locate_symbol(str(payload["symbol"]), timeout=float(payload.get("timeout") or 10.0))
            if symbol is None:
                raise ServiceError(f"no workspace symbol or source match found for {payload['symbol']}")
            return symbol, symbol.location.path, symbol.location.range.start
        if not payload.get("file"):
            raise ServiceError("request requires symbol or file")
        path = resolve_source_path(str(payload["file"]), self.config.project_root)
        line = int(payload.get("line") or 0)
        column = int(payload.get("column") or 0)
        if line <= 0 or column <= 0:
            raise ServiceError("line and column must be positive")
        return None, path, Position(line - 1, column - 1)

    def _locate_symbol(self, query: str, *, timeout: float) -> SymbolCandidate | None:
        symbols = self.client.workspace_symbol(query, limit=20, timeout=timeout)
        if symbols:
            return symbols[0]
        return locate_symbol_in_source(query, self.config.project_root)


def runtime_paths(project_root: Path) -> RuntimePaths:
    project_id = hashlib.sha1(str(project_root.resolve()).encode("utf-8")).hexdigest()[:20]
    base = Path.cwd() / ".runtime" / "cpp-clangd-service"
    try:
        base.mkdir(mode=0o700, parents=True, exist_ok=True)
    except OSError:
        base = Path("/tmp") / f"cpp-clangd-service-{os.getuid()}"
        base.mkdir(mode=0o700, parents=True, exist_ok=True)
    return RuntimePaths(
        base_dir=base,
        pid_path=base / f"{project_id}.pid",
        log_path=base / f"{project_id}.log",
        project_id=project_id,
        host="127.0.0.1",
        port=56000 + (int(project_id[:8], 16) % 8000),
    )


def send_request(project: str | os.PathLike[str], payload: dict[str, Any], *, timeout: float = 10.0) -> dict[str, Any]:
    project_root = Path(project).expanduser().resolve()
    paths = runtime_paths(project_root)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as conn:
        conn.settimeout(timeout)
        conn.connect((paths.host, paths.port))
        send_framed(conn, payload)
        response = recv_framed(conn)
    if not isinstance(response, dict):
        raise ServiceError("service returned non-object response")
    if not response.get("ok", False):
        raise ServiceError(str(response.get("error") or "service request failed"))
    return response


def endpoint_responds(project: str | os.PathLike[str]) -> bool:
    try:
        send_request(project, {"command": "status"}, timeout=0.3)
        return True
    except Exception:
        return False


def send_framed(conn: socket.socket, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    conn.sendall(len(body).to_bytes(4, "big") + body)


def recv_framed(conn: socket.socket) -> dict[str, Any]:
    size = int.from_bytes(recv_exact(conn, 4), "big")
    if size <= 0 or size > 64 * 1024 * 1024:
        raise ServiceError("invalid frame size")
    return json.loads(recv_exact(conn, size).decode("utf-8"))


def recv_exact(conn: socket.socket, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining > 0:
        chunk = conn.recv(remaining)
        if not chunk:
            raise ServiceError("connection closed")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def locations_from_result(result: Any) -> list[Location]:
    if result is None:
        return []
    values = result if isinstance(result, list) else [result]
    locations: list[Location] = []
    for item in values:
        if not isinstance(item, dict):
            continue
        try:
            locations.append(Location.from_lsp(item))
        except Exception:
            continue
    return locations


def dedupe_locations(locations: list[Location]) -> list[Location]:
    seen: set[tuple[str, int, int]] = set()
    result: list[Location] = []
    for location in locations:
        key = (str(location.path), location.range.start.line, location.range.start.character)
        if key in seen:
            continue
        seen.add(key)
        result.append(location)
    result.sort(key=lambda item: (str(item.path), item.range.start.line, item.range.start.character))
    return result


def symbol_query_with_client(
    *,
    client: ClangdClient,
    project_root: Path,
    symbol: str,
    limit: int,
    timeout: float,
    resolve_implementation: bool,
    started: float | None = None,
    deadline: float | None = None,
    workspace_budget: float | None = None,
) -> list[SymbolQueryResult]:
    started = time.perf_counter() if started is None else started
    deadline = started + timeout if deadline is None else deadline
    workspace_budget = (
        max(0.01, min(timeout * 0.65, deadline - time.perf_counter()))
        if workspace_budget is None
        else workspace_budget
    )
    candidates = client.workspace_symbol(symbol, limit=max(limit * 4, 20), timeout=workspace_budget)
    selected = dedupe_symbol_candidates(
        prefer_function_definitions(candidates, project_root, symbol),
        limit=limit,
    )
    results: list[SymbolQueryResult] = []
    for candidate in selected:
        if time.perf_counter() >= deadline:
            break
        result = result_for_symbol_candidate(
            client=client,
            project_root=project_root,
            candidate=candidate,
            query=symbol,
            deadline=deadline,
            resolve_implementation=resolve_implementation,
        )
        if result is not None:
            elapsed = (time.perf_counter() - started) * 1000
            results.append(replace_symbol_elapsed(result, elapsed))
    return results


def result_for_symbol_candidate(
    *,
    client: ClangdClient,
    project_root: Path,
    candidate: SymbolCandidate,
    query: str,
    deadline: float,
    resolve_implementation: bool,
) -> SymbolQueryResult | None:
    location = candidate.location
    resolution = "workspace-symbol"
    if not location.path.exists():
        return None

    if resolve_implementation and candidate.kind in FUNCTIONLIKE_KINDS:
        current_snippet = extract_source(
            location.path,
            location.range.start,
            symbol_name=candidate.full_name or query,
            kind=candidate.kind,
            preferred_range=location.range,
        )
        if looks_like_function_definition(current_snippet):
            return SymbolQueryResult(
                name=candidate.name,
                full_name=candidate.full_name,
                kind=candidate.kind,
                location=location,
                source=current_snippet.source,
                source_range=current_snippet.range,
                resolution=resolution,
                elapsed_ms=0.0,
            )

        implementation = None
        definition = None
        try:
            implementation = first_project_location(
                client.implementation(
                    location.path,
                    location.range.start,
                    timeout=remaining_request_timeout(deadline),
                ),
                project_root,
            )
        except ServiceError:
            implementation = None
        if implementation is not None:
            location = implementation
            resolution = "implementation"
        elif time.perf_counter() < deadline:
            try:
                definition = first_project_location(
                    client.definition(
                        location.path,
                        location.range.start,
                        timeout=remaining_request_timeout(deadline),
                    ),
                    project_root,
                )
            except ServiceError:
                definition = None
            if definition is not None:
                location = definition
                resolution = "definition"

    snippet = extract_source(
        location.path,
        location.range.start,
        symbol_name=candidate.full_name or query,
        kind=candidate.kind,
        preferred_range=location.range,
    )
    return SymbolQueryResult(
        name=candidate.name,
        full_name=candidate.full_name,
        kind=candidate.kind,
        location=location,
        source=snippet.source,
        source_range=snippet.range,
        resolution=resolution,
        elapsed_ms=0.0,
    )


def document_symbol_query(
    *,
    client: ClangdClient,
    project_root: Path,
    files: list[Path],
    symbol: str,
    limit: int,
    timeout: float,
    resolve_implementation: bool,
) -> list[SymbolQueryResult]:
    started = time.perf_counter()
    deadline = started + timeout
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
        return []
    filtered.sort(key=lambda candidate: direct_candidate_score(candidate, symbol))

    results: list[SymbolQueryResult] = []
    for candidate in filtered[:limit]:
        result = result_for_symbol_candidate(
            client=client,
            project_root=project_root,
            candidate=candidate,
            query=symbol,
            deadline=deadline,
            resolve_implementation=resolve_implementation,
        )
        if result is not None:
            elapsed = (time.perf_counter() - started) * 1000
            results.append(
                SymbolQueryResult(
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


def dedupe_symbol_candidates(candidates: list[SymbolCandidate], *, limit: int) -> list[SymbolCandidate]:
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


def prefer_function_definitions(
    candidates: list[SymbolCandidate],
    project_root: Path,
    query: str,
) -> list[SymbolCandidate]:
    def key(candidate: SymbolCandidate) -> tuple[tuple[int, int, int], int, str]:
        implementation_penalty = 0
        if candidate.kind in FUNCTIONLIKE_KINDS:
            try:
                snippet = extract_source(
                    candidate.location.path,
                    candidate.location.range.start,
                    symbol_name=candidate.full_name or query,
                    kind=candidate.kind,
                    preferred_range=candidate.location.range,
                )
            except OSError:
                implementation_penalty = 1
            else:
                if not looks_like_function_definition(snippet):
                    implementation_penalty = 1
            if not candidate.location.path.exists():
                implementation_penalty = 1
        try:
            relative = str(candidate.location.path.resolve().relative_to(project_root))
        except ValueError:
            relative = str(candidate.location.path)
        return (candidate.score, implementation_penalty, relative)

    return sorted(candidates, key=key)


def first_project_location(locations: list[Location], project_root: Path) -> Location | None:
    for location in locations:
        try:
            location.path.resolve().relative_to(project_root)
            return location
        except ValueError:
            continue
    return locations[0] if locations else None


def replace_symbol_elapsed(result: SymbolQueryResult, elapsed_ms: float) -> SymbolQueryResult:
    return SymbolQueryResult(
        name=result.name,
        full_name=result.full_name,
        kind=result.kind,
        location=result.location,
        source=result.source,
        source_range=result.source_range,
        resolution=result.resolution,
        elapsed_ms=elapsed_ms,
    )


def looks_like_function_definition(snippet: SourceSnippet) -> bool:
    source = snippet.source.strip()
    if not source or "{" not in source:
        return False
    if source.endswith(";"):
        return False
    return True


def direct_candidate_score(candidate: SymbolCandidate, symbol: str) -> tuple[int, int, int, int, int]:
    leaf = symbol.rsplit("::", 1)[-1].lower()
    query = symbol.lower()
    name = candidate.name.lower()
    full_name = candidate.full_name.lower()
    if full_name == query:
        tier = 0
    elif "::" in symbol and full_name.endswith(f"::{query}"):
        tier = 1
    elif name == leaf:
        tier = 2 if "::" in symbol else 0
    elif full_name.endswith(f"::{leaf}"):
        tier = 3
    elif leaf in name:
        tier = 3
    elif leaf in full_name:
        tier = 4
    else:
        tier = 5
    return (
        tier,
        candidate_declaration_penalty(candidate, symbol),
        len(full_name),
        candidate.location.range.start.line,
        candidate.location.range.start.character,
    )


def candidate_declaration_penalty(candidate: SymbolCandidate, query: str) -> int:
    if candidate.kind not in CLASSLIKE_KINDS:
        return 0
    try:
        snippet = extract_source(
            candidate.location.path,
            candidate.location.range.start,
            symbol_name=candidate.full_name or query,
            kind=candidate.kind,
            preferred_range=candidate.location.range,
        )
    except OSError:
        return 1
    return 0 if "{" in snippet.source else 1


def symbol_candidate_source_files(project_root: Path, symbol: str) -> list[Path]:
    parts = symbol_parts(symbol)
    leaf = parts[-1] if parts else symbol
    result = named_candidate_source_files(project_root, parts or [leaf], leaf=leaf, limit=20)

    if len(parts) > 1 and len(result) < 20:
        for path in files_containing_symbols(project_root, parts, leaf=leaf, limit=20):
            append_unique_path(result, path)
            if len(result) >= 20:
                return result

    if len(result) < 20:
        for path in files_containing_symbols(project_root, [leaf], leaf=leaf, limit=20):
            append_unique_path(result, path)
            if len(result) >= 20:
                return result
    return result


def named_candidate_source_files(
    project_root: Path,
    parts: list[str],
    *,
    leaf: str,
    limit: int,
) -> list[Path]:
    names = candidate_file_names(parts)
    matches: list[tuple[tuple[int, int, str], Path]] = []
    for path in iter_source_files(project_root):
        if path.name not in names:
            continue
        try:
            content = path.read_bytes()
        except OSError:
            content = b""
        matches.append((source_file_score(path, content, leaf), path))
    matches.sort(key=lambda item: item[0])
    return [path for _score, path in matches[:limit]]


def files_containing_symbols(
    project_root: Path,
    symbols: list[str],
    *,
    leaf: str,
    limit: int,
) -> list[Path]:
    symbols = [symbol for symbol in symbols if symbol]
    if not symbols:
        return []
    needles = [symbol.encode("utf-8", errors="ignore") for symbol in symbols]
    matches: list[tuple[tuple[int, int, str], Path]] = []
    for path in iter_source_files(project_root):
        try:
            content = path.read_bytes()
        except OSError:
            continue
        if not all(needle in content for needle in needles):
            continue
        matches.append((source_file_score(path, content, leaf), path))
        if len(matches) >= limit * 4:
            break
    matches.sort(key=lambda item: item[0])
    return [path for _score, path in matches[:limit]]


def iter_source_files(project_root: Path) -> list[Path]:
    roots: list[Path] = []
    for name in SOURCE_ROOTS:
        root = project_root / name
        if root.is_dir():
            roots.append(root)
    if not roots:
        roots.append(project_root)

    seen: set[Path] = set()
    result: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path in seen or not path.is_file() or path.suffix.lower() not in SOURCE_SUFFIXES:
                continue
            if set(path.relative_to(project_root).parts) & SKIPPED_SOURCE_DIRS:
                continue
            seen.add(path)
            result.append(path)
    return result


def candidate_file_names(parts: list[str]) -> set[str]:
    names: set[str] = set()
    for part in parts:
        snake = camel_to_snake(part)
        for stem in {part, snake}:
            names.update({f"{stem}.h", f"{stem}.hpp", f"{stem}.cpp"})
    return names


def symbol_parts(symbol: str) -> list[str]:
    return [part for part in symbol.split("::") if part]


def source_file_score(path: Path, content: bytes, leaf: str) -> tuple[int, int, str]:
    try:
        text = content.decode("utf-8", errors="replace")
    except Exception:
        text = ""
    definition_penalty = 0 if contains_type_definition(text, leaf) else 1
    suffix_penalty = 0 if path.suffix.lower() in {".h", ".hpp", ".hh", ".hxx"} else 1
    return (definition_penalty, suffix_penalty, str(path))


def contains_type_definition(text: str, leaf: str) -> bool:
    if not leaf:
        return False
    pattern = re.compile(
        rf"\b(?:class|struct|union|enum)\s+(?:class\s+|struct\s+)?{re.escape(leaf)}\b"
    )
    return pattern.search(text) is not None


def append_unique_path(paths: list[Path], path: Path) -> None:
    if path not in paths:
        paths.append(path)


def camel_to_snake(value: str) -> str:
    value = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", value)
    value = re.sub(r"([a-z])([A-Z])", r"\1_\2", value)
    value = re.sub(r"([A-Za-z])([0-9])", r"\1_\2", value)
    return value.lower()


def remaining_request_timeout(deadline: float) -> float:
    remaining = deadline - time.perf_counter()
    if remaining <= 0:
        return 0.01
    return max(0.01, min(remaining, 0.2))


def document_symbol_candidates(
    path: Path,
    item: dict[str, Any],
    *,
    query: str,
    container: str = "",
) -> list[SymbolCandidate]:
    try:
        symbol_range = Range.from_lsp(item["range"])
    except Exception:
        return []
    name = str(item.get("name") or "")
    kind = int(item.get("kind") or 0)
    candidate = SymbolCandidate(
        name=name,
        container_name=container,
        kind=kind,
        location=Location(path=path, range=symbol_range),
        score=score_candidate(query, name, container),
    )
    children = item.get("children")
    results = [candidate]
    if isinstance(children, list):
        next_container = f"{container}::{name}" if container else name
        for child in children:
            if isinstance(child, dict):
                results.extend(document_symbol_candidates(path, child, query=query, container=next_container))
    return results


def symbol_location_to_dict(location: Location, project_root: Path) -> dict[str, Any]:
    return {
        "path": str(location.path),
        "relative_path": relative_path(location.path, project_root),
        "range": location.range.to_lsp(),
        "line": location.range.start.line + 1,
        "character": location.range.start.character + 1,
        "column": location.range.start.character + 1,
    }


def extract_source(
    path: Path,
    position: Position,
    *,
    symbol_name: str = "",
    kind: int | None = None,
    preferred_range: Range | None = None,
) -> SourceSnippet:
    text = path.read_text(encoding="utf-8", errors="replace")
    offsets = line_offsets(text)

    if preferred_range is not None and range_has_body_shape(text, offsets, preferred_range):
        return slice_range(text, offsets, preferred_range)

    masked = mask_comments_and_strings(text)
    offset = position_to_offset(offsets, position)
    symbol_leaf = leaf_name(symbol_name)

    if kind in CLASSLIKE_KINDS:
        snippet = extract_classlike(text, masked, offsets, offset, symbol_leaf)
        if snippet is not None:
            return snippet

    if kind in FUNCTIONLIKE_KINDS or kind is None:
        snippet = extract_functionlike(text, masked, offsets, offset)
        if snippet is not None:
            return snippet

    snippet = extract_classlike(text, masked, offsets, offset, symbol_leaf)
    if snippet is not None:
        return snippet

    return fallback_context(text, offsets, position)


def range_has_body_shape(text: str, offsets: list[int], value: Range) -> bool:
    start = position_to_offset(offsets, value.start)
    end = position_to_offset(offsets, value.end)
    if end <= start:
        return False
    snippet = text[start:end]
    if "\n" not in snippet:
        return False
    return "{" in snippet or ";" in snippet


def slice_range(text: str, offsets: list[int], value: Range) -> SourceSnippet:
    start = position_to_offset(offsets, value.start)
    end = position_to_offset(offsets, value.end)
    source = text[start:end]
    return SourceSnippet(source=source, range=value)


def position_to_offset(offsets: list[int], position: Position) -> int:
    if not offsets:
        return 0
    line = max(0, min(position.line, len(offsets) - 1))
    line_start = offsets[line]
    line_end = offsets[line + 1] if line + 1 < len(offsets) else None
    absolute = line_start + max(0, position.character)
    if line_end is None:
        return absolute
    return min(absolute, line_end)


def offset_to_position_from_offsets(offsets: list[int], offset: int) -> Position:
    lo = 0
    hi = len(offsets) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if offsets[mid] <= offset:
            lo = mid + 1
        else:
            hi = mid - 1
    line = max(0, hi)
    return Position(line=line, character=max(0, offset - offsets[line]))


def leaf_name(symbol_name: str) -> str:
    name = symbol_name.split("(")[0].strip()
    if "::" in name:
        name = name.rsplit("::", 1)[1]
    return name.strip()


def extract_classlike(
    text: str,
    masked: str,
    offsets: list[int],
    offset: int,
    symbol_leaf: str,
) -> SourceSnippet | None:
    window_start = max(0, offset - 6000)
    prefix = masked[window_start : min(len(masked), offset + 1000)]
    if symbol_leaf:
        name_pattern = re.escape(symbol_leaf)
        pattern = re.compile(rf"\b(class|struct|union|enum)\s+(?:class\s+|struct\s+)?{name_pattern}\b")
    else:
        pattern = re.compile(r"\b(class|struct|union|enum)\s+[A-Za-z_]\w*\b")

    matches = list(pattern.finditer(prefix))
    if not matches:
        return None

    match = matches[-1]
    start = window_start + match.start()
    body_or_end = find_next_top_level(masked, window_start + match.end(), {"{", ";"})
    if body_or_end is None:
        return None

    if masked[body_or_end] == ";":
        end = body_or_end + 1
    else:
        close = find_matching(masked, body_or_end, "{", "}")
        if close is None:
            return None
        end = consume_trailing_semicolon(masked, close + 1)

    start = extend_start_for_prefix_lines(text, start)
    return snippet_from_offsets(text, offsets, start, end)


def extract_functionlike(text: str, masked: str, offsets: list[int], offset: int) -> SourceSnippet | None:
    start = logical_start(masked, offset)
    end_marker = find_function_end_marker(masked, offset)
    if end_marker is None:
        return None

    if masked[end_marker] == "{":
        close = find_matching(masked, end_marker, "{", "}")
        if close is None:
            return None
        end = consume_optional_function_suffix(masked, close + 1)
    else:
        end = end_marker + 1

    start = trim_leading_noise(text, start)
    start = extend_start_for_prefix_lines(text, start)
    if end <= start:
        return None
    return snippet_from_offsets(text, offsets, start, end)


def find_next_top_level(masked: str, start: int, targets: set[str]) -> int | None:
    paren = 0
    bracket = 0
    angle = 0
    for index in range(start, len(masked)):
        char = masked[index]
        if char == "(":
            paren += 1
        elif char == ")":
            paren = max(0, paren - 1)
        elif char == "[":
            bracket += 1
        elif char == "]":
            bracket = max(0, bracket - 1)
        elif char == "<" and paren == 0 and bracket == 0:
            angle += 1
        elif char == ">" and angle:
            angle -= 1
        elif char in targets and paren == 0 and bracket == 0 and angle == 0:
            return index
    return None


def find_function_end_marker(masked: str, offset: int) -> int | None:
    paren = 0
    bracket = 0
    for index in range(offset, len(masked)):
        char = masked[index]
        if char == "(":
            paren += 1
        elif char == ")":
            paren = max(0, paren - 1)
        elif char == "[":
            bracket += 1
        elif char == "]":
            bracket = max(0, bracket - 1)
        elif char in {"{", ";"} and paren == 0 and bracket == 0:
            return index
    return None


def find_matching(masked: str, open_offset: int, open_char: str, close_char: str) -> int | None:
    depth = 0
    for index in range(open_offset, len(masked)):
        char = masked[index]
        if char == open_char:
            depth += 1
        elif char == close_char:
            depth -= 1
            if depth == 0:
                return index
    return None


def logical_start(masked: str, offset: int) -> int:
    brace = paren = bracket = 0
    context_depth = brace_depth_at(masked, offset)
    last = 0
    index = 0
    while index < min(offset, len(masked)):
        char = masked[index]
        if char == "{":
            brace += 1
        elif char == "}":
            brace = max(0, brace - 1)
            if brace == context_depth and paren == 0 and bracket == 0:
                last = index + 1
        elif char == "(":
            paren += 1
        elif char == ")":
            paren = max(0, paren - 1)
        elif char == "[":
            bracket += 1
        elif char == "]":
            bracket = max(0, bracket - 1)
        elif char == ";" and brace == context_depth and paren == 0 and bracket == 0:
            last = index + 1
        index += 1
    access_label = None
    for match in re.finditer(r"(?m)^\s*(?:public|protected|private)\s*:\s*", masked[last:offset]):
        access_label = match
    if access_label is not None:
        last += access_label.end()
    return last


def brace_depth_at(masked: str, offset: int) -> int:
    depth = 0
    for char in masked[: max(0, min(offset, len(masked)))]:
        if char == "{":
            depth += 1
        elif char == "}":
            depth = max(0, depth - 1)
    return depth


def trim_leading_noise(text: str, start: int) -> int:
    while start < len(text) and text[start].isspace():
        start += 1

    line_start = text.rfind("\n", 0, start) + 1
    access_label = re.compile(r"\s*(public|protected|private)\s*:\s*")
    match = access_label.match(text, line_start, start + 32)
    if match:
        return match.end()
    return line_start if line_start <= start else start


def extend_start_for_prefix_lines(text: str, start: int) -> int:
    line_start = text.rfind("\n", 0, start) + 1
    current = line_start
    while current > 0:
        previous_end = current - 1
        previous_start = text.rfind("\n", 0, previous_end) + 1
        line = text[previous_start:previous_end].strip()
        if (
            line.startswith("template")
            or line.startswith("[[")
            or line.startswith("__attribute__")
            or line in {"inline", "static", "constexpr"}
        ):
            current = previous_start
            continue
        break
    return current


def consume_trailing_semicolon(masked: str, offset: int) -> int:
    index = offset
    while index < len(masked) and masked[index].isspace():
        index += 1
    if index < len(masked) and masked[index] == ";":
        return index + 1
    return offset


def consume_optional_function_suffix(masked: str, offset: int) -> int:
    index = offset
    while index < len(masked) and masked[index].isspace():
        index += 1
    if index < len(masked) and masked[index] == ";":
        return index + 1
    return offset


def snippet_from_offsets(text: str, offsets: list[int], start: int, end: int) -> SourceSnippet:
    start = max(0, min(start, len(text)))
    end = max(start, min(end, len(text)))
    return SourceSnippet(
        source=text[start:end],
        range=Range(
            start=offset_to_position_from_offsets(offsets, start),
            end=offset_to_position_from_offsets(offsets, end),
        ),
    )


def fallback_context(text: str, offsets: list[int], position: Position) -> SourceSnippet:
    start_line = max(0, position.line - 5)
    end_line = min(len(offsets), position.line + 6)
    start = offsets[start_line]
    end = offsets[end_line] if end_line < len(offsets) else len(text)
    return snippet_from_offsets(text, offsets, start, end)


def locate_symbol_in_source(query: str, project_root: Path) -> SymbolCandidate | None:
    names = [part for part in query.strip().split("::") if part]
    if not names:
        return None
    leaf = names[-1]
    container = "::".join(names[:-1])
    for path in candidate_source_files(project_root, leaf):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for pattern in symbol_patterns(names):
            match = pattern.search(text)
            if not match:
                continue
            start = match.start("name") if "name" in pattern.groupindex else match.start()
            position = offset_to_position(text, start)
            return SymbolCandidate(
                leaf,
                container,
                0,
                Location(path, Range(position, Position(position.line, position.character + len(leaf)))),
                (4, len(query), 0),
            )
    return None


def candidate_source_files(project_root: Path, leaf: str) -> list[Path]:
    roots = [project_root / name for name in SOURCE_ROOTS]
    roots.append(project_root)
    seen: set[Path] = set()
    result: list[Path] = []
    for root in roots:
        if not root.exists() or not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path in seen or path.suffix.lower() not in SOURCE_SUFFIXES or not path.is_file():
                continue
            parts = set(path.parts)
            if ".git" in parts or "thirdparty" in parts:
                continue
            try:
                if leaf not in path.name and leaf not in path.read_text(encoding="utf-8", errors="ignore"):
                    continue
            except OSError:
                continue
            seen.add(path)
            result.append(path)
            if len(result) >= 200:
                return result
    return result


def symbol_patterns(names: list[str]) -> list[re.Pattern[str]]:
    leaf = re.escape(names[-1])
    if len(names) >= 2:
        owner = re.escape(names[-2])
        qualified = re.escape("::".join(names[-2:]))
        return [
            re.compile(rf"\b{owner}\s*::\s*(?P<name>{leaf})\s*\("),
            re.compile(rf"\b(?P<name>{qualified})\s*\("),
        ]
    return [re.compile(rf"\b(?P<name>{leaf})\s*\("), re.compile(rf"\b(?P<name>{leaf})\b")]


def incoming_to_dict(call: dict[str, Any], project_root: Path) -> dict[str, Any]:
    item = call.get("from") if isinstance(call.get("from"), dict) else {}
    ranges = call.get("fromRanges") if isinstance(call.get("fromRanges"), list) else []
    return {
        "from": call_item_to_dict(item, project_root),
        "call_sites": [range_to_dict(item_uri_path(item), Range.from_lsp(value), project_root) for value in ranges if isinstance(value, dict)],
    }


def outgoing_to_dict(call: dict[str, Any], project_root: Path) -> dict[str, Any]:
    item = call.get("to") if isinstance(call.get("to"), dict) else {}
    ranges = call.get("fromRanges") if isinstance(call.get("fromRanges"), list) else []
    return {
        "to": call_item_to_dict(item, project_root),
        "call_sites": [range_to_dict(item_uri_path(item), Range.from_lsp(value), project_root) for value in ranges if isinstance(value, dict)],
    }


def call_item_to_dict(item: dict[str, Any], project_root: Path) -> dict[str, Any]:
    path = item_uri_path(item)
    selection = Range.from_lsp(item.get("selectionRange") or item.get("range"))
    kind = int(item.get("kind") or 0)
    return {
        "name": str(item.get("name") or ""),
        "detail": str(item.get("detail") or ""),
        "kind": kind,
        "kind_name": SYMBOL_KINDS.get(kind, f"Kind{kind}"),
        "location": range_to_dict(path, selection, project_root),
    }


def range_to_dict(path: Path, value: Range, project_root: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "relative_path": relative_path(path, project_root),
        "line": value.start.line + 1,
        "column": value.start.character + 1,
        "range": value.to_lsp(),
        "snippet": source_line(path, value.start.line),
    }


def item_uri_path(item: dict[str, Any]) -> Path:
    return uri_to_path(str(item.get("uri") or "file:///"))


def static_outgoing_calls(item: dict[str, Any], project_root: Path, *, limit: int) -> list[dict[str, Any]]:
    path = item_uri_path(item)
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    selection = Range.from_lsp(item.get("selectionRange") or item.get("range"))
    body = extract_function_body(text, selection.start.line)
    if body is None:
        return []
    body_start, body_text = body
    masked = mask_comments_and_strings(body_text)
    skip = {"if", "for", "while", "switch", "return", "sizeof", "decltype", "static_cast", "reinterpret_cast", "const_cast", "dynamic_cast"}
    calls: list[dict[str, Any]] = []
    seen: set[tuple[str, int, int]] = set()
    for match in re.finditer(r"\b(?P<name>[A-Za-z_]\w*(?:::\w+)?|operator\s*[^\s(]+)\s*\(", masked):
        name = " ".join(body_text[match.start("name") : match.end("name")].split())
        if name in skip:
            continue
        absolute = body_start + match.start("name")
        position = offset_to_position(text, absolute)
        site = range_to_dict(path, Range(position, Position(position.line, position.character + len(name))), project_root)
        key = (name, site["line"], site["column"])
        if key in seen:
            continue
        seen.add(key)
        calls.append({"to": {"name": name, "detail": "static fallback", "kind": 12, "kind_name": "Function", "location": site}, "call_sites": [site]})
        if len(calls) >= limit:
            break
    return calls


def extract_function_body(text: str, start_line: int) -> tuple[int, str] | None:
    offsets = line_offsets(text)
    if start_line >= len(offsets):
        return None
    start = offsets[start_line]
    brace = text.find("{", start)
    semicolon = text.find(";", start)
    if brace < 0 or (semicolon >= 0 and semicolon < brace):
        return None
    depth = 0
    for index in range(brace, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return brace + 1, text[brace + 1 : index]
    return None


def mask_comments_and_strings(text: str) -> str:
    chars = list(text)
    index = 0
    while index < len(chars):
        char = chars[index]
        next_char = chars[index + 1] if index + 1 < len(chars) else ""
        if char == "/" and next_char == "/":
            chars[index] = chars[index + 1] = " "
            index += 2
            while index < len(chars) and chars[index] != "\n":
                chars[index] = " "
                index += 1
            continue
        if char == "/" and next_char == "*":
            chars[index] = chars[index + 1] = " "
            index += 2
            while index + 1 < len(chars):
                if chars[index] == "*" and chars[index + 1] == "/":
                    chars[index] = chars[index + 1] = " "
                    index += 2
                    break
                if chars[index] != "\n":
                    chars[index] = " "
                index += 1
            continue
        if char in {'"', "'"}:
            quote = char
            chars[index] = " "
            index += 1
            escaped = False
            while index < len(chars):
                current = chars[index]
                if current != "\n":
                    chars[index] = " "
                if escaped:
                    escaped = False
                elif current == "\\":
                    escaped = True
                elif current == quote:
                    index += 1
                    break
                index += 1
            continue
        index += 1
    return "".join(chars)


def normalize_hover(hover: dict[str, Any] | None) -> dict[str, Any]:
    if not hover:
        return {"text": "", "range": None}
    contents = hover.get("contents")
    if isinstance(contents, str):
        text = contents
    elif isinstance(contents, dict):
        text = str(contents.get("value") or "")
    elif isinstance(contents, list):
        parts: list[str] = []
        for item in contents:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(str(item.get("value") or ""))
        text = "\n".join(part for part in parts if part)
    else:
        text = ""
    return {"text": text.strip(), "range": hover.get("range")}


def extract_type_summary(text: str) -> dict[str, str]:
    code_blocks = re.findall(r"```(?:cpp|c\+\+|c)?\n(.*?)```", text, flags=re.DOTALL)
    candidate = code_blocks[0].strip() if code_blocks else text.strip().splitlines()[0] if text.strip() else ""
    return {"display": " ".join(candidate.split())}


def resolve_source_path(path: str | os.PathLike[str], project_root: Path) -> Path:
    source = Path(path).expanduser()
    if not source.is_absolute():
        source = project_root / source
    source = source.resolve()
    if not source.is_file():
        raise ServiceError(f"source file does not exist: {source}")
    return source


def source_line(path: Path, line: int) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    return lines[line].strip() if 0 <= line < len(lines) else ""


def relative_path(path: Path, project_root: Path) -> str | None:
    try:
        return path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return None


def has_compile_database(path: Path) -> bool:
    return (path / "compile_commands.json").is_file() or (path / "compile_flags.txt").is_file()


def find_compile_commands_dir(project_root: Path) -> Path | None:
    if has_compile_database(project_root):
        return project_root
    for relative in ("build", "out", "out/build", "cmake-build-debug", "cmake-build-release"):
        candidate = project_root / relative
        if candidate.is_dir() and has_compile_database(candidate):
            return candidate
    return None


def resolve_clangd(clangd: str) -> str | None:
    if os.path.sep in clangd:
        candidate = Path(clangd).expanduser()
        return str(candidate.resolve()) if candidate.exists() else None
    resolved = shutil.which(clangd)
    if resolved:
        return resolved
    if clangd != "clangd":
        return None
    for name in ("clangd-20", "clangd-19", "clangd-18", "clangd-17", "clangd-16", "clangd-15"):
        resolved = shutil.which(name)
        if resolved:
            return resolved
    for candidate in sorted(Path("/usr/lib").glob("llvm-*/bin/clangd"), reverse=True):
        if candidate.exists():
            return str(candidate)
    return None


def path_to_uri(path: Path) -> str:
    return path.resolve().as_uri()


def uri_to_path(uri: str) -> Path:
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        raise ValueError(f"unsupported URI: {uri}")
    return Path(unquote(parsed.path))


def language_id(path: Path) -> str:
    return "c" if path.suffix.lower() in {".c", ".h"} else "cpp"


def line_offsets(text: str) -> list[int]:
    offsets = [0]
    for match in re.finditer(r"\n", text):
        offsets.append(match.end())
    return offsets


def offset_to_position(text: str, offset: int) -> Position:
    line = text.count("\n", 0, offset)
    line_start = text.rfind("\n", 0, offset)
    return Position(line, offset if line_start < 0 else offset - line_start - 1)


def score_candidate(query: str, name: str, container: str) -> tuple[int, int, int]:
    full = f"{container}::{name}" if container else name
    leaf = query.strip().rsplit("::", 1)[-1]
    if full == query.strip():
        return (0, len(full), 0)
    if name == leaf:
        return (1, len(full), 0)
    if query.strip().lower() in full.lower():
        return (2, len(full), 0)
    return (9, len(full), 0)
