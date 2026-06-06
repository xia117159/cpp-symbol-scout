from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


CPP_SUFFIXES = {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx", ".ipp", ".inl"}
SOURCE_SUFFIXES = {".c", ".cc", ".cpp", ".cxx"}
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
    "out",
    "thirdparty",
    "vendor",
}

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
DIAGNOSTIC_RE = re.compile(
    r"^(?P<path>[^:\n][^:\n]*?):(?P<line>\d+):(?:(?P<column>\d+):)?\s*"
    r"(?P<severity>fatal error|error|warning|note):\s*"
    r"(?P<message>.*?)(?:\s+\[(?P<check>[^\]]+)\])?\s*$"
)


class ToolError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProjectConfig:
    project_root: Path
    clang_tidy_path: str
    compile_commands_dir: Path | None

    @classmethod
    def discover(
        cls,
        project: str | os.PathLike[str],
        *,
        clang_tidy: str = "clang-tidy",
        compile_commands_dir: str | os.PathLike[str] | None = None,
        require_compile_db: bool = True,
    ) -> "ProjectConfig":
        project_root = Path(project).expanduser().resolve()
        if not project_root.exists():
            raise ToolError(f"project path does not exist: {project_root}")
        if not project_root.is_dir():
            raise ToolError(f"project path is not a directory: {project_root}")

        resolved_clang_tidy = resolve_clang_tidy(clang_tidy)
        if not resolved_clang_tidy:
            raise ToolError(
                "clang-tidy was not found in PATH. Install clang-tidy or pass --clang-tidy /path/to/clang-tidy."
            )

        if compile_commands_dir is None:
            db_dir = find_compile_commands_dir(project_root)
        else:
            db_dir = Path(compile_commands_dir).expanduser().resolve()
            if not db_dir.exists() or not db_dir.is_dir():
                raise ToolError(f"compile commands directory is invalid: {db_dir}")
            if not has_compile_commands(db_dir):
                raise ToolError(f"no compile_commands.json in {db_dir}")

        if require_compile_db and db_dir is None:
            raise ToolError(
                "no compile_commands.json was found. Generate one with your build system, "
                "then pass --compile-commands-dir if it is not in the project root."
            )

        return cls(
            project_root=project_root,
            clang_tidy_path=str(resolved_clang_tidy),
            compile_commands_dir=db_dir,
        )


@dataclass(frozen=True)
class SourceLocation:
    path: Path
    line: int
    column: int | None = None

    def to_dict(self, project_root: Path) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "relative_path": relative_path(self.path, project_root),
            "line": self.line,
            "column": self.column,
        }


@dataclass
class DiagnosticNote:
    location: SourceLocation
    message: str

    def to_dict(self, project_root: Path) -> dict[str, Any]:
        return {
            "location": self.location.to_dict(project_root),
            "message": self.message,
        }


@dataclass
class StaticDiagnostic:
    location: SourceLocation
    severity: str
    message: str
    check_name: str | None = None
    notes: list[DiagnosticNote] = field(default_factory=list)
    snippet: str = ""

    @property
    def has_fixit_hint(self) -> bool:
        haystack = " ".join([self.message, *(note.message for note in self.notes)]).lower()
        return "fix-it" in haystack or "fixit" in haystack or "use -fix" in haystack

    def to_dict(self, project_root: Path) -> dict[str, Any]:
        return {
            "location": self.location.to_dict(project_root),
            "severity": self.severity,
            "message": self.message,
            "check_name": self.check_name,
            "has_fixit_hint": self.has_fixit_hint,
            "snippet": self.snippet,
            "notes": [note.to_dict(project_root) for note in self.notes],
        }


@dataclass(frozen=True)
class FileCheckResult:
    path: Path
    command: list[str]
    exit_code: int | None
    elapsed_ms: float
    diagnostic_count: int
    timed_out: bool = False
    error_message: str = ""

    def to_dict(self, project_root: Path) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "relative_path": relative_path(self.path, project_root),
            "command": self.command,
            "command_string": shlex.join(self.command),
            "exit_code": self.exit_code,
            "elapsed_ms": round(self.elapsed_ms, 3),
            "diagnostics": self.diagnostic_count,
            "timed_out": self.timed_out,
            "error_message": self.error_message,
        }


