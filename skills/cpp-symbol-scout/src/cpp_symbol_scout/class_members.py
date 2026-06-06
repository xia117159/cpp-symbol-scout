from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import CLASSLIKE_KINDS, SYMBOL_KINDS, Position, Range
from .snippets import (
    _find_matching,
    _line_offsets,
    _mask_comments_and_strings,
    _offset_to_position,
)


ACCESS_VALUES = {"public", "protected", "private"}
MEMBER_KIND_VALUES = {"method", "field", "type"}


@dataclass(frozen=True)
class ClassMember:
    name: str
    kind: str
    access: str
    declaration: str
    path: Path
    range: Range

    def to_dict(self, project_root: Path) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "access": self.access,
            "declaration": self.declaration,
            "location": {
                "path": str(self.path),
                "relative_path": relative_path(self.path, project_root),
                "line": self.range.start.line + 1,
                "column": self.range.start.character + 1,
                "range": self.range.to_lsp(),
            },
        }


def members_payload_from_symbol_result(
    result: dict[str, Any],
    *,
    project_root: str | Path,
    access: str = "all",
    member_kind: str = "all",
    limit: int = 200,
) -> dict[str, Any]:
    root = Path(project_root).expanduser().resolve()
    source = str(result.get("source") or "")
    if not source:
        raise ValueError("selected symbol result has no source")
    location = result.get("location") if isinstance(result.get("location"), dict) else {}
    path = Path(str(location.get("path") or "")).expanduser()
    if not path.is_absolute():
        path = (root / path).resolve()
    source_range = _range_from_payload(result.get("source_range")) or _range_from_payload(location.get("range"))
    if source_range is None:
        source_range = Range(Position(0, 0), Position(0, 0))

    members = extract_class_members(
        source,
        path=path,
        source_range=source_range,
        symbol_name=str(result.get("full_name") or result.get("name") or ""),
        symbol_kind=int(result.get("kind") or 0),
    )
    filtered = filter_members(members, access=access, member_kind=member_kind)
    returned = filtered[:limit]
    return {
        "query": result.get("full_name") or result.get("name"),
        "class": {
            "name": result.get("name"),
            "full_name": result.get("full_name"),
            "kind": result.get("kind"),
            "kind_name": result.get("kind_name") or SYMBOL_KINDS.get(int(result.get("kind") or 0), "Unknown"),
            "location": {
                **location,
                "relative_path": location.get("relative_path")
                or relative_path(Path(str(location.get("path") or path)), root),
            },
            "source_range": source_range.to_lsp(),
        },
        "summary": {
            "member_count": len(members),
            "returned_count": len(returned),
            "access_filter": access,
            "kind_filter": member_kind,
            "methods": sum(1 for item in members if item.kind == "method"),
            "fields": sum(1 for item in members if item.kind == "field"),
            "types": sum(1 for item in members if item.kind == "type"),
            "truncated": len(filtered) > len(returned),
        },
        "members": [member.to_dict(root) for member in returned],
    }


def select_class_symbol_result(results: list[dict[str, Any]]) -> dict[str, Any] | None:
    for result in results:
        if int(result.get("kind") or 0) in CLASSLIKE_KINDS and _source_has_class_body(str(result.get("source") or "")):
            return result
    for result in results:
        if _source_has_class_body(str(result.get("source") or "")):
            return result
    return None


def filter_members(members: list[ClassMember], *, access: str, member_kind: str) -> list[ClassMember]:
    if access != "all" and access not in ACCESS_VALUES:
        raise ValueError(f"invalid access filter: {access}")
    if member_kind != "all" and member_kind not in MEMBER_KIND_VALUES:
        raise ValueError(f"invalid member kind filter: {member_kind}")
    result = members
    if access != "all":
        result = [member for member in result if member.access == access]
    if member_kind != "all":
        result = [member for member in result if member.kind == member_kind]
    return result


