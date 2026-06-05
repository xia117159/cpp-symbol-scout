from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .models import CLASSLIKE_KINDS, FUNCTIONLIKE_KINDS, Position, Range


@dataclass(frozen=True)
class SourceSnippet:
    source: str
    range: Range


def extract_source(
    path: Path,
    position: Position,
    *,
    symbol_name: str = "",
    kind: int | None = None,
    preferred_range: Range | None = None,
) -> SourceSnippet:
    text = path.read_text(encoding="utf-8", errors="replace")
    offsets = _line_offsets(text)

    if preferred_range is not None and _range_has_body_shape(text, offsets, preferred_range):
        return _slice_range(text, offsets, preferred_range)

    masked = _mask_comments_and_strings(text)
    offset = _position_to_offset(offsets, position)
    symbol_leaf = _leaf_name(symbol_name)

    if kind in CLASSLIKE_KINDS:
        snippet = _extract_classlike(text, masked, offsets, offset, symbol_leaf)
        if snippet is not None:
            return snippet

    if kind in FUNCTIONLIKE_KINDS or kind is None:
        snippet = _extract_functionlike(text, masked, offsets, offset)
        if snippet is not None:
            return snippet

    snippet = _extract_classlike(text, masked, offsets, offset, symbol_leaf)
    if snippet is not None:
        return snippet

    return _fallback_context(text, offsets, position)


def _range_has_body_shape(text: str, offsets: list[int], value: Range) -> bool:
    start = _position_to_offset(offsets, value.start)
    end = _position_to_offset(offsets, value.end)
    if end <= start:
        return False
    snippet = text[start:end]
    if "\n" not in snippet:
        return False
    return "{" in snippet or ";" in snippet


def _slice_range(text: str, offsets: list[int], value: Range) -> SourceSnippet:
    start = _position_to_offset(offsets, value.start)
    end = _position_to_offset(offsets, value.end)
    source = text[start:end]
    return SourceSnippet(source=source, range=value)


def _line_offsets(text: str) -> list[int]:
    offsets = [0]
    for match in re.finditer(r"\n", text):
        offsets.append(match.end())
    return offsets


def _position_to_offset(offsets: list[int], position: Position) -> int:
    if not offsets:
        return 0
    line = max(0, min(position.line, len(offsets) - 1))
    line_start = offsets[line]
    line_end = offsets[line + 1] if line + 1 < len(offsets) else None
    absolute = line_start + max(0, position.character)
    if line_end is None:
        return absolute
    return min(absolute, line_end)


def _offset_to_position(offsets: list[int], offset: int) -> Position:
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


def _leaf_name(symbol_name: str) -> str:
    name = symbol_name.split("(")[0].strip()
    if "::" in name:
        name = name.rsplit("::", 1)[1]
    return name.strip()


def _mask_comments_and_strings(text: str) -> str:
    chars = list(text)
    i = 0
    n = len(chars)
    while i < n:
        ch = chars[i]
        nxt = chars[i + 1] if i + 1 < n else ""

        if ch == "/" and nxt == "/":
            chars[i] = chars[i + 1] = " "
            i += 2
            while i < n and chars[i] != "\n":
                chars[i] = " "
                i += 1
            continue

        if ch == "/" and nxt == "*":
            chars[i] = chars[i + 1] = " "
            i += 2
            while i + 1 < n:
                if chars[i] == "*" and chars[i + 1] == "/":
                    chars[i] = chars[i + 1] = " "
                    i += 2
                    break
                if chars[i] != "\n":
                    chars[i] = " "
                i += 1
            continue

        if ch in {'"', "'"}:
            quote = ch
            chars[i] = " "
            i += 1
            escaped = False
            while i < n:
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


