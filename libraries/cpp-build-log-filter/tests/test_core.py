from __future__ import annotations

import unittest

from cpp_build_log_filter import FilterOptions, filter_build_log, filter_build_log_result


class BuildLogFilterTests(unittest.TestCase):
    def test_keeps_error_block_and_drops_progress_and_commands(self) -> None:
        log = """
[ 12%] Building CXX object CMakeFiles/app.dir/main.cpp.o
/usr/bin/c++ -Iinclude -Wall -c /tmp/main.cpp
/tmp/main.cpp:7:13: error: 'missing' was not declared in this scope
    7 |     return missing();
      |            ^~~~~~~
gmake[2]: *** [CMakeFiles/app.dir/build.make:76: CMakeFiles/app.dir/main.cpp.o] Error 1
gmake[1]: *** [CMakeFiles/Makefile2:83: CMakeFiles/app.dir/all] Error 2
gmake: *** [Makefile:91: all] Error 2
""".strip()

        filtered = filter_build_log(log)

        self.assertIn("error: 'missing' was not declared", filtered)
        self.assertIn("|            ^~~~~~~", filtered)
        self.assertIn("gmake: ***", filtered)
        self.assertNotIn("Building CXX object", filtered)
        self.assertNotIn("/usr/bin/c++ -Iinclude", filtered)

    def test_drops_warnings_when_errors_exist_by_default(self) -> None:
        log = """
main.cpp:3:5: warning: unused variable 'x' [-Wunused-variable]
    3 | int x;
      |     ^
main.cpp:8:1: error: expected ';' before '}' token
    8 | }
      | ^
""".strip()

        filtered = filter_build_log(log)

        self.assertIn("error: expected ';'", filtered)
        self.assertNotIn("unused variable", filtered)

    def test_drops_warnings_by_default_even_when_no_errors(self) -> None:
        log = """
[ 50%] Building CXX object CMakeFiles/app.dir/main.cpp.o
main.cpp:3:5: warning: unused variable 'x' [-Wunused-variable]
    3 | int x;
      |     ^
""".strip()

        filtered = filter_build_log(log)

        self.assertEqual(filtered, "")

    def test_keeps_limited_warnings_when_enabled(self) -> None:
        log = """
[ 50%] Building CXX object CMakeFiles/app.dir/main.cpp.o
main.cpp:3:5: warning: unused variable 'x' [-Wunused-variable]
    3 | int x;
      |     ^
main.cpp:4:5: warning: unused variable 'y' [-Wunused-variable]
    4 | int y;
      |     ^
""".strip()

        filtered = filter_build_log(log, FilterOptions(keep_warnings=True, max_warnings=1))

        self.assertIn("unused variable 'x'", filtered)
        self.assertNotIn("unused variable 'y'", filtered)

    def test_keep_warnings_keeps_warnings_with_errors(self) -> None:
        log = """
main.cpp:3:5: warning: unused variable 'x' [-Wunused-variable]
main.cpp:8:1: error: expected ';' before '}' token
""".strip()

        filtered = filter_build_log(log, FilterOptions(keep_warnings=True))

        self.assertIn("unused variable", filtered)
        self.assertIn("expected ';'", filtered)

    def test_warning_files_keeps_only_matching_warning_path(self) -> None:
        log = """
src/target.cpp:3:5: warning: unused variable 'target' [-Wunused-variable]
    3 | int target;
      |     ^~~~~~
src/other.cpp:4:5: warning: unused variable 'other' [-Wunused-variable]
    4 | int other;
      |     ^~~~~
""".strip()

        filtered = filter_build_log(
            log,
            FilterOptions(keep_warnings=True, warning_files=("target.cpp",)),
        )

        self.assertIn("unused variable 'target'", filtered)
        self.assertNotIn("unused variable 'other'", filtered)

    def test_warning_files_alone_enables_matching_warnings(self) -> None:
        log = """
src/target.cpp:3:5: warning: unused variable 'target' [-Wunused-variable]
src/other.cpp:4:5: warning: unused variable 'other' [-Wunused-variable]
""".strip()

        filtered = filter_build_log(log, FilterOptions(warning_files="target.cpp"))

        self.assertIn("unused variable 'target'", filtered)
        self.assertNotIn("unused variable 'other'", filtered)

    def test_keep_warnings_false_overrides_warning_files(self) -> None:
        log = "src/target.cpp:3:5: warning: unused variable 'target' [-Wunused-variable]"

        filtered = filter_build_log(
            log,
            FilterOptions(keep_warnings=False, warning_files="target.cpp"),
        )

        self.assertEqual(filtered, "")

    def test_warning_files_supports_header_basename_from_absolute_path(self) -> None:
        log = """
/tmp/project/include/widget.h:12:7: warning: private field 'value' is not used [-Wunused-private-field]
   12 |   int value;
      |       ^~~~~
/tmp/project/src/widget.cpp:22:9: warning: unused variable 'local' [-Wunused-variable]
   22 |     int local;
      |         ^~~~~
""".strip()

        filtered = filter_build_log(
            log,
            FilterOptions(keep_warnings=True, warning_files=("widget.h",)),
        )

        self.assertIn("private field 'value'", filtered)
        self.assertNotIn("unused variable 'local'", filtered)

    def test_keeps_linker_error_context(self) -> None:
        log = """
[100%] Linking CXX executable app
/usr/bin/ld: CMakeFiles/app.dir/main.cpp.o: in function `main':
main.cpp:(.text+0x12): undefined reference to `missing()'
collect2: error: ld returned 1 exit status
make[2]: *** [CMakeFiles/app.dir/build.make:97: app] Error 1
""".strip()

        filtered = filter_build_log(log)

        self.assertIn("/usr/bin/ld:", filtered)
        self.assertIn("undefined reference to `missing()'", filtered)
        self.assertIn("collect2: error", filtered)
        self.assertNotIn("Linking CXX executable", filtered)

    def test_keeps_compiler_context_before_error(self) -> None:
        log = """
g++ -std=c++17 -Wall -Wextra -c main.cpp
main.cpp: In function ‘int main()’:
main.cpp:5:18: error: ‘missing_symbol’ was not declared in this scope
    5 |     std::cout << missing_symbol() << "\\n";
      |                  ^~~~~~~~~~~~~~
main.cpp:4:9: warning: unused variable ‘unused’ [-Wunused-variable]
""".strip()

        filtered = filter_build_log(log)

        self.assertIn("main.cpp: In function", filtered)
        self.assertIn("missing_symbol", filtered)
        self.assertNotIn("unused variable", filtered)

    def test_keeps_cmake_error_and_call_stack(self) -> None:
        log = """
-- Configuring done
CMake Error at CMakeLists.txt:12 (add_executable):
  Cannot find source file:

    missing.cpp

Call Stack (most recent call first):
  src/CMakeLists.txt:3 (add_project_target)
-- Generating done
""".strip()

        filtered = filter_build_log(log)

        self.assertIn("CMake Error at CMakeLists.txt:12", filtered)
        self.assertIn("Cannot find source file", filtered)
        self.assertIn("src/CMakeLists.txt:3", filtered)
        self.assertNotIn("-- Configuring done", filtered)

    def test_strips_ansi_and_dedupes_repeated_diagnostics(self) -> None:
        log = "\n".join(
            [
                "\x1b[01mmain.cpp:1:1: error: bad thing\x1b[0m",
                "main.cpp:1:1: error: bad thing",
            ]
        )

        filtered = filter_build_log(log)

        self.assertEqual(filtered, "main.cpp:1:1: error: bad thing")

    def test_returns_stats(self) -> None:
        result = filter_build_log_result(
            """
g++ -std=c++17 -Wall -Wextra -c main.cpp
[1/2] Building CXX object app.o
main.cpp:1:1: warning: noisy
main.cpp:2:1: error: broken
""".strip()
        )

        self.assertEqual(result.stats.errors, 1)
        self.assertEqual(result.stats.warnings, 1)
        self.assertEqual(result.stats.progress_lines, 1)
        self.assertEqual(result.stats.command_lines, 1)
        self.assertLess(result.stats.output_lines, result.stats.input_lines)


if __name__ == "__main__":
    unittest.main()
