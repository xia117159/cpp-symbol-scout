from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cpp_symbol_scout.models import Position
from cpp_symbol_scout.snippets import extract_source


class SnippetTests(unittest.TestCase):
    def test_extract_class_definition(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            source = """
namespace demo {
template <typename T>
class Box final {
public:
    T get() const;
private:
    T value;
};
}
""".lstrip()
            path = tmp_path / "box.h"
            path.write_text(source, encoding="utf-8")

            snippet = extract_source(path, Position(line=2, character=6), symbol_name="Box", kind=5)

            self.assertTrue(snippet.source.startswith("template <typename T>"))
            self.assertIn("class Box final", snippet.source)
            self.assertTrue(snippet.source.rstrip().endswith("};"))


    def test_extract_function_body(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            source = """
int helper();

int EditorNode::save_scene(const String &p_path) const {
    if (p_path.is_empty()) {
        return ERR_INVALID_PARAMETER;
    }
    return OK;
}
""".lstrip()
            path = tmp_path / "editor_node.cpp"
            path.write_text(source, encoding="utf-8")

            snippet = extract_source(
                path,
                Position(line=2, character=17),
                symbol_name="EditorNode::save_scene",
                kind=6,
            )

            self.assertTrue(snippet.source.startswith("int EditorNode::save_scene"))
            self.assertIn("return ERR_INVALID_PARAMETER;", snippet.source)
            self.assertTrue(snippet.source.rstrip().endswith("}"))


    def test_extract_declaration_when_no_body(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            source = """
class Node {
public:
    void add_child(Node *p_child);
};
""".lstrip()
            path = tmp_path / "node.h"
            path.write_text(source, encoding="utf-8")

            snippet = extract_source(
                path,
                Position(line=2, character=10),
                symbol_name="Node::add_child",
                kind=6,
            )

            self.assertEqual(snippet.source.strip(), "void add_child(Node *p_child);")


    def test_comment_braces_do_not_break_function_extraction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            source = """
void f() {
    // }
    const char *s = "{";
    call();
}
""".lstrip()
            path = tmp_path / "sample.cpp"
            path.write_text(source, encoding="utf-8")

            snippet = extract_source(path, Position(line=0, character=5), symbol_name="f", kind=12)

            self.assertEqual(snippet.source, source.rstrip())


if __name__ == "__main__":
    unittest.main()
