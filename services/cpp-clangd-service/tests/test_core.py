from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cpp_clangd_service.core import (
    CLASSLIKE_KINDS,
    Location,
    Position,
    Range,
    SymbolCandidate,
    camel_to_snake,
    direct_candidate_score,
    extract_source,
    mask_comments_and_strings,
    runtime_paths,
    score_candidate,
    symbol_candidate_source_files,
)


class CoreTests(unittest.TestCase):
    def test_runtime_paths_are_stable_for_project(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first = runtime_paths(Path(directory))
            second = runtime_paths(Path(directory))
            self.assertEqual(first.port, second.port)
            self.assertEqual(first.project_id, second.project_id)

    def test_score_prefers_exact_symbol(self) -> None:
        self.assertLess(score_candidate("Foo::bar", "bar", "Foo"), score_candidate("Foo::bar", "bar", "Other"))

    def test_mask_comments_and_strings(self) -> None:
        masked = mask_comments_and_strings('real(); "fake()"; // also_fake()\n')
        self.assertIn("real", masked)
        self.assertNotIn("fake", masked)
        self.assertNotIn("also_fake", masked)

    def test_extract_source_returns_class_body(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "node.h"
            path.write_text("class Node {\npublic:\n    void add_child();\n};\n", encoding="utf-8")

            snippet = extract_source(path, Position(line=0, character=6), symbol_name="Node", kind=5)

            self.assertIn("class Node", snippet.source)
            self.assertIn("add_child", snippet.source)

    def test_camel_to_snake_keeps_numeric_suffixes_searchable(self) -> None:
        self.assertEqual(camel_to_snake("NavigationServer2D"), "navigation_server_2d")

    def test_candidate_source_files_prefers_nested_type_definition(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            usage = root / "scene" / "ray_cast_3d.cpp"
            usage.parent.mkdir(parents=True)
            usage.write_text(
                "void cast() { PhysicsDirectSpaceState3D::RayResult result; }\n",
                encoding="utf-8",
            )
            definition = root / "servers" / "physics_3d" / "physics_server_3d.h"
            definition.parent.mkdir(parents=True)
            definition.write_text(
                "class PhysicsDirectSpaceState3D {\npublic:\n    struct RayResult {};\n};\n",
                encoding="utf-8",
            )

            files = symbol_candidate_source_files(root, "PhysicsDirectSpaceState3D::RayResult")

            self.assertEqual(files[0], definition)

    def test_direct_candidate_score_prefers_class_body(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            forward = root / "resource.h"
            forward.write_text("class Node;\n", encoding="utf-8")
            definition = root / "node.h"
            definition.write_text("class Node {\n};\n", encoding="utf-8")

            candidates = [
                _candidate("Node", forward, kind=next(iter(CLASSLIKE_KINDS))),
                _candidate("Node", definition, kind=next(iter(CLASSLIKE_KINDS))),
            ]

            ordered = sorted(candidates, key=lambda item: direct_candidate_score(item, "Node"))

            self.assertEqual(ordered[0].location.path, definition)


def _candidate(name: str, path: Path, *, kind: int = 12) -> SymbolCandidate:
    position = Position(line=0, character=0)
    return SymbolCandidate(
        name=name,
        container_name="",
        kind=kind,
        location=Location(path, Range(position, Position(line=0, character=len(name)))),
        score=(0, 0, 0),
    )


if __name__ == "__main__":
    unittest.main()
