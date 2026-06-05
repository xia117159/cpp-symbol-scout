from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


HEADER_SUFFIXES = {".h", ".hh", ".hpp", ".hxx"}
SOURCE_SUFFIXES = {".c", ".cc", ".cpp", ".cxx", ".ipp", ".inl"}
ALL_SUFFIXES = HEADER_SUFFIXES | SOURCE_SUFFIXES
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
class Declaration:
    name: str
    qualified_name: str
    kind: str
    path: str
    line: int
    column: int
    include: str
    is_definition: bool
    snippet: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class IncludeFinderIndex:
    project_root: str
    declarations: list[Declaration]

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_root": self.project_root,
            "declarations": [declaration.to_dict() for declaration in self.declarations],
        }


def build_index(
    project_root: str | os.PathLike[str],
    *,
    include_roots: list[str | os.PathLike[str]] | None = None,
    all_files: bool = False,
) -> IncludeFinderIndex:
    root = Path(project_root).expanduser().resolve()
    roots = [Path(path).expanduser().resolve() for path in include_roots or []]
    declarations: list[Declaration] = []
    for path in discover_cpp_files(root, all_files=all_files):
        declarations.extend(parse_declarations(path, project_root=root, include_roots=roots))
    declarations.sort(key=lambda item: (item.qualified_name.lower(), item.path, item.line, item.kind))
    return IncludeFinderIndex(project_root=str(root), declarations=declarations)


def find_declarations(
    index: IncludeFinderIndex,
    query: str,
    *,
    limit: int = 10,
) -> list[Declaration]:
    query = query.strip()
    if not query:
        return []
    scored: list[tuple[tuple[int, int, int, int, str, int], Declaration]] = []
    for declaration in index.declarations:
        score = _match_score(declaration, query)
        if score is not None:
            scored.append((score, declaration))
    scored.sort(key=lambda item: item[0])
    return [declaration for _score, declaration in scored[:limit]]


