from __future__ import annotations

import json
import queue
import subprocess
import threading
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any, BinaryIO

from .models import Location, Position, Range, SymbolCandidate
from .uri import path_to_uri


class LspError(RuntimeError):
    """Raised when clangd returns an LSP error or cannot be contacted."""


class ClangdClient:
    def __init__(
        self,
        *,
        clangd_path: str,
        project_root: Path,
        compile_commands_dir: Path | None,
        log_file: Path | None = None,
    ) -> None:
        self.clangd_path = clangd_path
        self.project_root = project_root
        self.compile_commands_dir = compile_commands_dir
        self.log_file = log_file
        self._proc: subprocess.Popen[bytes] | None = None
        self._next_id = 1
        self._pending: dict[int, queue.Queue[dict[str, Any]]] = {}
        self._pending_lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._reader: threading.Thread | None = None
        self._stderr: threading.Thread | None = None
        self._stderr_file: BinaryIO | None = None
        self._diagnostics: list[dict[str, Any]] = []
        self._opened: dict[Path, int] = {}
        self._shutdown = False

    def start(self, *, timeout: float = 30.0) -> None:
        if self._proc is not None:
            return

        args = [
            self.clangd_path,
            "--background-index",
            "--clang-tidy=false",
            "--header-insertion=never",
            "--completion-style=detailed",
        ]
        if self.compile_commands_dir is not None:
            args.append(f"--compile-commands-dir={self.compile_commands_dir}")

        stderr_target: int | Any
        if self.log_file is not None:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            self._stderr_file = self.log_file.open("ab")
            stderr_target = self._stderr_file
        else:
            stderr_target = subprocess.DEVNULL

        self._proc = subprocess.Popen(
            args,
            cwd=self.project_root,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=stderr_target,
        )
        self._reader = threading.Thread(target=self._read_loop, name="clangd-lsp-reader", daemon=True)
        self._reader.start()

        init_result = self.request(
            "initialize",
            {
                "processId": None,
                "rootUri": path_to_uri(self.project_root),
                "workspaceFolders": [
                    {"uri": path_to_uri(self.project_root), "name": self.project_root.name}
                ],
                "capabilities": {
                    "workspace": {
                        "symbol": {"resolveSupport": {"properties": ["location.range"]}},
                        "workspaceFolders": True,
                    },
                    "textDocument": {
                        "documentSymbol": {"hierarchicalDocumentSymbolSupport": True},
                        "definition": {"linkSupport": True},
                        "implementation": {"linkSupport": True},
                    },
                },
            },
            timeout=timeout,
        )
        if not isinstance(init_result, dict):
            raise LspError("clangd initialize returned an invalid response")
        self.notify("initialized", {})

    def stop(self) -> None:
        if self._proc is None:
            return
        if not self._shutdown:
            try:
                self.request("shutdown", None, timeout=5.0)
                self.notify("exit", None)
            except Exception:
                self._proc.terminate()
            self._shutdown = True
        try:
            self._proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            self._proc.kill()
            self._proc.wait(timeout=5.0)
        if self._stderr_file is not None:
            self._stderr_file.close()
            self._stderr_file = None

    def request(self, method: str, params: Any, *, timeout: float = 10.0) -> Any:
        if self._proc is None or self._proc.stdin is None:
            raise LspError("clangd is not running")
        request_id = self._allocate_id()
        responses: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)
        with self._pending_lock:
            self._pending[request_id] = responses
        try:
            self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
            message = responses.get(timeout=timeout)
        except queue.Empty as exc:
            raise LspError(f"clangd request timed out: {method}") from exc
        finally:
            with self._pending_lock:
                self._pending.pop(request_id, None)

        if "error" in message:
            error = message["error"]
            if isinstance(error, dict):
                raise LspError(f"clangd {method} error {error.get('code')}: {error.get('message')}")
            raise LspError(f"clangd {method} error: {error}")
        return message.get("result")

    def notify(self, method: str, params: Any) -> None:
        if self._proc is None or self._proc.stdin is None:
            raise LspError("clangd is not running")
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def workspace_symbol(self, query: str, *, limit: int = 20, timeout: float = 8.0) -> list[SymbolCandidate]:
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
            kind = int(item.get("kind") or 0)
            candidates.append(
                SymbolCandidate(
                    name=name,
                    container_name=container,
                    kind=kind,
                    location=location,
                    score=_score_candidate(query, name, container),
                )
            )
        candidates.sort(key=lambda candidate: candidate.score)
        return candidates[:limit]

    def definition(
        self,
        path: Path,
        position: Position,
        *,
        timeout: float = 4.0,
    ) -> list[Location]:
        return self._location_request("textDocument/definition", path, position, timeout=timeout)

    def implementation(
        self,
        path: Path,
        position: Position,
        *,
        timeout: float = 4.0,
    ) -> list[Location]:
        return self._location_request("textDocument/implementation", path, position, timeout=timeout)

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
                    candidates.extend(_document_symbol_candidates(path, item, query=query))
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
                            score=_score_candidate(query, name, container),
                        )
                    )
        candidates.sort(key=lambda candidate: candidate.score)
        return candidates[:limit]

    def _location_request(
        self,
        method: str,
        path: Path,
        position: Position,
        *,
        timeout: float,
    ) -> list[Location]:
        self.open_document(path)
        result = self.request(
            method,
            {
                "textDocument": {"uri": path_to_uri(path)},
                "position": position.to_lsp(),
            },
            timeout=timeout,
        )
        return list(_locations_from_result(result))

    def open_document(self, path: Path) -> None:
        path = path.resolve()
        if path in self._opened:
            return
        text = path.read_text(encoding="utf-8", errors="replace")
        version = self._opened.get(path, 0) + 1
        self._opened[path] = version
        self.notify(
            "textDocument/didOpen",
            {
                "textDocument": {
                    "uri": path_to_uri(path),
                    "languageId": _language_id(path),
                    "version": version,
                    "text": text,
                }
            },
        )

    def wait_background_index(self, *, quiet_period: float = 1.0, timeout: float = 120.0) -> bool:
        deadline = time.monotonic() + timeout
        last_count = len(self._diagnostics)
        stable_since = time.monotonic()
        while time.monotonic() < deadline:
            time.sleep(0.25)
            count = len(self._diagnostics)
            if count == last_count:
                if time.monotonic() - stable_since >= quiet_period:
                    return True
            else:
                last_count = count
                stable_since = time.monotonic()
        return False

    def _allocate_id(self) -> int:
        with self._pending_lock:
            request_id = self._next_id
            self._next_id += 1
        return request_id

    def _send(self, payload: dict[str, Any]) -> None:
        assert self._proc is not None
        assert self._proc.stdin is not None
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        with self._write_lock:
            self._proc.stdin.write(header + body)
            self._proc.stdin.flush()

    def _read_loop(self) -> None:
        assert self._proc is not None
        assert self._proc.stdout is not None
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
                    decoded = line.decode("ascii", errors="replace")
                    name, _, value = decoded.partition(":")
                    headers[name.strip().lower()] = value.strip()
                content_length = int(headers.get("content-length", "0"))
                if content_length <= 0:
                    continue
                body = stdout.read(content_length)
                if not body:
                    return
                message = json.loads(body.decode("utf-8"))
            except Exception:
                return
            self._dispatch_message(message)

    def _dispatch_message(self, message: dict[str, Any]) -> None:
        if "id" in message:
            try:
                request_id = int(message["id"])
            except (TypeError, ValueError):
                return
            with self._pending_lock:
                responses = self._pending.get(request_id)
            if responses is not None:
                responses.put(message)
            return

        method = message.get("method")
        if method == "textDocument/publishDiagnostics":
            params = message.get("params")
            if isinstance(params, dict):
                self._diagnostics.append(params)


