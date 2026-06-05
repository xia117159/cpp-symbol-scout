from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cpp_symbol_scout.paths import find_compile_commands_dir, has_compile_database


class PathTests(unittest.TestCase):
    def test_find_compile_commands_in_project_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            (tmp_path / "compile_commands.json").write_text("[]", encoding="utf-8")

            self.assertTrue(has_compile_database(tmp_path))
            self.assertEqual(find_compile_commands_dir(tmp_path), tmp_path)


    def test_find_compile_commands_in_common_build_dir(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            build = tmp_path / "build"
            build.mkdir()
            (build / "compile_commands.json").write_text("[]", encoding="utf-8")

            self.assertEqual(find_compile_commands_dir(tmp_path), build)


    def test_missing_compile_commands_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            (tmp_path / "src").mkdir()

            self.assertIsNone(find_compile_commands_dir(tmp_path))


if __name__ == "__main__":
    unittest.main()
