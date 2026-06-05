# C++ AI Skills

这是一个面向 AI 辅助 C++ 大型项目开发的 SKILL 集合仓库。仓库当前包含三个相互独立的 SKILL，每个 SKILL 都有自己的 `SKILL.md`、Python CLI、`pyproject.toml` 和测试，不依赖其他 SKILL 才能运行。

## SKILL 清单

| SKILL | 目录 | 用途 |
| --- | --- | --- |
| `cpp-symbol-scout` | `skills/cpp-symbol-scout` | 基于 clangd daemon 快速查询 C/C++ 符号定义、实现位置和源码片段。 |
| `cpp-include-finder` | `skills/cpp-include-finder` | 查找类型、结构体、枚举、typedef、using alias 等声明所在头文件，并给出 include 建议。 |
| `cpp-include-analyzer` | `skills/cpp-include-analyzer` | 分析 C/C++ include 图、fan-in/fan-out、重复 include、未解析 include 和循环依赖。 |

Godot 工程只作为大型 C++ 项目的测试样本；这些 SKILL 不包含 Godot 专用逻辑。

## 仓库结构

```text
.
├── README.md
└── skills/
    ├── cpp-symbol-scout/
    │   ├── SKILL.md
    │   ├── agents/openai.yaml
    │   ├── pyproject.toml
    │   ├── src/
    │   ├── tests/
    │   ├── references/
    │   └── benchmarks/
    ├── cpp-include-finder/
    │   ├── SKILL.md
    │   ├── agents/openai.yaml
    │   ├── pyproject.toml
    │   ├── src/
    │   └── tests/
    └── cpp-include-analyzer/
        ├── SKILL.md
        ├── agents/openai.yaml
        ├── pyproject.toml
        ├── src/
        └── tests/
```

## 安装到 Codex CLI

```bash
REPO=/home/cheng/workspace/cpp-symbol-scout
mkdir -p ~/.codex/skills
ln -sfn "$REPO/skills/cpp-symbol-scout" ~/.codex/skills/cpp-symbol-scout
ln -sfn "$REPO/skills/cpp-include-finder" ~/.codex/skills/cpp-include-finder
ln -sfn "$REPO/skills/cpp-include-analyzer" ~/.codex/skills/cpp-include-analyzer
```

使用时可以显式指定：

```text
使用 $cpp-symbol-scout 查找 Foo::bar 的实现。
使用 $cpp-include-finder 查找 Node 应该 include 哪个头文件。
使用 $cpp-include-analyzer 分析 scene/main/node.h 的 include 影响。
```

## 安装到 OpenCode

全局安装：

```bash
REPO=/home/cheng/workspace/cpp-symbol-scout
mkdir -p ~/.config/opencode/skills
ln -sfn "$REPO/skills/cpp-symbol-scout" ~/.config/opencode/skills/cpp-symbol-scout
ln -sfn "$REPO/skills/cpp-include-finder" ~/.config/opencode/skills/cpp-include-finder
ln -sfn "$REPO/skills/cpp-include-analyzer" ~/.config/opencode/skills/cpp-include-analyzer
```

项目本地安装：

```bash
REPO=/home/cheng/workspace/cpp-symbol-scout
mkdir -p .opencode/skills
ln -sfn "$REPO/skills/cpp-symbol-scout" .opencode/skills/cpp-symbol-scout
ln -sfn "$REPO/skills/cpp-include-finder" .opencode/skills/cpp-include-finder
ln -sfn "$REPO/skills/cpp-include-analyzer" .opencode/skills/cpp-include-analyzer
```

如果 OpenCode 对 skill 加载有权限限制，需要在项目的 `opencode.json` 中允许对应 skill。

## CLI 最小用法

三个 CLI 都可以通过 editable install 安装，也可以直接用 `PYTHONPATH=src` 从各自 SKILL 目录运行。

`cpp-symbol-scout`：

```bash
cd /home/cheng/workspace/cpp-symbol-scout/skills/cpp-symbol-scout
PYTHONPATH=src python3 -B -m cpp_symbol_scout start --project /path/to/cpp/project --wait
PYTHONPATH=src python3 -B -m cpp_symbol_scout query 'Namespace::Class::method' --project /path/to/cpp/project --timeout 1 -n 1
PYTHONPATH=src python3 -B -m cpp_symbol_scout stop --project /path/to/cpp/project
```

`cpp-include-finder`：

```bash
cd /home/cheng/workspace/cpp-symbol-scout/skills/cpp-include-finder
PYTHONPATH=src python3 -B -m include_finder find 'TypeName' --project /path/to/cpp/project -n 5
```

`cpp-include-analyzer`：

```bash
cd /home/cheng/workspace/cpp-symbol-scout/skills/cpp-include-analyzer
PYTHONPATH=src python3 -B -m include_analyzer analyze --project /path/to/cpp/project --limit 20
```

## 验证

验证 SKILL 元数据：

```bash
python3 /home/cheng/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/cpp-symbol-scout
python3 /home/cheng/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/cpp-include-finder
python3 /home/cheng/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/cpp-include-analyzer
```

运行单元测试：

```bash
cd /home/cheng/workspace/cpp-symbol-scout/skills/cpp-symbol-scout
PYTHONPATH=src python3 -B -m unittest discover -s tests -v

cd /home/cheng/workspace/cpp-symbol-scout/skills/cpp-include-finder
PYTHONPATH=src python3 -B -m unittest discover -s tests -v

cd /home/cheng/workspace/cpp-symbol-scout/skills/cpp-include-analyzer
PYTHONPATH=src python3 -B -m unittest discover -s tests -v
```

## 设计原则

- 三个 SKILL 独立演进，避免做成一个超大工具。
- 每个 SKILL 都优先面向 AI Agent 的稳定、可重复工作流。
- CLI 使用 Python 标准库为主，便于在不同 C++ 项目中直接运行。
- 大型项目场景下优先复用索引、daemon 或缓存，减少 AI 反复全文搜索的成本。
