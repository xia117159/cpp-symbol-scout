from __future__ import annotations

import json
import os
import re
import shlex
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


CPP_SUFFIXES = {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx", ".ipp", ".inl"}
SKIP_DIRS = {
    ".cache",
    ".clangd",
    ".git",
    ".hg",
    ".mypy_cache",
    ".runtime",
    ".svn",
    ".venv",
    "__pycache__",
    "build",
    "cmake-build-debug",
    "cmake-build-release",
    "node_modules",
    "thirdparty",
}


@dataclass(frozen=True)
class IncludeEdge:
    source: str
    line: int
    include: str
    is_system: bool
    resolved: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DuplicateInclude:
    source: str
    include: str
    lines: list[int]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class IncludeAnalysis:
    project_root: str
    include_roots: list[str]
    files_scanned: int
    edges: list[IncludeEdge]
    duplicate_includes: list[DuplicateInclude]
    cycles: list[list[str]]

    def to_dict(self) -> dict[str, Any]:
        summary = summarize_analysis(self)
        return {
            "project_root": self.project_root,
            "include_roots": self.include_roots,
            "summary": summary,
            "edges": [edge.to_dict() for edge in self.edges],
            "duplicate_includes": [item.to_dict() for item in self.duplicate_includes],
            "cycles": self.cycles,
        }


def analyze_project(
    project_root: str | os.PathLike[str],
    *,
    include_roots: list[str | os.PathLike[str]] | None = None,
    use_compile_commands: bool = True,
) -> IncludeAnalysis:
    root = Path(project_root).expanduser().resolve()
    roots = [Path(path).expanduser().resolve() for path in include_roots or []]
    if use_compile_commands:
        roots.extend(discover_compile_command_include_roots(root))
    roots.append(root)
    roots = _dedupe_paths(roots)

    files = discover_cpp_files(root)
    edges: list[IncludeEdge] = []
    duplicates: list[DuplicateInclude] = []
    for path in files:
        parsed = parse_includes(path)
        relative_source = _relative(path, root)
        counts: dict[str, list[int]] = defaultdict(list)
        for include in parsed:
            counts[include["include"]].append(include["line"])
            resolved = resolve_include(
                include["include"],
                source=path,
                project_root=root,
                include_roots=roots,
                is_system=include["is_system"],
            )
            edges.append(
                IncludeEdge(
                    source=relative_source,
                    line=include["line"],
                    include=include["include"],
                    is_system=include["is_system"],
                    resolved=_relative(resolved, root) if resolved else None,
                )
            )
        for include, lines in counts.items():
            if len(lines) > 1:
                duplicates.append(DuplicateInclude(source=relative_source, include=include, lines=lines))

    cycles = find_cycles(edges)
    return IncludeAnalysis(
        project_root=str(root),
        include_roots=[str(path) for path in roots],
        files_scanned=len(files),
        edges=edges,
        duplicate_includes=duplicates,
        cycles=cycles,
    )


def summarize_analysis(analysis: IncludeAnalysis, *, limit: int = 20) -> dict[str, Any]:
    resolved_edges = [edge for edge in analysis.edges if edge.resolved]
    unresolved_edges = [edge for edge in analysis.edges if edge.resolved is None]
    fan_out = Counter(edge.source for edge in resolved_edges)
    fan_in = Counter(edge.resolved for edge in resolved_edges if edge.resolved)
    hotspots = []
    files = set(fan_in) | set(fan_out)
    for path in files:
        in_count = fan_in.get(path, 0)
        out_count = fan_out.get(path, 0)
        hotspots.append(
            {
                "path": path,
                "fan_in": in_count,
                "fan_out": out_count,
                "score": in_count * 3 + out_count,
            }
        )
    hotspots.sort(key=lambda item: (-item["score"], item["path"]))
    return {
        "files_scanned": analysis.files_scanned,
        "include_edges": len(analysis.edges),
        "resolved_edges": len(resolved_edges),
        "unresolved_edges": len(unresolved_edges),
        "duplicate_include_files": len(analysis.duplicate_includes),
        "cycles": len(analysis.cycles),
        "top_fan_in": _counter_items(fan_in, limit),
        "top_fan_out": _counter_items(fan_out, limit),
        "hotspots": hotspots[:limit],
    }


def file_report(analysis: IncludeAnalysis, file_path: str | os.PathLike[str]) -> dict[str, Any]:
    root = Path(analysis.project_root)
    requested = Path(file_path).expanduser()
    if requested.is_absolute():
        target = _relative(requested.resolve(), root)
    else:
        target = requested.as_posix()
    includes = [edge.to_dict() for edge in analysis.edges if edge.source == target]
    included_by = [edge.to_dict() for edge in analysis.edges if edge.resolved == target]
    duplicates = [item.to_dict() for item in analysis.duplicate_includes if item.source == target]
    return {
        "file": target,
        "includes": includes,
        "included_by": included_by,
        "duplicate_includes": duplicates,
        "fan_in": len(included_by),
        "fan_out": len([edge for edge in includes if edge.get("resolved")]),
    }


def discover_cpp_files(project_root: Path) -> list[Path]:
    result: list[Path] = []
    for directory, dirnames, filenames in os.walk(project_root):
        dirnames[:] = [
            dirname
            for dirname in dirnames
            if dirname not in SKIP_DIRS and not dirname.startswith(".cache")
        ]
        current = Path(directory)
        for filename in filenames:
            path = current / filename
            if path.suffix.lower() in CPP_SUFFIXES:
                result.append(path)
    result.sort()
    return result


def parse_includes(path: Path) -> list[dict[str, Any]]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    includes: list[dict[str, Any]] = []
    pattern = re.compile(r"^\s*#\s*include\s*([<\"])([^>\"]+)[>\"]", re.MULTILINE)
    for match in pattern.finditer(text):
        line = text.count("\n", 0, match.start()) + 1
        includes.append(
            {
                "line": line,
                "include": match.group(2).strip(),
                "is_system": match.group(1) == "<",
            }
        )
    return includes


def resolve_include(
    include: str,
    *,
    source: Path,
    project_root: Path,
    include_roots: list[Path],
    is_system: bool,
) -> Path | None:
    candidates: list[Path] = []
    if not is_system:
        candidates.append(source.parent / include)
    candidates.extend(root / include for root in include_roots)
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved.exists() and resolved.is_file():
            try:
                resolved.relative_to(project_root)
            except ValueError:
                return resolved
            return resolved
    return None


def discover_compile_command_include_roots(project_root: Path) -> list[Path]:
    compile_commands = project_root / "compile_commands.json"
    if not compile_commands.exists():
        return []
    try:
        commands = json.loads(compile_commands.read_text(encoding="utf-8"))
    except Exception:
        return []
    roots: list[Path] = []
    if not isinstance(commands, list):
        return roots
    for entry in commands:
        if not isinstance(entry, dict):
            continue
        directory = Path(entry.get("directory") or project_root).expanduser()
        if not directory.is_absolute():
            directory = (project_root / directory).resolve()
        args = entry.get("arguments")
        if isinstance(args, list):
            tokens = [str(token) for token in args]
        else:
            command = str(entry.get("command") or "")
            try:
                tokens = shlex.split(command)
            except ValueError:
                tokens = command.split()
        roots.extend(_include_roots_from_tokens(tokens, directory))
    return _dedupe_paths(roots)


def _include_roots_from_tokens(tokens: list[str], directory: Path) -> list[Path]:
    roots: list[Path] = []
    index = 0
    joined_flags = ("-I", "-isystem", "-iquote", "/I")
    while index < len(tokens):
        token = tokens[index]
        value: str | None = None
        if token in joined_flags and index + 1 < len(tokens):
            value = tokens[index + 1]
            index += 1
        elif token.startswith("-I") and len(token) > 2:
            value = token[2:]
        elif token.startswith("/I") and len(token) > 2:
            value = token[2:]
        elif token.startswith("-isystem") and len(token) > len("-isystem"):
            value = token[len("-isystem") :]
        elif token.startswith("-iquote") and len(token) > len("-iquote"):
            value = token[len("-iquote") :]
        if value:
            path = Path(value)
            if not path.is_absolute():
                path = (directory / path).resolve()
            roots.append(path)
        index += 1
    return roots


def find_cycles(edges: list[IncludeEdge]) -> list[list[str]]:
    adjacency: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        if edge.resolved:
            adjacency[edge.source].add(edge.resolved)

    index = 0
    stack: list[str] = []
    on_stack: set[str] = set()
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    components: list[list[str]] = []

    def strongconnect(node: str) -> None:
        nonlocal index
        indices[node] = index
        lowlinks[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)

        for neighbor in adjacency.get(node, set()):
            if neighbor not in indices:
                strongconnect(neighbor)
                lowlinks[node] = min(lowlinks[node], lowlinks[neighbor])
            elif neighbor in on_stack:
                lowlinks[node] = min(lowlinks[node], indices[neighbor])

        if lowlinks[node] == indices[node]:
            component: list[str] = []
            while True:
                current = stack.pop()
                on_stack.remove(current)
                component.append(current)
                if current == node:
                    break
            if len(component) > 1:
                components.append(sorted(component))

    for node in sorted(adjacency):
        if node not in indices:
            strongconnect(node)
    components.sort(key=lambda item: (-len(item), item))
    return components


def _counter_items(counter: Counter[str], limit: int) -> list[dict[str, Any]]:
    return [
        {"path": path, "count": count}
        for path, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))[:limit]
    ]


def _relative(path: Path, project_root: Path) -> str:
    try:
        return path.resolve().relative_to(project_root).as_posix()
    except ValueError:
        return str(path)


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    result: list[Path] = []
    for path in paths:
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)
        result.append(resolved)
    return result