@dataclass(frozen=True)
class CheckReport:
    project_root: Path
    clang_tidy_path: str | None
    compile_commands_dir: Path | None
    files_requested: int
    file_results: list[FileCheckResult]
    diagnostics: list[StaticDiagnostic]
    elapsed_ms: float
    mode: str

    def summary(self) -> dict[str, Any]:
        warnings = sum(1 for item in self.diagnostics if item.severity == "warning")
        errors = sum(1 for item in self.diagnostics if item.severity in {"fatal error", "error"})
        notes = sum(
            (1 if item.severity == "note" else 0) + len(item.notes)
            for item in self.diagnostics
        )
        unique_checks = sorted(
            {item.check_name for item in self.diagnostics if item.check_name}
        )
        failed_files = [
            item for item in self.file_results if item.timed_out or (item.exit_code not in {0, None})
        ]
        return {
            "mode": self.mode,
            "files_requested": self.files_requested,
            "files_checked": len(self.file_results),
            "files_with_diagnostics": len(
                {item.location.path for item in self.diagnostics}
            ),
            "diagnostics": len(self.diagnostics),
            "warnings": warnings,
            "errors": errors,
            "notes": notes,
            "unique_checks": unique_checks,
            "unique_check_count": len(unique_checks),
            "failed_files": len(failed_files),
            "timed_out_files": sum(1 for item in self.file_results if item.timed_out),
            "elapsed_ms": round(self.elapsed_ms, 3),
        }

    def to_dict(self, *, limit: int | None = None) -> dict[str, Any]:
        diagnostics = self.diagnostics[:limit] if limit is not None else self.diagnostics
        return {
            "project_root": str(self.project_root),
            "clang_tidy": self.clang_tidy_path,
            "compile_commands_dir": str(self.compile_commands_dir) if self.compile_commands_dir else None,
            "summary": {
                **self.summary(),
                "diagnostics_returned": len(diagnostics),
                "diagnostics_truncated": limit is not None and len(self.diagnostics) > limit,
            },
            "files": [item.to_dict(self.project_root) for item in self.file_results],
            "diagnostics": [item.to_dict(self.project_root) for item in diagnostics],
        }


@dataclass(frozen=True)
class CheckOptions:
    checks: str | None = None
    warnings_as_errors: str | None = None
    header_filter: str | None = None
    system_headers: bool = False
    quiet: bool = True
    fix: bool = False
    fix_errors: bool = False
    config_file: Path | None = None
    extra_args: tuple[str, ...] = ()
    extra_args_before: tuple[str, ...] = ()
    timeout: float = 0.0
    context_lines: int = 2


def resolve_clang_tidy(clang_tidy: str = "clang-tidy") -> str | None:
    if os.path.sep in clang_tidy:
        candidate = Path(clang_tidy).expanduser()
        return str(candidate.resolve()) if candidate.exists() else None

    resolved = shutil.which(clang_tidy)
    if resolved:
        return resolved

    if clang_tidy != "clang-tidy":
        return None

    for name in (
        "clang-tidy-20",
        "clang-tidy-19",
        "clang-tidy-18",
        "clang-tidy-17",
        "clang-tidy-16",
        "clang-tidy-15",
        "clang-tidy-14",
    ):
        resolved = shutil.which(name)
        if resolved:
            return resolved

    for candidate in sorted(Path("/usr/lib").glob("llvm-*/bin/clang-tidy"), reverse=True):
        if candidate.exists():
            return str(candidate)
    return None


def has_compile_commands(path: Path) -> bool:
    return (path / "compile_commands.json").is_file()


def find_compile_commands_dir(project_root: Path) -> Path | None:
    if has_compile_commands(project_root):
        return project_root

    common_dirs = [
        "build",
        "out",
        "out/build",
        "cmake-build-debug",
        "cmake-build-release",
        "build/debug",
        "build/release",
    ]
    for relative in common_dirs:
        candidate = project_root / relative
        if candidate.is_dir() and has_compile_commands(candidate):
            return candidate

    max_depth = 3
    root_depth = len(project_root.parts)
    for current, dirnames, filenames in os.walk(project_root):
        current_path = Path(current)
        depth = len(current_path.parts) - root_depth
        if depth >= max_depth:
            dirnames[:] = []
        dirnames[:] = [
            name
            for name in dirnames
            if not name.startswith(".") and name not in {"thirdparty", "vendor", "node_modules"}
        ]
        if "compile_commands.json" in filenames:
            return current_path
    return None


def discover_cpp_files(project_root: str | os.PathLike[str], *, source_only: bool = False) -> list[Path]:
    root = Path(project_root).expanduser().resolve()
    suffixes = SOURCE_SUFFIXES if source_only else CPP_SUFFIXES
    result: list[Path] = []
    for directory, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            dirname
            for dirname in dirnames
            if dirname not in SKIP_DIRS and not dirname.startswith(".cache")
        ]
        current = Path(directory)
        for filename in filenames:
            path = current / filename
            if path.suffix.lower() in suffixes:
                result.append(path.resolve())
    result.sort(key=lambda path: relative_path(path, root) or str(path))
    return result