def extract_class_members(
    source: str,
    *,
    path: Path,
    source_range: Range,
    symbol_name: str = "",
    symbol_kind: int = 0,
) -> list[ClassMember]:
    masked = _mask_comments_and_strings(source)
    offsets = _line_offsets(source)
    class_header = _class_header(masked, symbol_name=symbol_name)
    if class_header is None:
        return []
    tag, class_name, _header_start, body_start = class_header
    body_end = _find_matching(masked, body_start, "{", "}")
    if body_end is None:
        return []

    default_access = "public" if tag in {"struct", "union"} else "private"
    current_access = default_access
    index = body_start + 1
    members: list[ClassMember] = []

    while index < body_end:
        index = _skip_whitespace(masked, index, body_end)
        if index >= body_end:
            break

        label = _access_label_at(masked, index)
        if label is not None:
            current_access, index = label
            continue

        item_end = _next_member_end(masked, index, body_end)
        if item_end is None or item_end <= index:
            break
        member = _classify_member(
            source[index:item_end],
            masked[index:item_end],
            start_offset=index,
            access=current_access,
            class_name=class_name,
            path=path,
            source_start=source_range.start,
            offsets=offsets,
        )
        if member is not None:
            members.append(member)
        index = item_end

    return members


def _class_header(masked: str, *, symbol_name: str) -> tuple[str, str, int, int] | None:
    leaf = symbol_name.split("::")[-1].split("(")[0].strip()
    if leaf:
        name = re.escape(leaf)
        pattern = re.compile(rf"\b(class|struct|union)\s+(?:class\s+|struct\s+)?(?P<name>{name})\b")
    else:
        pattern = re.compile(r"\b(class|struct|union)\s+(?:class\s+|struct\s+)?(?P<name>[A-Za-z_]\w*)\b")
    for match in pattern.finditer(masked):
        body_start = _find_next_top_level(masked, match.end(), "{")
        if body_start is not None:
            return match.group(1), match.group("name"), match.start(), body_start
    return None


def _source_has_class_body(source: str) -> bool:
    masked = _mask_comments_and_strings(source)
    return _class_header(masked, symbol_name="") is not None


def _skip_whitespace(text: str, index: int, end: int) -> int:
    while index < end and text[index].isspace():
        index += 1
    return index


def _access_label_at(masked: str, index: int) -> tuple[str, int] | None:
    match = re.match(r"(public|protected|private)\s*:\s*", masked[index:])
    if not match:
        return None
    return match.group(1), index + match.end()


def _next_member_end(masked: str, start: int, end: int) -> int | None:
    paren = 0
    bracket = 0
    angle = 0
    index = start
    while index < end:
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
        elif char == "{" and paren == 0 and bracket == 0 and angle == 0:
            close = _find_matching(masked, index, "{", "}")
            if close is None:
                return None
            after = _skip_whitespace(masked, close + 1, end)
            if after < end and masked[after] == ";":
                return after + 1
            return close + 1
        elif char == ";" and paren == 0 and bracket == 0 and angle == 0:
            return index + 1
        index += 1
    return None


def _classify_member(
    source: str,
    masked: str,
    *,
    start_offset: int,
    access: str,
    class_name: str,
    path: Path,
    source_start: Position,
    offsets: list[int],
) -> ClassMember | None:
    stripped = source.strip()
    if not stripped:
        return None
    if stripped.startswith("#"):
        return None
    if _looks_like_macro_statement(stripped):
        return None
    compact = _compact_declaration(stripped)
    if compact in {"public:", "protected:", "private:"}:
        return None

    kind = _member_kind(compact, masked)
    if kind is None:
        return None
    if kind == "method":
        name = _method_name(compact, class_name=class_name)
        declaration = _method_declaration_without_body(source, masked)
    elif kind == "field":
        name = _field_name(compact)
        declaration = compact
    else:
        name = _type_name(compact)
        declaration = compact
    if not name:
        return None

    relative_position = _offset_to_position(offsets, start_offset + _leading_space_length(source))
    return ClassMember(
        name=name,
        kind=kind,
        access=access,
        declaration=declaration,
        path=path,
        range=Range(
            start=_absolute_position(source_start, relative_position),
            end=_absolute_position(source_start, _offset_to_position(offsets, start_offset + len(source))),
        ),
    )


def _member_kind(declaration: str, masked: str) -> str | None:
    if re.match(r"^(class|struct|union|enum)\b", declaration):
        return "type"
    if re.match(r"^(using|typedef)\b", declaration):
        return "type"
    if re.match(r"^(static_assert|friend)\b", declaration):
        return None
    if _is_function_pointer_field(declaration):
        return "field"
    if _first_top_level_paren(masked) is not None:
        return "method"
    if declaration.endswith(";"):
        return "field"
    return None


