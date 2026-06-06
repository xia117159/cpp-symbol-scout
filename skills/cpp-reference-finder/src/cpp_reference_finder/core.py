from __future__ import annotations

import json
import os
import queue
import re
import shutil
import subprocess
import threading
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


class ToolError(RuntimeError):
    pass


@dataclass(frozen=True)
class Position:
    line: int
    character: int

    @classmethod
    def from_lsp(cls, value: dict[str, Any]) -> "Position":
        return cls(line=int(value["line"]), character=int(value["character"]))

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
        return cls(path=uri_to_path(uri), range=Range.from_lsp(range_value))

    def to_dict(self, project_root: Path | None = None) -> dict[str, Any]:
        path = self.path
        relative = None
        if project_root is not None:
            try:
                relative = path.resolve().relative_to(project_root.resolve()).as_posix()
            except ValueError:
                relative = None
        return {
            "path": str(path),
            "relative_path": relative,
            "line": self.range.start.line + 1,
            "column": self.range.start.character + 1,
            "range": self.range.to_lsp(),
        }


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


@dataclass(frozen=True)
class ReferenceResult:
    query: str
    symbol: SymbolCandidate | None
    position: Location
    references: list[Location]
    snippets: dict[str, str]
    include_declaration: bool

    def to_dict(self, project_root: Path) -> dict[str, Any]:
        return {
            "query": self.query,
            "symbol": symbol_to_dict(self.symbol, project_root) if self.symbol else None,
            "position": self.position.to_dict(project_root),
            "include_declaration": self.include_declaration,
            "reference_count": len(self.references),
            "references": [
                {**location.to_dict(project_root), "snippet": self.snippets.get(location_key(location), "")}
                for location in self.references
            ],
        }


def symbol_to_dict(symbol: SymbolCandidate, project_root: Path) -> dict[str, Any]:
    return {
        "name": symbol.name,
        "full_name": symbol.full_name,
        "kind": symbol.kind,
        "kind_name": symbol.kind_name,
        "location": symbol.location.to_dict(project_root),
    }


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
            raise ToolError(f"project path is not a directory: {project_root}")
        clangd_path = resolve_clangd(clangd)
        if not clangd_path:
            raise ToolError("clangd was not found. Install clangd or pass --clangd.")
        if compile_commands_dir is None:
            db_dir = find_compile_commands_dir(project_root)
        else:
            db_dir = Path(compile_commands_dir).expanduser().resolve()
            if not db_dir.is_dir() or not has_compile_database(db_dir):
                raise ToolError(f"invalid compile commands directory: {db_dir}")
        if require_compile_db and db_dir is None:
            raise ToolError("no compile_commands.json or compile_flags.txt found")
        return cls(project_root=project_root, clangd_path=clangd_path, compile_commands_dir=db_dir)


