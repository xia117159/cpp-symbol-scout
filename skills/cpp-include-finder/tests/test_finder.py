from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from include_finder.finder import build_index, find_declarations


class IncludeFinderTests(unittest.TestCase):
    def test_finds_class_definition_and_include_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            header = root / "include" / "demo" / "node.h"
            header.parent.mkdir(parents=True)
            header.write_text(
                """
namespace demo {
class Node {
public:
    void tick();
};
}
""".lstrip(),
                encoding="utf-8",
            )

            index = build_index(root, include_roots=[root / "include"])
            results = find_declarations(index, "demo::Node", limit=1)

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].qualified_name, "demo::Node")
            self.assertEqual(results[0].include, "demo/node.h")
            self.assertTrue(results[0].is_definition)

    def test_prefers_definition_over_forward_declaration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            forward = root / "include" / "resource.h"
            forward.parent.mkdir(parents=True)
            forward.write_text("class Node;\n", encoding="utf-8")
            definition = root / "scene" / "node.h"
            definition.parent.mkdir(parents=True)
            definition.write_text("class Node {\n};\n", encoding="utf-8")

            index = build_index(root)
            results = find_declarations(index, "Node", limit=2)

            self.assertEqual(results[0].path, str(definition))

    def test_finds_nested_struct(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            header = root / "physics_server_3d.h"
            header.write_text(
                """
class PhysicsDirectSpaceState3D {
public:
    struct RayResult {
        int shape = 0;
    };
};
""".lstrip(),
                encoding="utf-8",
            )

            index = build_index(root)
            results = find_declarations(index, "PhysicsDirectSpaceState3D::RayResult", limit=1)

            self.assertEqual(results[0].qualified_name, "PhysicsDirectSpaceState3D::RayResult")
            self.assertEqual(results[0].include, "physics_server_3d.h")


if __name__ == "__main__":
    unittest.main()
