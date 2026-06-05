# cpp-include-analyzer

`include-analyzer` 是一个独立的 C++ include 图分析 CLI 工具。它用于观察大型 C++ 项目的 include 耦合、潜在编译成本和局部风险点。

该工具只使用 Python 标准库，不依赖 clangd，也不依赖 `cpp-symbol-scout` 或 `cpp-include-finder`。

## 用法

分析项目：

```bash
PYTHONPATH=src python3 -m include_analyzer analyze --project /path/to/project
```

输出 JSON：

```bash
PYTHONPATH=src python3 -m include_analyzer analyze \
  --project /path/to/project \
  --json
```

查看单个文件：

```bash
PYTHONPATH=src python3 -m include_analyzer file scene/main/node.h \
  --project /path/to/project
```

## 分析内容

- include 边数量；
- 可解析和不可解析 include；
- 文件 fan-in：被多少文件 include；
- 文件 fan-out：include 了多少项目内文件；
- 热点头文件：按 `fan_in * 3 + fan_out` 排序；
- 重复 include；
- include 循环依赖。

## include 解析

工具默认会：

- 将项目根目录作为 include root；
- 尝试读取 `compile_commands.json` 并提取 `-I`、`-isystem`、`-iquote`、`/I`；
- 对双引号 include 先从当前文件目录解析，再从 include roots 解析；
- 对尖括号 include 从 include roots 解析。

如果不想读取 `compile_commands.json`，可以使用：

```bash
PYTHONPATH=src python3 -m include_analyzer analyze \
  --project /path/to/project \
  --no-compile-commands
```

## 设计边界

该工具做的是 include 图静态分析，不执行预处理器，也不判断某个 include 是否真正必要。它适合快速发现高耦合头文件、重复 include、解析失败的 include 和循环风险；“可删除 include”需要结合编译验证或专门的 include-cleaner 工具。

