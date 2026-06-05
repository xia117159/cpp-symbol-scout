# 独立 C++ 工具与 Skills

本目录存放与 `cpp-symbol-scout` 并列的独立 CLI 工具。它们共享同一个 git 仓库，但不是同一个 Python 包，也不依赖 `cpp-symbol-scout`。

## 当前工具

- `cpp-include-finder`：扫描 C++ 头文件声明，快速查找类型、枚举、typedef、using alias 对应的推荐 include。
- `cpp-include-analyzer`：扫描 C++ include 图，分析 fan-in、fan-out、重复 include、未解析 include、热点头文件和 include 循环。

## 与 SKILL 的关系

这两个目录现在也都是独立 Skill：

- `tools/cpp-include-finder/SKILL.md`
- `tools/cpp-include-analyzer/SKILL.md`

它们可以作为独立 Skill 目录安装到 Codex CLI 或 OpenCode，也可以直接在仓库内通过 `PYTHONPATH=src python3 -m ...` 使用 CLI。
