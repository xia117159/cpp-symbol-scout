from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cpp_diagnostic_context.core import analyze_log


class DiagnosticContextTests(unittest.TestCase):
    def test_parses_error_with_include_stack_and_snippet(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "src" / "main.cpp"
            source.parent.mkdir()
            source.write_text("int main() {\n  return missing;\n}\n", encoding="utf-8")
            log = (
                'In file included from include/demo.h:3:\n'
                'src/main.cpp:2:10: error: use of undeclared identifier \'missing\'\n'
                'src/main.cpp:2:10: note: did you mean something else?\n'
            )
            report = analyze_log(log, project_root=root)
            self.assertEqual(report.total_errors, 1)
            self.assertEqual(len(report.diagnostics), 1)
            self.assertIn("return missing", report.diagnostics[0].snippet)
            self.assertEqual(len(report.diagnostics[0].include_stack), 1)
            self.assertEqual(len(report.diagnostics[0].notes), 1)


if __name__ == "__main__":
    unittest.main()
