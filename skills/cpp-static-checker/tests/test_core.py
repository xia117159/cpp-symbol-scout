from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cpp_static_checker.core import (
    CheckOptions,
    ProjectConfig,
    build_clang_tidy_command,
    discover_cpp_files,
    explicit_files,
    parse_diagnostics,
    parse_list_checks,
    report_from_log,
)


class StaticCheckerCoreTests(unittest.TestCase):
    def test_parse_diagnostics_attaches_notes_and_source_context(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "src" / "main.cpp"
            source.parent.mkdir()
            source.write_text("int main() {\n  int *p = 0;\n  return p == 0;\n}\n", encoding="utf-8")
            output = (
                "src/main.cpp:2:12: warning: use nullptr [modernize-use-nullptr]\n"
                "src/main.cpp:2:12: note: FIX-IT available\n"
            )

            diagnostics = parse_diagnostics(output, project_root=root, context_lines=1)

            self.assertEqual(len(diagnostics), 1)
            diagnostic = diagnostics[0]
            self.assertEqual(diagnostic.severity, "warning")
            self.assertEqual(diagnostic.check_name, "modernize-use-nullptr")
            self.assertEqual(len(diagnostic.notes), 1)
            self.assertTrue(diagnostic.has_fixit_hint)
            self.assertIn("int *p = 0", diagnostic.snippet)

    def test_report_summary_counts_checks_and_notes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "a.cpp"
            source.write_text("int main() { return 0; }\n", encoding="utf-8")
            report = report_from_log(
                "a.cpp:1:5: error: bad thing [bugprone-test]\n"
                "a.cpp:1:5: note: related thing\n",
                project_root=root,
            )

            summary = report.summary()

            self.assertEqual(summary["diagnostics"], 1)
            self.assertEqual(summary["errors"], 1)
            self.assertEqual(summary["notes"], 1)
            self.assertEqual(summary["unique_checks"], ["bugprone-test"])

    def test_parse_list_checks(self) -> None:
        output = "Enabled checks:\n    bugprone-use-after-move\n    modernize-use-nullptr\n"

        self.assertEqual(
            parse_list_checks(output),
            ["bugprone-use-after-move", "modernize-use-nullptr"],
        )

    def test_discover_and_explicit_files_filter_cpp_suffixes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src").mkdir()
            (root / "src" / "a.cpp").write_text("", encoding="utf-8")
            (root / "src" / "b.hpp").write_text("", encoding="utf-8")
            (root / "src" / "notes.txt").write_text("", encoding="utf-8")

            self.assertEqual(len(discover_cpp_files(root)), 2)
            self.assertEqual(len(discover_cpp_files(root, source_only=True)), 1)
            self.assertEqual(len(explicit_files(root, ["src/a.cpp", "src/notes.txt"])), 1)

    def test_build_clang_tidy_command(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = ProjectConfig(
                project_root=root,
                clang_tidy_path="/usr/bin/clang-tidy",
                compile_commands_dir=root / "build",
            )
            options = CheckOptions(
                checks="bugprone-*",
                warnings_as_errors="*",
                header_filter=".*",
                system_headers=True,
                fix=True,
                extra_args=("-std=c++20",),
            )

            command = build_clang_tidy_command(config, root / "a.cpp", options)

            self.assertIn("-p", command)
            self.assertIn(str(root / "build"), command)
            self.assertIn("--checks=bugprone-*", command)
            self.assertIn("--warnings-as-errors=*", command)
            self.assertIn("--header-filter=.*", command)
            self.assertIn("--system-headers", command)
            self.assertIn("--fix", command)
            self.assertIn("--extra-arg=-std=c++20", command)


if __name__ == "__main__":
    unittest.main()
