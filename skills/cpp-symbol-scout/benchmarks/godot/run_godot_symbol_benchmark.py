#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROJECT = Path("/home/cheng/godotengine/godot-master")
DEFAULT_CASES = Path(__file__).with_name("godot_symbol_cases.json")
DEFAULT_RESULTS_DIR = Path(__file__).with_name("results")


@dataclass(frozen=True)
class QueryRun:
    phase: str
    case: dict[str, Any]
    command_elapsed_ms: float
    returncode: int
    stdout: str
    stderr: str
    results: list[dict[str, Any]]
    error: str | None


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Godot symbol lookup benchmark cases.")
    parser.add_argument("--project", type=Path, default=DEFAULT_PROJECT)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--clangd", default="clangd-18")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--cold-stop", action="store_true", help="stop any existing service first")
    parser.add_argument("--start-timeout", type=float, default=30.0)
    parser.add_argument("--warmup-timeout", type=float, default=4.0)
    args = parser.parse_args()

    project = args.project.expanduser().resolve()
    cases_path = args.cases.expanduser().resolve()
    results_dir = args.results_dir.expanduser().resolve()
    results_dir.mkdir(parents=True, exist_ok=True)

    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    if not isinstance(cases, list):
        raise SystemExit("cases file must be a JSON array")

    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT / "src")

    if args.cold_stop:
        run_cli(args.python, ["stop", "--project", str(project)], env=env, check=False)
        time.sleep(0.5)

    start_result = run_cli(
        args.python,
        [
            "start",
            "--project",
            str(project),
            "--clangd",
            args.clangd,
            "--wait",
            "--wait-timeout",
            str(args.start_timeout),
        ],
        env=env,
        check=False,
    )
    if start_result.returncode != 0:
        sys.stderr.write(start_result.stderr)
        sys.stderr.write(start_result.stdout)
        return start_result.returncode

    status = run_cli(args.python, ["status", "--project", str(project), "--json"], env=env)
    status_data = json.loads(status.stdout)

    runs: list[QueryRun] = []
    for case in cases:
        runs.append(query_case(args.python, project, case, env=env, phase="first"))
    for case in cases:
        runs.append(query_case(args.python, project, case, env=env, phase="cached"))

    evaluated = [evaluate_run(run) for run in runs]

    jsonl_path = results_dir / "godot_symbol_benchmark.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for item in evaluated:
            handle.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")

    summary = build_summary(
        project=project,
        cases_path=cases_path,
        status_data=status_data,
        evaluated=evaluated,
    )
    summary_path = results_dir / "godot_symbol_benchmark_summary.md"
    summary_path.write_text(summary, encoding="utf-8")

    print(f"wrote {jsonl_path}")
    print(f"wrote {summary_path}")

    required_failures = [
        item
        for item in evaluated
        if item["phase"] == "first" and item["required"] and not item["passed"]
    ]
    return 1 if required_failures else 0


def query_case(
    python: str,
    project: Path,
    case: dict[str, Any],
    *,
    env: dict[str, str],
    phase: str,
) -> QueryRun:
    args = [
        "query",
        str(case["symbol"]),
        "--project",
        str(project),
        "--timeout",
        str(case.get("timeout", 4.0)),
        "--limit",
        str(case.get("limit", 3)),
        "--json",
    ]
    if case.get("no_implementation"):
        args.append("--no-implementation")

    started = time.perf_counter()
    completed = run_cli(python, args, env=env, check=False)
    elapsed_ms = (time.perf_counter() - started) * 1000

    results: list[dict[str, Any]] = []
    error: str | None = None
    if completed.stdout.strip():
        try:
            decoded = json.loads(completed.stdout)
            if isinstance(decoded, list):
                results = decoded
            else:
                error = "stdout JSON is not an array"
        except json.JSONDecodeError as exc:
            error = f"invalid JSON stdout: {exc}"
    elif completed.returncode != 0:
        error = completed.stderr.strip() or "query returned no stdout"

    return QueryRun(
        phase=phase,
        case=case,
        command_elapsed_ms=elapsed_ms,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        results=results,
        error=error,
    )