def save_index(index: IncludeFinderIndex, path: str | os.PathLike[str]) -> None:
    output = Path(path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(index.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")


def load_index(path: str | os.PathLike[str]) -> IncludeFinderIndex:
    payload = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    declarations = [Declaration(**item) for item in payload.get("declarations", [])]
    return IncludeFinderIndex(
        project_root=str(payload.get("project_root") or ""),
        declarations=declarations,
    )


def discover_cpp_files(project_root: Path, *, all_files: bool) -> list[Path]:
    suffixes = ALL_SUFFIXES if all_files else HEADER_SUFFIXES
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
            if path.suffix.lower() in suffixes:
                result.append(path)
    result.sort()
    return result


def parse_declarations(
    path: Path,
    *,
    project_root: Path,
    include_roots: list[Path],
) -> list[Declaration]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    masked = mask_comments_and_strings(text)
    offsets = line_offsets(text)
    scopes = _scope_ranges(masked)
    declarations: list[Declaration] = []
    seen: set[tuple[str, str, int, str]] = set()

    for match in _type_declaration_pattern().finditer(masked):
        if _is_enum_class_keyword(masked, match.start()):
            continue
        kind = match.group(1)
        name = match.group(2)
        declaration = _make_declaration(
            text=text,
            masked=masked,
            offsets=offsets,
            scopes=scopes,
            path=path,
            project_root=project_root,
            include_roots=include_roots,
            name=name,
            kind=kind,
            offset=match.start(),
            name_offset=match.start(2),
        )
        if declaration is not None:
            key = (declaration.qualified_name, declaration.kind, declaration.line, declaration.path)
            if key not in seen:
                declarations.append(declaration)
                seen.add(key)

    for match in _enum_declaration_pattern().finditer(masked):
        name = match.group(2)
        declaration = _make_declaration(
            text=text,
            masked=masked,
            offsets=offsets,
            scopes=scopes,
            path=path,
            project_root=project_root,
            include_roots=include_roots,
            name=name,
            kind="enum class" if match.group(1) else "enum",
            offset=match.start(),
            name_offset=match.start(2),
        )
        if declaration is not None:
            key = (declaration.qualified_name, declaration.kind, declaration.line, declaration.path)
            if key not in seen:
                declarations.append(declaration)
                seen.add(key)

    for match in re.finditer(r"(?m)^\s*using\s+([A-Za-z_]\w*)\s*=", masked):
        name = match.group(1)
        declaration = _line_declaration(
            text=text,
            offsets=offsets,
            scopes=scopes,
            path=path,
            project_root=project_root,
            include_roots=include_roots,
            name=name,
            kind="using",
            offset=match.start(),
            name_offset=match.start(1),
        )
        declarations.append(declaration)

    for match in re.finditer(r"(?m)^\s*typedef\b(?P<body>[^;]+);", masked):
        body = match.group("body")
        names = re.findall(r"\b([A-Za-z_]\w*)\b", body)
        if not names:
            continue
        name = names[-1]
        declaration = _line_declaration(
            text=text,
            offsets=offsets,
            scopes=scopes,
            path=path,
            project_root=project_root,
            include_roots=include_roots,
            name=name,
            kind="typedef",
            offset=match.start(),
            name_offset=match.start() + match.group(0).find(name),
        )
        declarations.append(declaration)

    return declarations


def mask_comments_and_strings(text: str) -> str:
    chars = list(text)
    i = 0
    while i < len(chars):
        ch = chars[i]
        nxt = chars[i + 1] if i + 1 < len(chars) else ""
        if ch == "/" and nxt == "/":
            chars[i] = chars[i + 1] = " "
            i += 2
            while i < len(chars) and chars[i] != "\n":
                chars[i] = " "
                i += 1
            continue
        if ch == "/" and nxt == "*":
            chars[i] = chars[i + 1] = " "
            i += 2
            while i + 1 < len(chars):
                if chars[i] == "*" and chars[i + 1] == "/":
                    chars[i] = chars[i + 1] = " "
                    i += 2
                    break
                if chars[i] != "\n":
                    chars[i] = " "
                i += 1
            continue
        if ch in {"'", '"'}:
            quote = ch
            chars[i] = " "
            i += 1
            escaped = False
            while i < len(chars):
                current = chars[i]
                if current != "\n":
                    chars[i] = " "
                if escaped:
                    escaped = False
                elif current == "\\":
                    escaped = True
                elif current == quote:
                    i += 1
                    break
                i += 1
            continue
        i += 1
    return "".join(chars)


def line_offsets(text: str) -> list[int]:
    offsets = [0]
    for match in re.finditer(r"\n", text):
        offsets.append(match.end())
    return offsets


def offset_to_line_column(offsets: list[int], offset: int) -> tuple[int, int]:
    low = 0
    high = len(offsets) - 1
    while low <= high:
        mid = (low + high) // 2
        if offsets[mid] <= offset:
            low = mid + 1
        else:
            high = mid - 1
    line_index = max(0, high)
    return line_index + 1, offset - offsets[line_index] + 1


def _type_declaration_pattern() -> re.Pattern[str]:
    return re.compile(r"\b(class|struct|union)\s+(?:[A-Za-z_]\w+\s+)*([A-Za-z_]\w*)\b")


def _enum_declaration_pattern() -> re.Pattern[str]:
    return re.compile(r"\benum\s+(class|struct)?\s*([A-Za-z_]\w*)\b")


def _scope_ranges(masked: str) -> list[tuple[int, int, str]]:
    scopes: list[tuple[int, int, str]] = []
    namespace_pattern = re.compile(r"\bnamespace\s+([A-Za-z_]\w*(?:::[A-Za-z_]\w*)*)?\s*\{")
    for match in namespace_pattern.finditer(masked):
        name = match.group(1) or ""
        if not name:
            continue
        open_brace = masked.find("{", match.start(), match.end())
        close_brace = find_matching_brace(masked, open_brace)
        if close_brace is not None:
            scopes.append((open_brace + 1, close_brace, name))

    for match in _type_declaration_pattern().finditer(masked):
        if _is_enum_class_keyword(masked, match.start()):
            continue
        marker = _declaration_marker(masked, match.end())
        if marker is None or masked[marker] != "{":
            continue
        close_brace = find_matching_brace(masked, marker)
        if close_brace is not None:
            scopes.append((marker + 1, close_brace, match.group(2)))

    scopes.sort(key=lambda item: (item[0], item[1]))
    return scopes


def _is_enum_class_keyword(masked: str, start: int) -> bool:
    prefix = masked[max(0, start - 12) : start]
    return bool(re.search(r"\benum\s+$", prefix))


def _make_declaration(
    *,
    text: str,
    masked: str,
    offsets: list[int],
    scopes: list[tuple[int, int, str]],
    path: Path,
    project_root: Path,
    include_roots: list[Path],
    name: str,
    kind: str,
    offset: int,
    name_offset: int,
) -> Declaration | None:
    marker = _declaration_marker(masked, offset)
    if marker is None:
        return None
    is_definition = masked[marker] == "{"
    if is_definition:
        close = find_matching_brace(masked, marker)
        if close is None:
            return None
        end = _consume_trailing_semicolon(masked, close + 1)
    else:
        end = marker + 1
    start = _extend_start_for_template_prefix(text, offset)
    snippet_end = marker + 1 if is_definition else end
    snippet = text[start:snippet_end].strip()
    line, column = offset_to_line_column(offsets, name_offset)
    qualified_name = _qualified_name(name, scopes, offset)
    return Declaration(
        name=name,
        qualified_name=qualified_name,
        kind=kind,
        path=str(path),
        line=line,
        column=column,
        include=_include_path(path, project_root, include_roots),
        is_definition=is_definition,
        snippet=snippet,
    )


def _line_declaration(
    *,
    text: str,
    offsets: list[int],
    scopes: list[tuple[int, int, str]],
    path: Path,
    project_root: Path,
    include_roots: list[Path],
    name: str,
    kind: str,
    offset: int,
    name_offset: int,
) -> Declaration:
    line_start = text.rfind("\n", 0, offset) + 1
    line_end = text.find("\n", offset)
    if line_end == -1:
        line_end = len(text)
    line, column = offset_to_line_column(offsets, name_offset)
    return Declaration(
        name=name,
        qualified_name=_qualified_name(name, scopes, offset),
        kind=kind,
        path=str(path),
        line=line,
        column=column,
        include=_include_path(path, project_root, include_roots),
        is_definition=True,
        snippet=text[line_start:line_end].strip(),
    )


def _qualified_name(name: str, scopes: list[tuple[int, int, str]], offset: int) -> str:
    containers = [scope_name for start, end, scope_name in scopes if start <= offset < end]
    return "::".join([*containers, name]) if containers else name


def _declaration_marker(masked: str, start: int) -> int | None:
    angle = paren = bracket = 0
    for index in range(start, len(masked)):
        ch = masked[index]
        if ch == "<":
            angle += 1
        elif ch == ">" and angle:
            angle -= 1
        elif ch == "(":
            paren += 1
        elif ch == ")" and paren:
            paren -= 1
        elif ch == "[":
            bracket += 1
        elif ch == "]" and bracket:
            bracket -= 1
        elif ch in {"{", ";"} and angle == 0 and paren == 0 and bracket == 0:
            return index
    return None


def find_matching_brace(masked: str, open_offset: int) -> int | None:
    if open_offset < 0:
        return None
    depth = 0
    for index in range(open_offset, len(masked)):
        if masked[index] == "{":
            depth += 1
        elif masked[index] == "}":
            depth -= 1
            if depth == 0:
                return index
    return None


def _consume_trailing_semicolon(masked: str, offset: int) -> int:
    index = offset
    while index < len(masked) and masked[index].isspace():
        index += 1
    if index < len(masked) and masked[index] == ";":
        return index + 1
    return offset


def _extend_start_for_template_prefix(text: str, offset: int) -> int:
    current = text.rfind("\n", 0, offset) + 1
    while current > 0:
        previous_end = current - 1
        previous_start = text.rfind("\n", 0, previous_end) + 1
        line = text[previous_start:previous_end].strip()
        if line.startswith("template") or line.startswith("[["):
            current = previous_start
            continue
        break
    return current


def _include_path(path: Path, project_root: Path, include_roots: list[Path]) -> str:
    candidates: list[str] = []
    for root in [*include_roots, project_root]:
        try:
            candidates.append(path.resolve().relative_to(root).as_posix())
        except ValueError:
            continue
    if candidates:
        return min(candidates, key=len)
    return path.name


def _match_score(declaration: Declaration, query: str) -> tuple[int, int, int, int, str, int] | None:
    query_lower = query.lower()
    leaf = query.rsplit("::", 1)[-1]
    leaf_lower = leaf.lower()
    qualified_lower = declaration.qualified_name.lower()
    name_lower = declaration.name.lower()

    if declaration.qualified_name == query:
        tier = 0
    elif declaration.name == leaf:
        tier = 1
    elif qualified_lower == query_lower:
        tier = 2
    elif name_lower == leaf_lower:
        tier = 3
    elif query_lower in qualified_lower:
        tier = 4
    elif leaf_lower in name_lower:
        tier = 5
    else:
        return None

    definition_penalty = 0 if declaration.is_definition else 1
    suffix_penalty = 0 if Path(declaration.path).suffix.lower() in HEADER_SUFFIXES else 1
    kind_penalty = 0 if declaration.kind in {"class", "struct", "union", "enum", "enum class"} else 1
    return (tier, definition_penalty, suffix_penalty, kind_penalty, declaration.path, declaration.line)
