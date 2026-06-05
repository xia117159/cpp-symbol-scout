# 独立 C++ 工具

本目录存放与 `cpp-symbol-scout` 并列的独立 CLI 工具。它们共享同一个 git 仓库，但不是同一个 Python 包，也不依赖 `cpp-symbol-scout`。

## 当前工具

- `cpp-include-finder`：扫描 C++ 头文件声明，快速查找类型、枚举、typedef、using alias 对应的推荐 include。
- `cpp-include-analyzer`：扫描 C++ include 图，分析 fan-in、fan-out、重复 include、未解析 include、热点头文件和 include 循环。

## 与 SKILL 的关系

当前这两个目录是独立 CLI 工具，不是 SKILL。若后续要让 Codex CLI 或 OPENCODE 按“技能”方式自动调用，可以在各自目录或仓库层增加 `SKILL.md`，描述触发条件、输入输出和推荐命令。