def evaluate_run(run: QueryRun) -> dict[str, Any]:
    case = run.case
    expect = case.get("expect", {})
    first = run.results[0] if run.results else None
    checks: dict[str, bool] = {}

    checks["returned_results"] = bool(run.results)
    if "min_results" in expect:
        checks["min_results"] = len(run.results) >= int(expect["min_results"])
    if first is not None:
        checks["first_kind"] = (
            "first_kind" not in expect or first.get("kind_name") == expect["first_kind"]
        )
        checks["full_name_contains"] = contains(first.get("full_name"), expect.get("full_name_contains"))
        checks["path_contains"] = contains(first.get("location", {}).get("path"), expect.get("path_contains"))
        checks["source_contains"] = contains(first.get("source"), expect.get("source_contains"))
    else:
        checks["first_kind"] = "first_kind" not in expect
        checks["full_name_contains"] = "full_name_contains" not in expect
        checks["path_contains"] = "path_contains" not in expect
        checks["source_contains"] = "source_contains" not in expect

    if "any_full_name_contains" in expect:
        checks["any_full_name_contains"] = any(
            contains(result.get("full_name"), expect["any_full_name_contains"])
            for result in run.results
        )
    if "any_path_contains" in expect:
        checks["any_path_contains"] = any(
            contains(result.get("location", {}).get("path"), expect["any_path_contains"])
            for result in run.results
        )

    checks["tool_elapsed_under_1s"] = bool(first and float(first.get("elapsed_ms", 10**9)) < 1000)
    checks["command_elapsed_under_1s"] = run.command_elapsed_ms < 1000

    semantic_checks = {
        name: value
        for name, value in checks.items()
        if name not in {"tool_elapsed_under_1s", "command_elapsed_under_1s"}
    }
    passed = all(semantic_checks.values()) and run.error is None and run.returncode == 0

    return {
        "id": case["id"],
        "category": case["category"],
        "symbol": case["symbol"],
        "phase": run.phase,
        "required": bool(case.get("required", True)),
        "passed": passed,
        "checks": checks,
        "returncode": run.returncode,
        "error": run.error,
        "command_elapsed_ms": round(run.command_elapsed_ms, 3),
        "result_count": len(run.results),
        "first_result": summarize_result(first),
        "all_results": [summarize_result(result) for result in run.results],
    }


def contains(value: Any, needle: Any) -> bool:
    if needle is None:
        return True
    if value is None:
        return False
    return str(needle) in str(value)


def summarize_result(result: dict[str, Any] | None) -> dict[str, Any] | None:
    if result is None:
        return None
    source = str(result.get("source") or "")
    return {
        "kind_name": result.get("kind_name"),
        "full_name": result.get("full_name"),
        "resolution": result.get("resolution"),
        "elapsed_ms": result.get("elapsed_ms"),
        "path": result.get("location", {}).get("path"),
        "line": result.get("location", {}).get("line"),
        "source_first_line": first_nonempty_line(source),
        "source_line_count": len(source.splitlines()),
    }


def first_nonempty_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:160]
    return ""


