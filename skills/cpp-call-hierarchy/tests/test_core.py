from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cpp_call_hierarchy.core import mask_comments_and_strings, source_line, score_candidate


class CoreTests(unittest.TestCase):
    def test_source_line_returns_trimmed_line(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "a.cpp"
            path.write_text("int a;\n  call();\n", encoding="utf-8")
            self.assertEqual(source_line(path, 1), "call();")

    def test_score_prefers_exact(self) -> None:
        self.assertLess(score_candidate("Foo::bar", "bar", "Foo"), score_candidate("Foo::bar", "bar", "Baz"))

    def test_mask_comments_and_strings_preserves_real_calls_only(self) -> None:
        masked = mask_comments_and_strings('real_call(); "fake_call()"; // comment_call()\n')
        self.assertIn("real_call", masked)
        self.assertNotIn("fake_call", masked)
        self.assertNotIn("comment_call", masked)


if __name__ == "__main__":
    unittest.main()
