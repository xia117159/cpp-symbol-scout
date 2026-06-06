# cpp-build-log-filter

`cpp-build-log-filter` 是一个只处理文本的 Python 库，用于压缩 CMake/Make/GCC/Clang 构建日志，方便 AI Agent 在编译失败时读取关键信息。

它不执行构建命令，不包装 CMake/Make，只接收一整段构建输出并返回过滤后的文本。

## 为什么单独实现

现有开源项目里，`gccoutputparser` 这类库更偏“解析 GCC/LLVM 诊断”；`scan-build`、`CodeChecker`、`compiledb` 等工具更偏构建包装、静态分析或编译数据库生成。它们不太适合作为一个轻量的“AI 上下文压缩过滤器”直接使用。

本库的目标是：

- 丢弃 CMake/Make/Ninja 进度行；
- 丢弃普通编译命令行；
- 保留 C/C++ error、fatal error、linker error、CMake Error；
- 默认隐藏 warning，避免 warning 噪声挤占 AI 上下文；
- 支持显式保留 warning，也支持只保留某个 `.cpp`/`.h` 文件的 warning；
- 保留源码行、caret、include 栈、模板实例化上下文、CMake call stack；
- 返回结构化统计，便于 Agent 判断压缩效果。

## API

```python
from cpp_build_log_filter import FilterOptions, filter_build_log, filter_build_log_result

filtered = filter_build_log(raw_build_output)

result = filter_build_log_result(
    raw_build_output,
    FilterOptions(
        keep_warnings=True,
        max_warnings=10,
        include_summary=True,
    ),
)

print(result.text)
print(result.stats.errors, result.stats.warnings)
```

Warning 过滤参数：

- `keep_warnings=None`：默认值。不传 `warning_files` 时不输出 warning；传了 `warning_files` 时只输出匹配文件的 warning。
- `keep_warnings=False`：强制不输出任何 warning，即使传了 `warning_files`。
- `keep_warnings=True`：输出 warning，最多保留 `max_warnings` 条。
- `warning_files="foo.cpp"` 或 `warning_files=("src/foo.cpp", "bar.h")`：只保留路径后缀或文件名匹配的 warning。

示例：

```python
# 默认：只保留 error/fatal error/linker error/CMake Error，不输出 warning。
filtered = filter_build_log(raw_build_output)

# 保留 warning，最多 5 条。
filtered = filter_build_log(
    raw_build_output,
    FilterOptions(keep_warnings=True, max_warnings=5),
)

# 只保留 main.cpp 的 warning。
filtered = filter_build_log(
    raw_build_output,
    FilterOptions(warning_files="main.cpp"),
)

# 显式关闭 warning，输出中不会包含任何 warning。
filtered = filter_build_log(
    raw_build_output,
    FilterOptions(keep_warnings=False),
)
```

## 验证

运行单元测试：

```bash
cd /home/cheng/workspace/cpp-symbol-scout/libraries/cpp-build-log-filter
PYTHONPATH=src python3 -B -m unittest discover -s tests -v
```

实际 C++ 小项目测试：

```bash
cd /home/cheng/workspace/cpp-symbol-scout/libraries/cpp-build-log-filter

# 默认示例：执行 examples/simple-make-project 的 make，并打印过滤后的构建输出。
python3 examples/run_filtered_build.py --clean --summary

# 同时打印原始构建输出，便于对比过滤前后效果。
python3 examples/run_filtered_build.py --clean --show-raw --summary

# 保留 warning。
python3 examples/run_filtered_build.py --clean --keep-warnings --summary

# 只保留某个 .cpp/.h 文件的 warning。
python3 examples/run_filtered_build.py --clean --warning-file noisy.hpp --summary

# 执行自定义构建命令。-- 后面的内容会作为构建命令执行。
python3 examples/run_filtered_build.py --project examples/simple-make-project -- make CXX=clang++
```

`examples/run_filtered_build.py` 是演示壳脚本：它负责执行编译命令、捕获 stdout/stderr，再调用 `cpp-build-log-filter` 输出过滤结果。它不属于核心库 API。

Make 示例：

```bash
cd examples/make-warning-error
make clean
make 2>&1 | tee /tmp/build.log

PYTHONPATH=../../src python3 - <<'PY'
from pathlib import Path
from cpp_build_log_filter import FilterOptions, filter_build_log_result

result = filter_build_log_result(Path("/tmp/build.log").read_text(), FilterOptions(include_summary=True))
print(result.text)
PY
```

`examples/cmake-sample` 提供 CMake 工程结构样例。当前环境未安装 `cmake` 时，仍可通过单元测试中的 CMake 日志样例覆盖 CMake 输出格式。
