# cpp-include-finder

`include-finder` 是一个独立的 C++ 头文件查找 CLI 工具。它扫描项目中的头文件，建立类型声明索引，并根据类名、结构体名、枚举名或别名快速返回推荐的 `#include` 路径。

该工具只使用 Python 标准库，不依赖 clangd，也不依赖 `cpp-symbol-scout`。

## 用法

直接查询：

```bash
PYTHONPATH=src python3 -m include_finder find Node --project /path/to/project
```

生成索引：

```bash
PYTHONPATH=src python3 -m include_finder build-index \
  --project /path/to/project \
  --output /tmp/include-finder-index.json
```

使用索引查询：

```bash
PYTHONPATH=src python3 -m include_finder find Node \
  --index /tmp/include-finder-index.json \
  --json
```

## 输出含义

每个结果包含：

- `qualified_name`：声明的限定名；
- `kind`：`class`、`struct`、`enum class`、`using`、`typedef` 等；
- `path`、`line`、`column`：声明位置；
- `include`：推荐写入代码的 include 路径；
- `is_definition`：是否为带定义体的声明；
- `snippet`：声明源码片段。

## 设计边界

该工具是通用静态扫描器，不执行完整 C++ 语义分析。它适合快速为 AI 提供头文件候选；如果项目存在复杂宏生成类型或条件编译，结果应作为候选而不是唯一真值。

