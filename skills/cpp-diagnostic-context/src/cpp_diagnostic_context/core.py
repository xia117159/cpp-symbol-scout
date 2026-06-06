from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


DIAGNOSTIC_RE = re.compile(
    r"^(?P<path>[^:\n][^:\n]*?):(?P<line>\d+):(?:(?P<column>\d+):)?\s*"
    r"(?P<severity>fatal error|error|warning|note):\s*(?P<message>.*)$"
)
INCLUDED_FROM_RE = re.compile(
    r"^(?:In file included from|                 from)\s+(?P<path>[^:]+):(?P<line>\d+)(?::(?P<column>\d+))?[,:]"
)
REQUIRED_FROM_RE = re.compile(r"^\s*(?:required from|instantiated from)\s+(?P<message>.*)$")


@dataclass(frozen=True)
class SourceLocation:
    path: str
    line: int
    column: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "line": self.line, "column": self.column}


@dataclass
class Diagnostic:
    location: SourceLocation
    severity: str
    message: str
    include_stack: list[SourceLocation] = field(default_factory=list)
    template_stack: list[str] = field(default_factory=list)
    notes: list[dict[str, Any]] = field(default_factory=list)
    snippet: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "location": self.location.to_dict(),
            "severity": self.severity,
            "message": self.message,
            "include_stack": [item.to_dict() for item in self.include_stack],
            "template_stack": self.template_stack,
            "notes": self.notes,
            "snippet": self.snippet,
        }


@dataclass(frozen=True)
class DiagnosticReport:
    diagnostics: list[Diagnostic]
    total_errors: int
    total_warnings: int
    total_notes: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": {
                "diagnostics": len(self.diagnostics),
                "errors": self.total_errors,
                "warnings": self.total_warnings,
                "notes": self.total_notes,
            },
            "diagnostics": [diagnostic.to_dict() for diagnostic in self.diagnostics],
        }


def analyze_log(text: str, *, project_root: str | Path = ".", context_lines: int = 2, limit: int = 50) -> DiagnosticReport:
    root = Path(project_root).expanduser().resolve()
    diagnostics: list[Diagnostic] = []
    include_stack: list[SourceLocation] = []
    template_stack: list[str] = []
    pending_notes: list[dict[str, Any]] = []
    last_primary: Diagnostic | None = None
    total_errors = 0
    total_warnings = 0
    total_notes = 0

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        include_match = INCLUDED_FROM_RE.match(line)
        if include_match:
            include_stack.append(
                SourceLocation(
                    path=normalize_path(include_match.group("path"), root),
                    line=int(include_match.group("line")),
                    column=int(include_match.group("column")) if include_match.group("column") else None,
                )
            )
            continue

        required_match = REQUIRED_FROM_RE.match(line)
        if required_match:
            template_stack.append(required_match.group("message").strip())
            continue

        diagnostic_match = DIAGNOSTIC_RE.match(line)
        if not diagnostic_match:
            continue

        severity = diagnostic_match.group("severity")
        location = SourceLocation(
            path=normalize_path(diagnostic_match.group("path"), root),
            line=int(diagnostic_match.group("line")),
            column=int(diagnostic_match.group("column")) if diagnostic_match.group("column") else None,
        )
        message = diagnostic_match.group("message").strip()

        if severity == "note":
            total_notes += 1
            note = {"location": location.to_dict(), "message": message}
            if last_primary is not None:
                last_primary.notes.append(note)
            else:
                pending_notes.append(note)
            continue

        if severity == "warning":
            total_warnings += 1
        else:
            total_errors += 1

        diagnostic = Diagnostic(
            location=location,
            severity=severity,
            message=message,
            include_stack=list(include_stack),
            template_stack=list(template_stack),
            notes=list(pending_notes),
            snippet=source_context(location, root, context_lines=context_lines),
        )
        diagnostics.append(diagnostic)
        last_primary = diagnostic
        include_stack = []
        template_stack = []
        pending_notes = []

        if len(diagnostics) >= limit:
            break

    return DiagnosticReport(
        diagnostics=diagnostics,
        total_errors=total_errors,
        total_warnings=total_warnings,
        total_notes=total_notes,
    )


def normalize_path(value: str, root: Path) -> str:
    path = Path(value.strip())
    if not path.is_absolute():
        candidate = (root / path).resolve()
        if candidate.exists():
            return str(candidate)
        return path.as_posix()
    return str(path)


def source_context(location: SourceLocation, root: Path, *, context_lines: int) -> str:
    path = Path(location.path)
    if not path.is_absolute():
        path = root / path
    if not path.is_file():
        return ""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if not (1 <= location.line <= len(lines)):
        return ""
    start = max(1, location.line - context_lines)
    end = min(len(lines), location.line + context_lines)
    width = len(str(end))
    output: list[str] = []
    for line_number in range(start, end + 1):
        marker = ">" if line_number == location.line else " "
        output.append(f"{marker} {line_number:{width}d}: {lines[line_number - 1]}")
        if line_number == location.line and location.column:
            caret_padding = " " * (location.column + width + 3)
            output.append(f"{caret_padding}^")
    return "\n".join(output)


def load_log(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    return Path(path).expanduser().read_text(encoding="utf-8", errors="replace")


def report_to_json(report: DiagnosticReport) -> str:
    return json.dumps(report.to_dict(), ensure_ascii=False, indent=2)