def explicit_files(
    project_root: str | os.PathLike[str],
    files: list[str],
    *,
    source_only: bool = False,
) -> list[Path]:
    root = Path(project_root).expanduser().resolve()
    suffixes = SOURCE_SUFFIXES if source_only else CPP_SUFFIXES
    selected: list[Path] = []
    for value in files:
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = root / path
        path = path.resolve()
        if not path.exists():
            raise ToolError(f"file does not exist: {path}")
        if not path.is_file():
            raise ToolError(f"path is not a file: {path}")
        if path.suffix.lower() not in suffixes:
            continue
        selected.append(path)
    return dedupe_paths(selected, root)


def changed_files(
    project_root: str | os.PathLike[str],
    *,
    base: str = "HEAD",
    include_untracked: bool = True,
    source_only: bool = False,
) -> list[Path]:
    root = Path(project_root).expanduser().resolve()
    if not (root / ".git").exists() and not _git_ok(root, ["rev-parse", "--is-inside-work-tree"]):
        raise ToolError(f"project is not a git working tree: {root}")

    names: list[str] = []
    names.extend(
        _git_lines(
            root,
            ["diff", "--name-only", "--diff-filter=ACMRTUXB", base, "--"],
        )
    )
    if include_untracked:
        names.extend(_git_lines(root, ["ls-files", "--others", "--exclude-standard"]))

    suffixes = SOURCE_SUFFIXES if source_only else CPP_SUFFIXES
    paths: list[Path] = []
    for name in names:
        path = (root / name).resolve()
        if path.is_file() and path.suffix.lower() in suffixes:
            paths.append(path)
    return dedupe_paths(paths, root)


def dedupe_paths(paths: list[Path], project_root: str | os.PathLike[str]) -> list[Path]:
    root = Path(project_root).expanduser().resolve()
    seen: set[Path] = set()
    result: list[Path] = []
    for path in paths:
        path = path.resolve()
        if path not in seen:
            result.append(path)
            seen.add(path)
    result.sort(key=lambda item: relative_path(item, root) or str(item))
    return result


def enforce_max_files(files: list[Path], max_files: int) -> list[Path]:
    if max_files <= 0 or len(files) <= max_files:
        return files
    raise ToolError(f"selected {len(files)} files, which exceeds --max-files {max_files}")


def build_clang_tidy_command(config: ProjectConfig, file_path: Path, options: CheckOptions) -> list[str]:
    command = [config.clang_tidy_path, str(file_path)]
    if config.compile_commands_dir is not None:
        command.extend(["-p", str(config.compile_commands_dir)])
    if options.quiet:
        command.append("--quiet")
    if options.checks:
        command.append(f"--checks={options.checks}")
    if options.warnings_as_errors:
        command.append(f"--warnings-as-errors={options.warnings_as_errors}")
    if options.header_filter:
        command.append(f"--header-filter={options.header_filter}")
    if options.system_headers:
        command.append("--system-headers")
    if options.fix:
        command.append("--fix")
    if options.fix_errors:
        command.append("--fix-errors")
    if options.config_file is not None:
        command.append(f"--config-file={options.config_file}")
    for value in options.extra_args:
        command.append(f"--extra-arg={value}")
    for value in options.extra_args_before:
        command.append(f"--extra-arg-before={value}")
    return command


def run_checks(
    config: ProjectConfig,
    files: list[Path],
    *,
    options: CheckOptions,
    mode: str,
) -> CheckReport:
    started = time.monotonic()
    file_results: list[FileCheckResult] = []
    diagnostics: list[StaticDiagnostic] = []

    for file_path in files:
        command = build_clang_tidy_command(config, file_path, options)
        file_started = time.monotonic()
        try:
            completed = subprocess.run(
                command,
                cwd=config.project_root,
                text=True,
                capture_output=True,
                timeout=options.timeout if options.timeout > 0 else None,
                check=False,
            )
            output = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
            parsed = parse_diagnostics(
                output,
                project_root=config.project_root,
                context_lines=options.context_lines,
            )
            diagnostics.extend(parsed)
            file_results.append(
                FileCheckResult(
                    path=file_path,
                    command=command,
                    exit_code=completed.returncode,
                    elapsed_ms=(time.monotonic() - file_started) * 1000,
                    diagnostic_count=len(parsed),
                )
            )
        except subprocess.TimeoutExpired as exc:
            output = "\n".join(
                part.decode("utf-8", errors="replace") if isinstance(part, bytes) else str(part)
                for part in (exc.stdout, exc.stderr)
                if part
            )
            parsed = parse_diagnostics(
                output,
                project_root=config.project_root,
                context_lines=options.context_lines,
            )
            diagnostics.extend(parsed)
            file_results.append(
                FileCheckResult(
                    path=file_path,
                    command=command,
                    exit_code=None,
                    elapsed_ms=(time.monotonic() - file_started) * 1000,
                    diagnostic_count=len(parsed),
                    timed_out=True,
                    error_message=f"clang-tidy timed out after {options.timeout:g}s",
                )
            )

    return CheckReport(
        project_root=config.project_root,
        clang_tidy_path=config.clang_tidy_path,
        compile_commands_dir=config.compile_commands_dir,
        files_requested=len(files),
        file_results=file_results,
        diagnostics=diagnostics,
        elapsed_ms=(time.monotonic() - started) * 1000,
        mode=mode,
    )