def _extract_classlike(
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
    body_or_end = _find_next_top_level(masked, window_start + match.end(), {"{", ";"})
    if body_or_end is None:
        return None

    if masked[body_or_end] == ";":
        end = body_or_end + 1
    else:
        close = _find_matching(masked, body_or_end, "{", "}")
        if close is None:
            return None
        end = _consume_trailing_semicolon(masked, close + 1)

    start = _extend_start_for_prefix_lines(text, start)
    return _snippet_from_offsets(text, offsets, start, end)


def _extract_functionlike(
    text: str,
    masked: str,
    offsets: list[int],
    offset: int,
) -> SourceSnippet | None:
    start = _logical_start(masked, offset)
    end_marker = _find_function_end_marker(masked, offset)
    if end_marker is None:
        return None

    if masked[end_marker] == "{":
        close = _find_matching(masked, end_marker, "{", "}")
        if close is None:
            return None
        end = close + 1
        end = _consume_optional_function_suffix(masked, end)
    else:
        end = end_marker + 1

    start = _trim_leading_noise(text, start)
    start = _extend_start_for_prefix_lines(text, start)
    if end <= start:
        return None
    return _snippet_from_offsets(text, offsets, start, end)


def _find_next_top_level(masked: str, start: int, targets: set[str]) -> int | None:
    paren = 0
    bracket = 0
    angle = 0
    for i in range(start, len(masked)):
        ch = masked[i]
        if ch == "(":
            paren += 1
        elif ch == ")":
            paren = max(0, paren - 1)
        elif ch == "[":
            bracket += 1
        elif ch == "]":
            bracket = max(0, bracket - 1)
        elif ch == "<" and paren == 0 and bracket == 0:
            angle += 1
        elif ch == ">" and angle:
            angle -= 1
        elif ch in targets and paren == 0 and bracket == 0 and angle == 0:
            return i
    return None


def _find_function_end_marker(masked: str, offset: int) -> int | None:
    paren = 0
    bracket = 0
    for i in range(offset, len(masked)):
        ch = masked[i]
        if ch == "(":
            paren += 1
        elif ch == ")":
            paren = max(0, paren - 1)
        elif ch == "[":
            bracket += 1
        elif ch == "]":
            bracket = max(0, bracket - 1)
        elif ch in {"{", ";"} and paren == 0 and bracket == 0:
            return i
    return None


def _find_matching(masked: str, open_offset: int, open_char: str, close_char: str) -> int | None:
    depth = 0
    for i in range(open_offset, len(masked)):
        ch = masked[i]
        if ch == open_char:
            depth += 1
        elif ch == close_char:
            depth -= 1
            if depth == 0:
                return i
    return None


def _logical_start(masked: str, offset: int) -> int:
    brace = paren = bracket = 0
    context_depth = _brace_depth_at(masked, offset)
    last = 0
    i = 0
    while i < min(offset, len(masked)):
        ch = masked[i]
        if ch == "{":
            brace += 1
        elif ch == "}":
            brace = max(0, brace - 1)
            if brace == context_depth and paren == 0 and bracket == 0:
                last = i + 1
        elif ch == "(":
            paren += 1
        elif ch == ")":
            paren = max(0, paren - 1)
        elif ch == "[":
            bracket += 1
        elif ch == "]":
            bracket = max(0, bracket - 1)
        elif ch == ";" and brace == context_depth and paren == 0 and bracket == 0:
            last = i + 1
        i += 1
    access_label = None
    for match in re.finditer(r"(?m)^\s*(?:public|protected|private)\s*:\s*", masked[last:offset]):
        access_label = match
    if access_label is not None:
        last += access_label.end()
    return last


def _brace_depth_at(masked: str, offset: int) -> int:
    depth = 0
    for ch in masked[: max(0, min(offset, len(masked)))]:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth = max(0, depth - 1)
    return depth


def _trim_leading_noise(text: str, start: int) -> int:
    while start < len(text) and text[start].isspace():
        start += 1

    line_start = text.rfind("\n", 0, start) + 1
    access_label = re.compile(r"\s*(public|protected|private)\s*:\s*")
    match = access_label.match(text, line_start, start + 32)
    if match:
        return match.end()
    return line_start if line_start <= start else start


def _extend_start_for_prefix_lines(text: str, start: int) -> int:
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


def _consume_trailing_semicolon(masked: str, offset: int) -> int:
    i = offset
    while i < len(masked) and masked[i].isspace():
        i += 1
    if i < len(masked) and masked[i] == ";":
        return i + 1
    return offset


def _consume_optional_function_suffix(masked: str, offset: int) -> int:
    i = offset
    while i < len(masked) and masked[i].isspace():
        i += 1
    if i < len(masked) and masked[i] == ";":
        return i + 1
    return offset


def _snippet_from_offsets(text: str, offsets: list[int], start: int, end: int) -> SourceSnippet:
    start = max(0, min(start, len(text)))
    end = max(start, min(end, len(text)))
    return SourceSnippet(
        source=text[start:end],
        range=Range(start=_offset_to_position(offsets, start), end=_offset_to_position(offsets, end)),
    )


def _fallback_context(text: str, offsets: list[int], position: Position) -> SourceSnippet:
    start_line = max(0, position.line - 5)
    end_line = min(len(offsets), position.line + 6)
    start = offsets[start_line]
    end = offsets[end_line] if end_line < len(offsets) else len(text)
    return _snippet_from_offsets(text, offsets, start, end)
