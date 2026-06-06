from __future__ import annotations

import re
import posixpath
from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    NOTE = "note"
    INFO = "info"


@dataclass(frozen=True)
class FilterOptions:
    keep_warnings: bool | None = None
    warning_files: str | Iterable[str] = ()
    max_warnings: int = 10
    max_notes_per_diagnostic: int = 8
    max_context_lines_per_diagnostic: int = 12
    keep_make_failures: bool = True
    keep_linker_errors: bool = True
    dedupe: bool = True
    include_summary: bool = False


@dataclass(frozen=True)
class Diagnostic:
    severity: Severity
    lines: tuple[str, ...]
    primary: str


@dataclass(frozen=True)
class FilterStats:
    input_lines: int
    output_lines: int
    dropped_lines: int
    errors: int
    warnings: int
    notes: int
    progress_lines: int
    command_lines: int


@dataclass(frozen=True)
class FilterResult:
    text: str
    diagnostics: tuple[Diagnostic, ...]
    stats: FilterStats


@dataclass
class _MutableStats:
    input_lines: int = 0
    progress_lines: int = 0
    command_lines: int = 0


ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
GCC_CLANG_DIAGNOSTIC_RE = re.compile(
    r"^(?P<path>[^:\n]+):(?P<line>\d+)(?::(?P<column>\d+))?:\s+"
    r"(?P<severity>fatal error|error|warning|note):\s+.+"
)
MSVC_DIAGNOSTIC_RE = re.compile(
    r"^(?P<path>.+?)\((?P<line>\d+)(?:,(?P<column>\d+))?\):\s+"
    r"(?P<severity>fatal error|error|warning|note)\s+[A-Z]+\d*:\s+.+",
    re.IGNORECASE,
)
CMAKE_DIAGNOSTIC_RE = re.compile(r"^CMake\s+(?P<severity>Error|Warning)(?:\s+at|\s+\(.*\)|:|$)")
MAKE_FAILURE_RE = re.compile(r"^(?:g?make(?:\[\d+\])?:\s+)?(?:\*\*\*|Stop\.|.*Error\s+\d+\b)")
LINKER_ERROR_RE = re.compile(
    r"^(?:/[^:\n]*/)?(?:ld|collect2|lld|gold)(?:\b|:)|"
    r"(?:undefined reference to|multiple definition of|cannot find -l|ld returned \d+ exit status)"
)
FAILED_RE = re.compile(r"^(FAILED:|ninja: build stopped:|Build FAILED|Error: )")
INCLUDED_FROM_RE = re.compile(r"^(In file included from|                 from)\s+")
TEMPLATE_CONTEXT_RE = re.compile(r"^\s*(?:required from|instantiated from|in instantiation of|note: in instantiation)")
CMAKE_STACK_RE = re.compile(r"^(?:Call Stack \(most recent call first\):|  .+CMakeLists\.txt:\d+ \(.+\))")
COMPILER_CONTEXT_RE = re.compile(r"^[^:\n]+:\s+(?:In function|In member function|At global scope|In constructor)")

PROGRESS_PATTERNS = (
    re.compile(r"^\[\s*\d+%\]\s+(?:Building|Linking|Generating|Scanning|Built|Installing|Consolidate)\b"),
    re.compile(r"^\[\d+/\d+\]\s+"),
    re.compile(r"^(?:Scanning dependencies of target|Consolidate compiler generated dependencies of target)\b"),
    re.compile(r"^(?:Building CXX object|Building C object|Linking CXX executable|Built target)\b"),
    re.compile(r"^(?:g?make)(?:\[\d+\])?: (?:Entering|Leaving) directory\b"),
    re.compile(r"^-- (?:Configuring done|Generating done|Build files have been written to:|Detecting|Check for working|The CXX compiler identification is)\b"),
)
COMMAND_RE = re.compile(
    r"^(?:cd\s+.+\s+&&\s+)?(?:/[\w./+-]+/)?"
    r"(?:c\+\+|g\+\+|gcc|clang\+\+|clang|cc|ar|ranlib|ld|cmake|make|gmake|ninja)(?=\s|$)"
)


def filter_build_log(text: str, options: FilterOptions | None = None) -> str:
    return filter_build_log_result(text, options).text


def filter_build_log_result(text: str, options: FilterOptions | None = None) -> FilterResult:
    options = options or FilterOptions()
    lines = _normalize_lines(text)
    stats = _MutableStats(input_lines=len(lines))
    diagnostics = _collect_diagnostics(lines, stats, options)
    selected = _select_diagnostics(diagnostics, options)
    output_lines = _diagnostic_lines(selected, options)
    if options.include_summary:
        output_lines = _summary_lines(diagnostics, selected, stats, len(output_lines)) + output_lines
    if options.dedupe:
        output_lines = _dedupe_lines(output_lines)
    output_text = "\n".join(output_lines).rstrip()
    output_count = len(output_text.splitlines()) if output_text else 0
    result_stats = FilterStats(
        input_lines=len(lines),
        output_lines=output_count,
        dropped_lines=max(0, len(lines) - output_count),
        errors=sum(1 for item in diagnostics if item.severity == Severity.ERROR),
        warnings=sum(1 for item in diagnostics if item.severity == Severity.WARNING),
        notes=sum(1 for item in diagnostics if item.severity == Severity.NOTE),
        progress_lines=stats.progress_lines,
        command_lines=stats.command_lines,
    )
    return FilterResult(text=output_text, diagnostics=tuple(selected), stats=result_stats)


