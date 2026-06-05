from __future__ import annotations

import hashlib
import os
import shutil
from dataclasses import dataclass
from pathlib import Path


class ConfigurationError(RuntimeError):
    """Raised when the project or clangd environment is not usable."""


@dataclass(frozen=True)
class ProjectConfig:
    project_root: Path
    clangd_path: str
    compile_commands_dir: Path | None
    require_compile_db: bool = True

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
        if not project_root.exists():
            raise ConfigurationError(f"project path does not exist: {project_root}")
        if not project_root.is_dir():
            raise ConfigurationError(f"project path is not a directory: {project_root}")

        resolved_clangd = resolve_clangd(clangd)
        if not resolved_clangd:
            raise ConfigurationError(
                "clangd was not found in PATH. Install clangd or pass --clangd /path/to/clangd."
            )

        if compile_commands_dir is None:
            db_dir = find_compile_commands_dir(project_root)
        else:
            db_dir = Path(compile_commands_dir).expanduser().resolve()
            if not db_dir.exists() or not db_dir.is_dir():
                raise ConfigurationError(f"compile commands directory is invalid: {db_dir}")
            if not has_compile_database(db_dir):
                raise ConfigurationError(
                    f"no compile_commands.json or compile_flags.txt in {db_dir}"
                )

        if require_compile_db and db_dir is None:
            raise ConfigurationError(
                "no compile_commands.json or compile_flags.txt was found. "
                "Generate one with your build system, then pass --compile-commands-dir "
                "if it is not in the project root."
            )

        return cls(
            project_root=project_root,
            clangd_path=str(resolved_clangd),
            compile_commands_dir=db_dir,
            require_compile_db=require_compile_db,
        )


@dataclass(frozen=True)
class RuntimePaths:
    base_dir: Path
    socket_path: Path
    pid_path: Path
    log_path: Path
    project_id: str
    host: str
    port: int


def has_compile_database(path: Path) -> bool:
    return (path / "compile_commands.json").is_file() or (path / "compile_flags.txt").is_file()


def resolve_clangd(clangd: str = "clangd") -> str | None:
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


def find_compile_commands_dir(project_root: Path) -> Path | None:
    if has_compile_database(project_root):
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
        if candidate.is_dir() and has_compile_database(candidate):
            return candidate

    max_depth = 3
    root_depth = len(project_root.parts)
    for current, dirnames, filenames in os.walk(project_root):
        current_path = Path(current)
        depth = len(current_path.parts) - root_depth
        if depth >= max_depth:
            dirnames[:] = []
        dirnames[:] = [
            name for name in dirnames if not name.startswith(".") and name not in {"thirdparty"}
        ]
        if "compile_commands.json" in filenames or "compile_flags.txt" in filenames:
            return current_path
    return None


def runtime_paths(project_root: Path) -> RuntimePaths:
    project_real = str(project_root.resolve())
    project_id = hashlib.sha1(project_real.encode("utf-8")).hexdigest()[:20]
    workspace_runtime = Path.cwd() / ".runtime" / "cpp-symbol-scout"
    try:
        workspace_runtime.mkdir(mode=0o700, parents=True, exist_ok=True)
        base_dir = workspace_runtime
    except OSError:
        base_dir = None

    runtime_root = os.environ.get("XDG_RUNTIME_DIR")
    if base_dir is None:
        if runtime_root:
            base_dir = Path(runtime_root) / "cpp-symbol-scout"
        else:
            base_dir = Path("/tmp") / f"cpp-symbol-scout-{os.getuid()}"
        try:
            base_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        except OSError:
            base_dir = Path("/tmp") / f"cpp-symbol-scout-{os.getuid()}"
            base_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    return RuntimePaths(
        base_dir=base_dir,
        socket_path=base_dir / f"{project_id}.sock",
        pid_path=base_dir / f"{project_id}.pid",
        log_path=base_dir / f"{project_id}.log",
        project_id=project_id,
        host="127.0.0.1",
        port=46000 + (int(project_id[:8], 16) % 10000),
    )
