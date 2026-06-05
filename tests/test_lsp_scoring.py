from __future__ import annotations

import unittest

from cpp_symbol_scout.lsp import _score_candidate


class LspScoringTests(unittest.TestCase):
    def test_scoring_prefers_full_exact_match(self) -> None:
        exact = _score_candidate("EditorNode::save_scene", "save_scene", "EditorNode")
        leaf = _score_candidate("EditorNode::save_scene", "save_scene", "Other")

        self.assertLess(exact, leaf)


    def test_scoring_prefers_case_sensitive_leaf_match(self) -> None:
        exact_leaf = _score_candidate("Node", "Node", "")
        case_only = _score_candidate("Node", "node", "")

        self.assertLess(exact_leaf, case_only)


if __name__ == "__main__":
    unittest.main()
