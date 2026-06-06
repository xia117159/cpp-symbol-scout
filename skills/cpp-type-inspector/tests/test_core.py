from __future__ import annotations

import unittest

from cpp_type_inspector.core import extract_type_summary, score_candidate


class CoreTests(unittest.TestCase):
    def test_extract_type_summary_from_code_block(self) -> None:
        summary = extract_type_summary("```cpp\nNode *Node::get_parent() const\n```")
        self.assertEqual(summary["display"], "Node *Node::get_parent() const")

    def test_score_prefers_leaf_match(self) -> None:
        self.assertLess(score_candidate("Node::get_parent", "get_parent", "Node"), score_candidate("Node::get_parent", "get_child", "Node"))


if __name__ == "__main__":
    unittest.main()