def _looks_like_macro_statement(declaration: str) -> bool:
    first_line = declaration.splitlines()[0].strip()
    return re.match(r"^[A-Z_][A-Z0-9_]*\s*(?:\(|;)", first_line) is not None


def _is_function_pointer_field(declaration: str) -> bool:
    return re.search(r"\(\s*[*&]\s*[A-Za-z_]\w*\s*\)", declaration) is not None


def _method_name(declaration: str, *, class_name: str) -> str:
    paren = _first_top_level_paren(declaration)
    if paren is None:
        return ""
    prefix = declaration[:paren].rstrip()
    operator_index = prefix.rfind("operator")
    if operator_index >= 0:
        return prefix[operator_index:].strip()
    match = re.search(r"(~?[A-Za-z_]\w*)\s*$", prefix)
    return match.group(1) if match else ""


def _field_name(declaration: str) -> str:
    head = declaration.rsplit(";", 1)[0]
    head = head.split("=", 1)[0]
    head = head.split(":", 1)[0]
    head = head.rsplit(",", 1)[-1]
    identifiers = re.findall(r"\b[A-Za-z_]\w*\b", head)
    keywords = {
        "alignas",
        "const",
        "constexpr",
        "inline",
        "mutable",
        "static",
        "thread_local",
        "volatile",
    }
    for name in reversed(identifiers):
        if name not in keywords:
            return name
    return ""


def _type_name(declaration: str) -> str:
    match = re.match(r"(?:class|struct|union|enum)(?:\s+class|\s+struct)?\s+([A-Za-z_]\w*)", declaration)
    if match:
        return match.group(1)
    match = re.match(r"using\s+([A-Za-z_]\w*)\b", declaration)
    if match:
        return match.group(1)
    match = re.match(r"typedef\b.*\b([A-Za-z_]\w*)\s*;", declaration)
    return match.group(1) if match else ""


def _method_declaration_without_body(source: str, masked: str) -> str:
    body_open = _top_level_body_open(masked)
    if body_open is None:
        return _compact_declaration(source.strip())
    prefix = source[:body_open].rstrip()
    masked_prefix = masked[:body_open]
    initializer_colon = _constructor_initializer_colon(masked_prefix)
    if initializer_colon is not None:
        prefix = prefix[:initializer_colon].rstrip()
    return _compact_declaration(prefix) + ";"


def _top_level_body_open(masked: str) -> int | None:
    paren = 0
    bracket = 0
    angle = 0
    for index, char in enumerate(masked):
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
        elif char == "{" and paren == 0 and bracket == 0 and angle == 0:
            return index
        elif char == ";" and paren == 0 and bracket == 0 and angle == 0:
            return None
    return None


def _constructor_initializer_colon(masked_prefix: str) -> int | None:
    open_paren = _first_top_level_paren(masked_prefix)
    if open_paren is None:
        return None
    close = _find_matching(masked_prefix, open_paren, "(", ")")
    if close is None:
        return None
    tail = masked_prefix[close + 1 :]
    if "->" in tail:
        return None
    colon = tail.find(":")
    return close + 1 + colon if colon >= 0 else None


def _first_top_level_paren(text: str) -> int | None:
    angle = 0
    bracket = 0
    for index, char in enumerate(text):
        if char == "[":
            bracket += 1
        elif char == "]":
            bracket = max(0, bracket - 1)
        elif char == "<" and bracket == 0:
            angle += 1
        elif char == ">" and angle:
            angle -= 1
        elif char == "(" and angle == 0 and bracket == 0:
            return index
    return None


def _find_next_top_level(masked: str, start: int, target: str) -> int | None:
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
        elif char == target and paren == 0 and bracket == 0 and angle == 0:
            return index
    return None


def _compact_declaration(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def _leading_space_length(value: str) -> int:
    return len(value) - len(value.lstrip())


def _absolute_position(base: Position, relative: Position) -> Position:
    if relative.line == 0:
        return Position(base.line, base.character + relative.character)
    return Position(base.line + relative.line, relative.character)


def _range_from_payload(value: Any) -> Range | None:
    if not isinstance(value, dict):
        return None
    try:
        return Range.from_lsp(value)
    except Exception:
        return None


def relative_path(path: Path, project_root: Path) -> str | None:
    try:
        return path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return None