def build_summary(
    *,
    project: Path,
    cases_path: Path,
    status_data: dict[str, Any],
    evaluated: list[dict[str, Any]],
) -> str:
    first_phase = [item for item in evaluated if item["phase"] == "first"]
    cached_phase = [item for item in evaluated if item["phase"] == "cached"]

    first_pass = sum(1 for item in first_phase if item["passed"])
    cached_pass = sum(1 for item in cached_phase if item["passed"])
    required_first = [item for item in first_phase if item["required"]]
    required_first_pass = sum(1 for item in required_first if item["passed"])

    first_tool_times = [
        item["first_result"]["elapsed_ms"]
        for item in first_phase
        if item["first_result"] and item["first_result"]["elapsed_ms"] is not None
    ]
    cached_tool_times = [
        item["first_result"]["elapsed_ms"]
        for item in cached_phase
        if item["first_result"] and item["first_result"]["elapsed_ms"] is not None
    ]

    lines = [
        "# Godot 符号查询压测结果",
        "",
        f"- 项目：`{project}`",
        f"- 用例文件：`{cases_path}`",
        f"- clangd：`{status_data.get('clangd')}`",
        f"- compile_commands_dir：`{status_data.get('compile_commands_dir')}`",
        f"- service：`{status_data.get('tcp')}`",
        "",
        "## 总览",
        "",
        f"- 首次查询通过：{first_pass}/{len(first_phase)}",
        f"- 首次查询必测通过：{required_first_pass}/{len(required_first)}",
        f"- 缓存查询通过：{cached_pass}/{len(cached_phase)}",
        f"- 首次查询耗时：{format_stats(first_tool_times)}",
        f"- 缓存查询耗时：{format_stats(cached_tool_times)}",
        "",
        "## 首次查询明细",
        "",
        "| ID | 类别 | 符号 | 通过 | 结果 | 工具耗时(ms) | 位置 | 首行 |",
        "| --- | --- | --- | --- | --- | ---: | --- | --- |",
    ]
    lines.extend(table_rows(first_phase))
    lines.extend(
        [
            "",
            "## 缓存查询明细",
            "",
            "| ID | 类别 | 符号 | 通过 | 结果 | 工具耗时(ms) | 位置 | 首行 |",
            "| --- | --- | --- | --- | --- | ---: | --- | --- |",
        ]
    )
    lines.extend(table_rows(cached_phase))

    failures = [item for item in first_phase if not item["passed"]]
    lines.extend(["", "## 首次查询失败或薄弱项", ""])
    if not failures:
        lines.append("无。")
    else:
        for item in failures:
            failed_checks = [
                name for name, value in item["checks"].items()
                if not value and name not in {"tool_elapsed_under_1s", "command_elapsed_under_1s"}
            ]
            lines.append(
                f"- `{item['id']}` `{item['symbol']}`：失败检查 `{', '.join(failed_checks) or 'unknown'}`；"
                f"首个结果 `{format_first_result(item)}`"
            )

    slow_first = [
        item for item in first_phase
        if not item["checks"].get("tool_elapsed_under_1s", False)
    ]
    slow_cached = [
        item for item in cached_phase
        if not item["checks"].get("tool_elapsed_under_1s", False)
    ]
    lines.extend(["", "## 1 秒性能检查", ""])
    lines.append(f"- 首次查询超过 1 秒：{len(slow_first)} 个")
    lines.append(f"- 缓存查询超过 1 秒：{len(slow_cached)} 个")
    if slow_first:
        lines.append("- 首次慢查询：" + ", ".join(f"`{item['symbol']}`" for item in slow_first))
    if slow_cached:
        lines.append("- 缓存慢查询：" + ", ".join(f"`{item['symbol']}`" for item in slow_cached))

    lines.extend(
        [
            "",
            "## 说明",
            "",
            "- “通过”只统计语义校验，不把 1 秒耗时作为硬性通过条件；耗时单独在性能检查中记录。",
            "- `required=false` 的用例用于记录宏、typedef/using、namespace、字段等当前实现的边界。",
            "- `tool_elapsed_ms` 来自服务返回的结果；`command_elapsed_ms` 包含 CLI 进程启动和 JSON 输出成本。",
        ]
    )
    return "\n".join(lines) + "\n"


def table_rows(items: list[dict[str, Any]]) -> list[str]:
    rows = []
    for item in items:
        first = item["first_result"] or {}
        location = ""
        if first.get("path"):
            location = f"{short_path(first['path'])}:{first.get('line')}"
        rows.append(
            "| {id} | {category} | `{symbol}` | {passed} | {kind} {full_name} | {elapsed} | `{location}` | {source} |".format(
                id=escape_md(item["id"]),
                category=escape_md(item["category"]),
                symbol=escape_md(item["symbol"]),
                passed="是" if item["passed"] else "否",
                kind=escape_md(str(first.get("kind_name") or "")),
                full_name=escape_md(str(first.get("full_name") or "")),
                elapsed=first.get("elapsed_ms", ""),
                location=escape_md(location),
                source=escape_md(str(first.get("source_first_line") or "")),
            )
        )
    return rows


def format_first_result(item: dict[str, Any]) -> str:
    first = item.get("first_result") or {}
    if not first:
        return "no result"
    return f"{first.get('kind_name')} {first.get('full_name')} {short_path(first.get('path'))}:{first.get('line')}"


def format_stats(values: list[float]) -> str:
    if not values:
        return "无数据"
    ordered = sorted(float(value) for value in values)
    return (
        f"min={ordered[0]:.3f}, "
        f"p50={statistics.median(ordered):.3f}, "
        f"max={ordered[-1]:.3f}"
    )


def short_path(path: Any) -> str:
    if not path:
        return ""
    text = str(path)
    marker = "/godot-master/"
    if marker in text:
        return text.split(marker, 1)[1]
    return text


def escape_md(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def run_cli(
    python: str,
    args: list[str],
    *,
    env: dict[str, str],
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    command = [python, "-B", "-m", "cpp_symbol_scout", *args]
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and completed.returncode != 0:
        raise subprocess.CalledProcessError(
            completed.returncode,
            command,
            output=completed.stdout,
            stderr=completed.stderr,
        )
    return completed


if __name__ == "__main__":
    raise SystemExit(main())