def _normalize_lines(text: str) -> list[str]:
    normalized = ANSI_RE.sub("", text.replace("\r\n", "\n").replace("\r", "\n"))
    return normalized.splitlines()


def _collect_diagnostics(
    lines: list[str],
    stats: _MutableStats,
    options: FilterOptions,
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    index = 0
    while index < len(lines):
        line = lines[index].rstrip()
        severity = _diagnostic_severity(line)
        if severity is not None:
            start_index = index
            block, index = _consume_diagnostic_block(lines, index, options)
            if start_index > 0:
                previous = lines[start_index - 1].rstrip()
                if COMPILER_CONTEXT_RE.match(previous):
                    block.insert(0, previous)
            diagnostics.append(Diagnostic(severity=severity, lines=tuple(block), primary=line))
            continue
        if options.keep_linker_errors and _is_linker_error(line):
            block, index = _consume_linker_block(lines, index, options)
            diagnostics.append(Diagnostic(severity=Severity.ERROR, lines=tuple(block), primary=block[0]))
            continue
        if _is_failed_line(line) or (options.keep_make_failures and _is_make_failure(line)):
            diagnostics.append(Diagnostic(severity=Severity.ERROR, lines=(line,), primary=line))
            index += 1
            continue
        if _is_progress_line(line):
            stats.progress_lines += 1
        elif _is_command_line(line):
            stats.command_lines += 1
        index += 1
    return diagnostics


def _consume_diagnostic_block(
    lines: list[str],
    start: int,
    options: FilterOptions,
) -> tuple[list[str], int]:
    block = [lines[start].rstrip()]
    index = start + 1
    context_count = 0
    note_count = 0
    while index < len(lines):
        line = lines[index].rstrip()
        severity = _diagnostic_severity(line)
        if severity in {Severity.ERROR, Severity.WARNING}:
            break
        if severity == Severity.NOTE:
            if note_count >= options.max_notes_per_diagnostic:
                index += 1
                continue
            note_count += 1
            block.append(line)
            index += 1
            continue
        if _is_continuation_line(line):
            if context_count < options.max_context_lines_per_diagnostic:
                block.append(line)
                context_count += 1
            index += 1
            continue
        if not line:
            if block and block[-1]:
                block.append(line)
            index += 1
            continue
        if _is_progress_line(line) or _is_command_line(line):
            break
        if INCLUDED_FROM_RE.match(line) or TEMPLATE_CONTEXT_RE.match(line) or CMAKE_STACK_RE.match(line):
            if context_count < options.max_context_lines_per_diagnostic:
                block.append(line)
                context_count += 1
            index += 1
            continue
        break
    return block, index


def _consume_linker_block(
    lines: list[str],
    start: int,
    options: FilterOptions,
) -> tuple[list[str], int]:
    block = [lines[start].rstrip()]
    index = start + 1
    context_count = 0
    while index < len(lines):
        line = lines[index].rstrip()
        if _diagnostic_severity(line) is not None:
            break
        if _is_progress_line(line) or _is_command_line(line):
            break
        if not line:
            index += 1
            continue
        if context_count >= options.max_context_lines_per_diagnostic:
            index += 1
            continue
        block.append(line)
        context_count += 1
        index += 1
    return block, index


def _select_diagnostics(diagnostics: list[Diagnostic], options: FilterOptions) -> list[Diagnostic]:
    warnings = [item for item in diagnostics if item.severity == Severity.WARNING]
    selected_warning_ids: set[int] = set()
    if _should_keep_warnings(options):
        selected_warning_ids = {id(item) for item in _select_warnings(warnings, options)}
    return [
        item for item in diagnostics
        if item.severity in {Severity.ERROR, Severity.NOTE}
        or (item.severity == Severity.WARNING and id(item) in selected_warning_ids)
    ]


def _should_keep_warnings(options: FilterOptions) -> bool:
    if options.keep_warnings is not None:
        return options.keep_warnings
    return bool(_normalize_warning_files(options.warning_files))


def _select_warnings(warnings: list[Diagnostic], options: FilterOptions) -> list[Diagnostic]:
    matched = [
        item for item in warnings
        if _warning_matches_files(item, options.warning_files)
    ]
    return matched[: max(0, options.max_warnings)]


def _warning_matches_files(diagnostic: Diagnostic, warning_files: str | Iterable[str]) -> bool:
    patterns = _normalize_warning_files(warning_files)
    if not patterns:
        return True
    path = _diagnostic_path(diagnostic)
    if path is None:
        return False
    normalized_path = _normalize_path(path)
    basename = normalized_path.rsplit("/", 1)[-1]
    for pattern in patterns:
        normalized_pattern = _normalize_path(pattern)
        if not normalized_pattern:
            continue
        if "/" not in normalized_pattern and basename == normalized_pattern:
            return True
        if normalized_path == normalized_pattern or normalized_path.endswith(f"/{normalized_pattern}"):
            return True
    return False


def _normalize_warning_files(warning_files: str | Iterable[str]) -> tuple[str, ...]:
    if isinstance(warning_files, str):
        return (warning_files,)
    return tuple(warning_files)


def _diagnostic_path(diagnostic: Diagnostic) -> str | None:
    match = GCC_CLANG_DIAGNOSTIC_RE.match(diagnostic.primary) or MSVC_DIAGNOSTIC_RE.match(diagnostic.primary)
    if not match:
        return None
    return match.group("path")


def _normalize_path(value: str) -> str:
    normalized = value.strip().replace("\\", "/")
    return posixpath.normpath(normalized) if normalized else ""


def _diagnostic_lines(diagnostics: Iterable[Diagnostic], options: FilterOptions) -> list[str]:
    output: list[str] = []
    for diagnostic in diagnostics:
        if output and output[-1] != "":
            output.append("")
        output.extend(_limit_block_lines(diagnostic.lines, options))
    return output


def _limit_block_lines(lines: tuple[str, ...], options: FilterOptions) -> list[str]:
    if not lines:
        return []
    result: list[str] = []
    context_count = 0
    note_count = 0
    for index, line in enumerate(lines):
        severity = _diagnostic_severity(line)
        if index == 0 or severity in {Severity.ERROR, Severity.WARNING}:
            result.append(line)
            continue
        if severity == Severity.NOTE:
            if note_count < options.max_notes_per_diagnostic:
                result.append(line)
                note_count += 1
            continue
        if not line:
            if result and result[-1]:
                result.append(line)
            continue
        if context_count < options.max_context_lines_per_diagnostic:
            result.append(line)
            context_count += 1
    while result and not result[-1]:
        result.pop()
    return result


def _summary_lines(
    diagnostics: list[Diagnostic],
    selected: list[Diagnostic],
    stats: _MutableStats,
    output_line_count: int,
) -> list[str]:
    errors = sum(1 for item in diagnostics if item.severity == Severity.ERROR)
    warnings = sum(1 for item in diagnostics if item.severity == Severity.WARNING)
    hidden = max(0, len(diagnostics) - len(selected))
    return [
        f"Build log filter: kept {output_line_count} lines from {stats.input_lines}; "
        f"errors={errors}, warnings={warnings}, hidden_diagnostics={hidden}.",
        "",
    ]


def _dedupe_lines(lines: list[str]) -> list[str]:
    seen_blocks: set[tuple[str, ...]] = set()
    result: list[str] = []
    block: list[str] = []
    for line in lines + [""]:
        if line:
            block.append(line)
            continue
        if block:
            key = tuple(block)
            if key not in seen_blocks:
                if result and result[-1] != "":
                    result.append("")
                result.extend(block)
                seen_blocks.add(key)
            block = []
        elif result and result[-1] != "":
            result.append("")
    while result and not result[-1]:
        result.pop()
    return result


def _diagnostic_severity(line: str) -> Severity | None:
    match = GCC_CLANG_DIAGNOSTIC_RE.match(line) or MSVC_DIAGNOSTIC_RE.match(line)
    if match:
        return _severity_from_text(match.group("severity"))
    match = CMAKE_DIAGNOSTIC_RE.match(line)
    if match:
        return Severity.ERROR if match.group("severity") == "Error" else Severity.WARNING
    return None


def _severity_from_text(value: str) -> Severity:
    normalized = value.lower()
    if "error" in normalized:
        return Severity.ERROR
    if "warning" in normalized:
        return Severity.WARNING
    if "note" in normalized:
        return Severity.NOTE
    return Severity.INFO


def _is_continuation_line(line: str) -> bool:
    if not line:
        return True
    if INCLUDED_FROM_RE.match(line) or TEMPLATE_CONTEXT_RE.match(line) or CMAKE_STACK_RE.match(line):
        return True
    stripped = line.lstrip()
    return (
        line.startswith((" ", "\t"))
        or stripped.startswith(("^", "~", "|", "`", ">", "required from", "instantiated from"))
        or bool(re.match(r"^\s*\d+\s*\|\s+", line))
    )


def _is_linker_error(line: str) -> bool:
    return bool(LINKER_ERROR_RE.search(line))


def _is_failed_line(line: str) -> bool:
    return bool(FAILED_RE.match(line))


def _is_make_failure(line: str) -> bool:
    return bool(MAKE_FAILURE_RE.match(line))


def _is_progress_line(line: str) -> bool:
    return any(pattern.match(line) for pattern in PROGRESS_PATTERNS)


def _is_command_line(line: str) -> bool:
    if len(line) < 12:
        return False
    return bool(COMMAND_RE.match(line))
