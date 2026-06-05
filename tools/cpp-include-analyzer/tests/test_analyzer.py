from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from include_analyzer.analyzer import analyze_project, file_report, summarize_analysis


class IncludeAnalyzerTests(unittest.TestCase):
    def test_analyzes_fan_in_fan_out_and_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            include = root / "include"
            src = root / "src"
            include.mkdir()
            src.mkdir()
            (include / "a.h").write_text(
                '#include "b.h"\n#include "b.h"\n',
                encoding="utf-8",
            )
            (include / "b.h").write_text("#pragma once\n", encoding="utf-8")
            (src / "main.cpp").write_text('#include "a.h"\n', encoding="utf-8")

            analysis = analyze_project(root, include_roots=[include], use_compile_commands=False)
            summary = summarize_analysis(analysis)

            self.assertEqual(summary["files_scanned"], 3)
            self.assertEqual(summary["duplicate_include_files"], 1)
            self.assertIn(
                {"path": "include/b.h", "count": 2},
                summary["top_fan_in"],
            )

            report = file_report(analysis, "include/a.h")
            self.assertEqual(report["fan_out"], 2)
            self.assertEqual(len(report["duplicate_includes"]), 1)

    def test_detects_include_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.h").write_text('#include "b.h"\n', encoding="utf-8")
            (root / "b.h").write_text('#include "a.h"\n', encoding="utf-8")

            analysis = analyze_project(root, use_compile_commands=False)

            self.assertEqual(len(analysis.cycles), 1)
            self.assertEqual(sorted(analysis.cycles[0]), ["a.h", "b.h"])


if __name__ == "__main__":
    unittest.main()