def report_from_log(
    text: str,
    *,
    project_root: str | os.PathLike[str] = ".",
    context_lines: int = 2,
) -> CheckReport:
    root = Path(project_root).expanduser().resolve()
    diagnostics = parse_diagnostics(text, project_root=root, context_lines=context_lines)
    return CheckReport(
        project_root=root,
        clang_tidy_path=None,
        compile_commands_dir=find_compile_commands_dir(root),
        files_requested=0,
        file_results=[],
        diagnostics=diagnostics,
        elapsed_ms=0.0,
        mode="explain",
    )


def parse_diagnostics(
    text: str,
    *,
    project_root: str | os.PathLike[str],
    context_lines: int = 2,
) -> list[StaticDiagnostic]:
    root = Path(project_root).expanduser().resolve()
    diagnostics: list[StaticDiagnostic] = []
    last_primary: StaticDiagnostic | None = None

    for raw_line in strip_ansi(text).splitlines():
        line = raw_line.rstrip()
        match = DIAGNOSTIC_RE.match(line)
        if not match:
            continue

        location = SourceLocation(
            path=normalize_path(match.group("path"), root),
            line=int(match.group("line")),
            column=int(match.group("column")) if match.group("column") else None,
        )
        severity = match.group("severity")
        message = match.group("message").strip()
        check_name = match.group("check")

        if severity == "note" and last_primary is not None:
            last_primary.notes.append(DiagnosticNote(location=location, message=message))
            continue

        diagnostic = StaticDiagnostic(
            location=location,
            severity=severity,
            message=message,
            check_name=check_name,
            snippet=source_context(location, root, context_lines=context_lines),
        )
        diagnostics.append(diagnostic)
        if severity != "note":
            last_primary = diagnostic

    return diagnostics


def list_checks(
    *,
    clang_tidy: str = "clang-tidy",
    checks: str = "*",
    project_root: str | os.PathLike[str] = ".",
    config_file: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    resolved = resolve_clang_tidy(clang_tidy)
    if not resolved:
        raise ToolError("clang-tidy was not found. Install clang-tidy or pass --clang-tidy.")
    command = [resolved, "--list-checks", f"--checks={checks}"]
    if config_file is not None:
        command.append(f"--config-file={Path(config_file).expanduser().resolve()}")
    completed = subprocess.run(
        command,
        cwd=Path(project_root).expanduser().resolve(),
        text=True,
        capture_output=True,
        check=False,
    )
    output = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
    if completed.returncode != 0:
        raise ToolError(output.strip() or f"clang-tidy failed with exit code {completed.returncode}")
    enabled = parse_list_checks(output)
    return {
        "clang_tidy": resolved,
        "checks_expression": checks,
        "enabled_checks": enabled,
        "enabled_check_count": len(enabled),
    }


def parse_list_checks(text: str) -> list[str]:
    checks: list[str] = []
    in_section = False
    for raw_line in strip_ansi(text).splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line == "Enabled checks:":
            in_section = True
            continue
        if in_section:
            checks.append(line)
    return checks


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def normalize_path(value: str, root: Path) -> Path:
    path = Path(value.strip())
    if not path.is_absolute():
        candidate = (root / path).resolve()
        if candidate.exists():
            return candidate
        return candidate
    try:
        return path.resolve()
    except OSError:
        return path


def source_context(location: SourceLocation, root: Path, *, context_lines: int) -> str:
    path = location.path
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


def relative_path(path: Path, project_root: str | os.PathLike[str]) -> str | None:
    root = Path(project_root).expanduser().resolve()
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return None


def load_text(path: str) -> str:
    if path == "-":
        import sys

        return sys.stdin.read()
    return Path(path).expanduser().read_text(encoding="utf-8", errors="replace")


def report_to_json(report: CheckReport, *, limit: int | None = None) -> str:
    return json.dumps(report.to_dict(limit=limit), ensure_ascii=False, indent=2)


def _git_ok(root: Path, args: list[str]) -> bool:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), *args],
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError:
        return False
    return completed.returncode == 0


def _git_lines(root: Path, args: list[str]) -> list[str]:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), *args],
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        raise ToolError("git was not found in PATH") from exc
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip()
        raise ToolError(message or f"git {' '.join(args)} failed")
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]