class ClangdClient:
    def __init__(self, config: ProjectConfig) -> None:
        self.config = config
        self._proc: subprocess.Popen[bytes] | None = None
        self._next_id = 1
        self._pending: dict[int, queue.Queue[dict[str, Any]]] = {}
        self._pending_lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._reader: threading.Thread | None = None
        self._opened: set[Path] = set()

    def __enter__(self) -> "ClangdClient":
        self.start()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.stop()

    def start(self, *, timeout: float = 30.0) -> None:
        args = [
            self.config.clangd_path,
            "--background-index",
            "--clang-tidy=false",
            "--header-insertion=never",
            "--completion-style=detailed",
        ]
        if self.config.compile_commands_dir is not None:
            args.append(f"--compile-commands-dir={self.config.compile_commands_dir}")
        self._proc = subprocess.Popen(
            args,
            cwd=self.config.project_root,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()
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
                        "definition": {"linkSupport": True},
                        "references": {},
                        "documentSymbol": {"hierarchicalDocumentSymbolSupport": True},
                    },
                },
            },
            timeout=timeout,
        )
        if not isinstance(result, dict):
            raise ToolError("clangd initialize failed")
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

    def request(self, method: str, params: Any, *, timeout: float = 10.0) -> Any:
        if self._proc is None or self._proc.stdin is None:
            raise ToolError("clangd is not running")
        request_id = self._allocate_id()
        response_queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)
        with self._pending_lock:
            self._pending[request_id] = response_queue
        try:
            self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
            message = response_queue.get(timeout=timeout)
        except queue.Empty as exc:
            raise ToolError(f"clangd request timed out: {method}") from exc
        finally:
            with self._pending_lock:
                self._pending.pop(request_id, None)
        if "error" in message:
            raise ToolError(f"clangd {method} error: {message['error']}")
        return message.get("result")

    def notify(self, method: str, params: Any) -> None:
        if self._proc is None or self._proc.stdin is None:
            raise ToolError("clangd is not running")
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def open_document(self, path: Path) -> None:
        path = path.resolve()
        if path in self._opened:
            return
        self.notify(
            "textDocument/didOpen",
            {
                "textDocument": {
                    "uri": path_to_uri(path),
                    "languageId": language_id(path),
                    "version": 1,
                    "text": path.read_text(encoding="utf-8", errors="replace"),
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
        candidates.sort(key=lambda candidate: candidate.score)
        return candidates[:limit]

    def references(
        self,
        path: Path,
        position: Position,
        *,
        include_declaration: bool,
        timeout: float = 10.0,
    ) -> list[Location]:
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

    def definition(self, path: Path, position: Position, *, timeout: float = 8.0) -> list[Location]:
        self.open_document(path)
        result = self.request(
            "textDocument/definition",
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
            request_id = message.get("id")
            if request_id is None:
                continue
            with self._pending_lock:
                response_queue = self._pending.get(int(request_id))
            if response_queue is not None:
                response_queue.put(message)


def find_references_by_symbol(
    query: str,
    config: ProjectConfig,
    *,
    include_declaration: bool = False,
    limit: int = 50,
    timeout: float = 10.0,
) -> ReferenceResult:
    with ClangdClient(config) as client:
        symbols = client.workspace_symbol(query, limit=20, timeout=timeout)
        symbol = symbols[0] if symbols else locate_symbol_in_source(query, config.project_root)
        if symbol is None:
            raise ToolError(f"no workspace symbol or source match found for {query}")
        position = symbol.location.range.start
        refs = client.references(
            symbol.location.path,
            position,
            include_declaration=include_declaration,
            timeout=timeout,
        )
        refs = dedupe_locations(refs)[:limit]
        snippets = {location_key(location): source_line(location.path, location.range.start.line) for location in refs}
        return ReferenceResult(
            query=query,
            symbol=symbol,
            position=symbol.location,
            references=refs,
            snippets=snippets,
            include_declaration=include_declaration,
        )


def find_references_at(
    file_path: str | os.PathLike[str],
    line: int,
    column: int,
    config: ProjectConfig,
    *,
    include_declaration: bool = False,
    limit: int = 50,
    timeout: float = 10.0,
) -> ReferenceResult:
    path = resolve_source_path(file_path, config.project_root)
    position = Position(line=max(0, line - 1), character=max(0, column - 1))
    with ClangdClient(config) as client:
        definitions = client.definition(path, position, timeout=timeout)
        symbol_location = definitions[0] if definitions else Location(path=path, range=Range(position, position))
        refs = client.references(path, position, include_declaration=include_declaration, timeout=timeout)
        refs = dedupe_locations(refs)[:limit]
        snippets = {location_key(location): source_line(location.path, location.range.start.line) for location in refs}
        return ReferenceResult(
            query=f"{path}:{line}:{column}",
            symbol=None,
            position=symbol_location,
            references=refs,
            snippets=snippets,
            include_declaration=include_declaration,
        )


def resolve_source_path(path: str | os.PathLike[str], project_root: Path) -> Path:
    source = Path(path).expanduser()
    if not source.is_absolute():
        source = project_root / source
    source = source.resolve()
    if not source.is_file():
        raise ToolError(f"source file does not exist: {source}")
    return source


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
    seen: set[str] = set()
    result: list[Location] = []
    for location in locations:
        key = location_key(location)
        if key in seen:
            continue
        seen.add(key)
        result.append(location)
    result.sort(key=lambda item: (str(item.path), item.range.start.line, item.range.start.character))
    return result


def location_key(location: Location) -> str:
    return f"{location.path}:{location.range.start.line}:{location.range.start.character}"


def source_line(path: Path, line: int) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    if 0 <= line < len(lines):
        return lines[line].strip()
    return ""


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
    suffix = path.suffix.lower()
    if suffix in {".c", ".h"}:
        return "c"
    return "cpp"


def score_candidate(query: str, name: str, container: str) -> tuple[int, int, int]:
    query_norm = query.strip()
    leaf = query_norm.rsplit("::", 1)[-1]
    full = f"{container}::{name}" if container else name
    if full == query_norm:
        return (0, len(full), 0)
    if name == leaf:
        return (1, len(full), 0)
    if full.endswith(f"::{query_norm}") or full.endswith(f"::{leaf}"):
        return (2, len(full), 0)
    if query_norm.lower() in full.lower():
        return (3, len(full), 0)
    return (9, len(full), 0)


def parse_line_column(value: str) -> tuple[str, int, int]:
    match = re.match(r"^(.*):(\d+):(\d+)$", value)
    if not match:
        raise ToolError("expected location format path:line:column")
    return match.group(1), int(match.group(2)), int(match.group(3))


def locate_symbol_in_source(query: str, project_root: Path) -> SymbolCandidate | None:
    names = [part for part in query.strip().split("::") if part]
    if not names:
        return None
    leaf = names[-1]
    container = "::".join(names[:-1])
    patterns = symbol_patterns(names)
    for path in candidate_source_files(project_root, leaf):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for pattern in patterns:
            match = pattern.search(text)
            if not match:
                continue
            start = match.start("name") if "name" in pattern.groupindex else match.start()
            position = offset_to_position(text, start)
            location = Location(path=path, range=Range(position, Position(position.line, position.character + len(leaf))))
            return SymbolCandidate(
                name=leaf,
                container_name=container,
                kind=0,
                location=location,
                score=(4, len(query), 0),
            )
    return None


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


def candidate_source_files(project_root: Path, leaf: str) -> list[Path]:
    suffixes = {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx", ".ipp", ".inl"}
    roots = [project_root / name for name in ("core", "scene", "servers", "editor", "modules", "drivers", "platform")]
    roots.append(project_root)
    seen: set[Path] = set()
    result: list[Path] = []
    for root in roots:
        if not root.exists() or not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path in seen or path.suffix.lower() not in suffixes or not path.is_file():
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


def offset_to_position(text: str, offset: int) -> Position:
    line = text.count("\n", 0, offset)
    line_start = text.rfind("\n", 0, offset)
    character = offset if line_start < 0 else offset - line_start - 1
    return Position(line=line, character=character)
