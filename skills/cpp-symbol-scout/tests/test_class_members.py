from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cpp_symbol_scout.class_members import (
    extract_class_members,
    members_payload_from_symbol_result,
    select_class_symbol_result,
)
from cpp_symbol_scout.models import Position, Range


class ClassMemberTests(unittest.TestCase):
    def test_extract_members_tracks_access_and_strips_inline_method_bodies(self) -> None:
        source = """
template <typename T>
class Box final {
public:
    Box() : value() {}
    T get() const { return value; }
    void set(T p_value);
    using Value = T;
protected:
    int protected_count = 0;
private:
    struct Impl {
        int flag;
    };
    T value;
};
""".lstrip()
        members = extract_class_members(
            source,
            path=Path("/tmp/box.h"),
            source_range=Range(Position(10, 0), Position(25, 0)),
            symbol_name="demo::Box",
            symbol_kind=5,
        )

        by_name = {member.name: member for member in members}
        self.assertEqual(by_name["Box"].access, "public")
        self.assertEqual(by_name["Box"].kind, "method")
        self.assertEqual(by_name["Box"].declaration, "Box();")
        self.assertEqual(by_name["get"].declaration, "T get() const;")
        self.assertNotIn("return value", by_name["get"].declaration)
        self.assertEqual(by_name["set"].declaration, "void set(T p_value);")
        self.assertEqual(by_name["Value"].kind, "type")
        self.assertEqual(by_name["protected_count"].access, "protected")
        self.assertEqual(by_name["value"].access, "private")
        self.assertEqual(by_name["Impl"].kind, "type")

    def test_struct_members_default_to_public(self) -> None:
        source = """
struct Point {
    int x;
    int y;
};
""".lstrip()
        members = extract_class_members(
            source,
            path=Path("/tmp/point.h"),
            source_range=Range(Position(0, 0), Position(4, 0)),
            symbol_name="Point",
            symbol_kind=23,
        )

        self.assertEqual([member.access for member in members], ["public", "public"])

    def test_members_payload_filters_public_methods(self) -> None:
        source = """
class Node {
public:
    void add_child(Node *p_child);
    int get_child_count() const { return count; }
private:
    int count = 0;
};
""".lstrip()
        result = {
            "name": "Node",
            "full_name": "Node",
            "kind": 5,
            "kind_name": "Class",
            "location": {
                "path": "/tmp/node.h",
                "line": 1,
                "column": 7,
                "range": {
                    "start": {"line": 0, "character": 0},
                    "end": {"line": 7, "character": 0},
                },
            },
            "source_range": {
                "start": {"line": 0, "character": 0},
                "end": {"line": 7, "character": 0},
            },
            "source": source,
        }

        payload = members_payload_from_symbol_result(
            result,
            project_root="/tmp",
            access="public",
            member_kind="method",
        )

        self.assertEqual(payload["summary"]["member_count"], 3)
        self.assertEqual(payload["summary"]["returned_count"], 2)
        self.assertEqual([member["name"] for member in payload["members"]], ["add_child", "get_child_count"])
        self.assertEqual(payload["members"][1]["declaration"], "int get_child_count() const;")

    def test_select_class_symbol_result_ignores_function_results(self) -> None:
        function = {"kind": 12, "source": "void f() {}\n"}
        klass = {"kind": 5, "source": "class Node {\npublic:\n    void f();\n};\n"}

        self.assertIs(select_class_symbol_result([function, klass]), klass)


if __name__ == "__main__":
    unittest.main()

