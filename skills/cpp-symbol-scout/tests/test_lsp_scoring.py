from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cpp_symbol_scout.daemon import (
    QueryOptions,
    _camel_to_snake,
    _direct_candidate_score,
    _prefer_function_definitions,
    candidate_source_files,
    document_symbol_query,
)
from cpp_symbol_scout.lsp import _score_candidate
from cpp_symbol_scout.models import Location, Position, Range, SymbolCandidate


def _candidate(
    *,
    name: str,
    container: str,
    path: Path,
    line: int,
    score: tuple[int, int, int],
    kind: int = 12,
) -> SymbolCandidate:
    position = Position(line=line, character=0)
    return SymbolCandidate(
        name=name,
        container_name=container,
        kind=kind,
        location=Location(
            path=path,
            range=Range(start=position, end=Position(line=line, character=12)),
        ),
        score=score,
    )


class LspScoringTests(unittest.TestCase):
    def test_scoring_prefers_full_exact_match(self) -> None:
        exact = _score_candidate("EditorNode::save_scene", "save_scene", "EditorNode")
        leaf = _score_candidate("EditorNode::save_scene", "save_scene", "Other")

        self.assertLess(exact, leaf)

    def test_scoring_prefers_case_sensitive_leaf_match(self) -> None:
        exact_leaf = _score_candidate("Node", "Node", "")
        case_only = _score_candidate("Node", "node", "")

        self.assertLess(exact_leaf, case_only)

    def test_prefer_function_definitions_keeps_score_before_body_shape(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            declaration = root / "thing.h"
            declaration.write_text("void exact();\n", encoding="utf-8")
            implementation = root / "other.cpp"
            implementation.write_text("void other() {}\n", encoding="utf-8")

            candidates = [
                _candidate(
                    name="other",
                    container="",
                    path=implementation,
                    line=0,
                    score=(2, 0, 5),
                ),
                _candidate(
                    name="exact",
                    container="",
                    path=declaration,
                    line=0,
                    score=(0, 0, 0),
                ),
            ]

            ordered = _prefer_function_definitions(candidates, root, "exact")

            self.assertEqual(ordered[0].name, "exact")

    def test_prefer_function_definitions_breaks_score_ties_by_body_shape(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            declaration = root / "thing.h"
            declaration.write_text("void exact();\n", encoding="utf-8")
            implementation = root / "thing.cpp"
            implementation.write_text("void exact() {}\n", encoding="utf-8")

            candidates = [
                _candidate(
                    name="exact",
                    container="",
                    path=declaration,
                    line=0,
                    score=(0, 0, 0),
                ),
                _candidate(
                    name="exact",
                    container="",
                    path=implementation,
                    line=0,
                    score=(0, 0, 0),
                ),
            ]

            ordered = _prefer_function_definitions(candidates, root, "exact")

            self.assertEqual(ordered[0].location.path, implementation)

    def test_camel_to_snake_keeps_numeric_suffixes_searchable(self) -> None:
        self.assertEqual(_camel_to_snake("NavigationServer2D"), "navigation_server_2d")
        self.assertEqual(_camel_to_snake("PhysicsServer3DExtension"), "physics_server_3d_extension")

    def test_direct_candidate_score_marks_non_matching_symbols_last(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "world_2d.cpp"
            path.write_text("World2D::World2D() {}\n", encoding="utf-8")
            candidate = _candidate(
                name="World2D",
                container="World2D",
                path=path,
                line=0,
                score=(0, 0, 0),
            )

            self.assertEqual(_direct_candidate_score(candidate, "NavigationServer2D")[0], 5)

    def test_direct_candidate_score_prefers_class_body_over_forward_declaration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            forward = root / "resource.h"
            forward.write_text("class Node;\n", encoding="utf-8")
            definition = root / "node.h"
            definition.write_text("class Node {\n};\n", encoding="utf-8")
            candidates = [
                _candidate(
                    name="Node",
                    container="",
                    path=forward,
                    line=0,
                    score=(0, 0, 0),
                    kind=5,
                ),
                _candidate(
                    name="Node",
                    container="",
                    path=definition,
                    line=0,
                    score=(0, 0, 0),
                    kind=5,
                ),
            ]

            ordered = sorted(candidates, key=lambda item: _direct_candidate_score(item, "Node"))

            self.assertEqual(ordered[0].location.path, definition)

    def test_candidate_source_files_prefers_nested_type_definition_over_use_sites(self) -> None:
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

            files = candidate_source_files(root, "PhysicsDirectSpaceState3D::RayResult")

            self.assertEqual(files[0], definition)

    def test_document_symbol_query_does_not_return_unmatched_fallback_symbols(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "world_2d.cpp"
            source.write_text("World2D::World2D() {}\n", encoding="utf-8")
            candidate = _candidate(
                name="World2D",
                container="World2D",
                path=source,
                line=0,
                score=(0, 0, 0),
            )

            class FakeClient:
                def document_symbols(self, *_args, **_kwargs):
                    return [candidate]

            results = document_symbol_query(
                client=FakeClient(),
                project_root=root,
                files=[source],
                symbol="NavigationServer2D",
                options=QueryOptions(limit=1, timeout=1, resolve_implementation=False),
            )

            self.assertEqual(results, [])


if __name__ == "__main__":
    unittest.main()