def _locations_from_result(result: Any) -> Iterable[Location]:
    if result is None:
        return []
    if isinstance(result, dict):
        try:
            return [Location.from_lsp(result)]
        except Exception:
            return []
    if isinstance(result, list):
        locations: list[Location] = []
        for item in result:
            if not isinstance(item, dict):
                continue
            try:
                locations.append(Location.from_lsp(item))
            except Exception:
                continue
        return locations
    return []


def _document_symbol_candidates(
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
    current_container = container
    candidate = SymbolCandidate(
        name=name,
        container_name=current_container,
        kind=kind,
        location=Location(path=path, range=symbol_range),
        score=_score_candidate(query, name, current_container),
    )
    children = item.get("children")
    results = [candidate]
    if isinstance(children, list):
        next_container = f"{current_container}::{name}" if current_container else name
        for child in children:
            if isinstance(child, dict):
                results.extend(
                    _document_symbol_candidates(
                        path,
                        child,
                        query=query,
                        container=next_container,
                    )
                )
    return results


def _language_id(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".c", ".h"}:
        return "c"
    if suffix in {".cc", ".cpp", ".cxx", ".hpp", ".hh", ".hxx", ".ipp", ".inl"}:
        return "cpp"
    return "cpp"


def _score_candidate(query: str, name: str, container: str) -> tuple[int, int, int]:
    query_norm = query.strip()
    leaf = query_norm.rsplit("::", 1)[-1]
    full = f"{container}::{name}" if container else name
    full_lower = full.lower()
    name_lower = name.lower()
    query_lower = query_norm.lower()
    leaf_lower = leaf.lower()

    if full == query_norm:
        tier = 0
    elif name == leaf and (not container or container in query_norm or "::" not in query_norm):
        tier = 1
    elif full_lower == query_lower:
        tier = 2
    elif name_lower == leaf_lower:
        tier = 3
    elif query_lower in full_lower:
        tier = 4
    else:
        tier = 5
    return (tier, len(full), len(name))
