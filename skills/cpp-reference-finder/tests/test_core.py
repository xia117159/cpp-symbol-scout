from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cpp_reference_finder.core import Position, Range, Location, dedupe_locations, score_candidate


class CoreTests(unittest.TestCase):
    def test_score_prefers_exact_qualified_match(self) -> None:
        exact = score_candidate("Foo::bar", "bar", "Foo")
        leaf = score_candidate("Foo::bar", "bar", "Other")
        self.assertLess(exact, leaf)

    def test_dedupe_locations_keeps_one_per_position(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "a.cpp"
            path.write_text("int x;\n", encoding="utf-8")
            location = Location(path, Range(Position(0, 4), Position(0, 5)))
            self.assertEqual(dedupe_locations([location, location]), [location])


if __name__ == "__main__":
    unittest.main()
