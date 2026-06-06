# C++ AI Skills

这是一个面向 AI 辅助 C++ 大型项目开发的 SKILL 集合仓库。仓库当前包含八个相互独立的 SKILL，每个 SKILL 都有自己的 `SKILL.md`、Python CLI、`pyproject.toml` 和测试，不依赖其他 SKILL 才能运行。

## SKILL 清单

| SKILL | 目录 | 用途 |
| --- | --- | --- |
| `cpp-symbol-scout` | `skills/cpp-symbol-scout` | 基于公共 `cpp-clangd-service` 快速查询 C/C++ 符号定义、实现位置和源码片段。 |
| `cpp-include-finder` | `skills/cpp-include-finder` | 查找类型、结构体、枚举、typedef、using alias 等声明所在头文件，并给出 include 建议。 |
| `cpp-include-analyzer` | `skills/cpp-include-analyzer` | 分析 C/C++ include 图、fan-in/fan-out、重复 include、未解析 include 和循环依赖。 |
| `cpp-reference-finder` | `skills/cpp-reference-finder` | 基于 clangd 查询符号真实引用位置，适合重构前影响面分析。 |
| `cpp-call-hierarchy` | `skills/cpp-call-hierarchy` | 基于 clangd 查询 incoming calls，并在必要时静态提取 outgoing 调用候选。 |
| `cpp-type-inspector` | `skills/cpp-type-inspector` | 基于 clangd hover/definition/typeDefinition 查看表达式、变量、函数和类类型。 |
| `cpp-diagnostic-context` | `skills/cpp-diagnostic-context` | 解析 Clang/GCC 编译日志，提取错误位置、include 栈、模板栈和源码上下文。 |
| `cpp-static-checker` | `skills/cpp-static-checker` | 基于 clang-tidy 对 C/C++ 文件、git 改动或日志做静态检查和 AI 友好诊断摘要。 |

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
    ├── cpp-include-analyzer/
    ├── cpp-reference-finder/
    ├── cpp-call-hierarchy/
    ├── cpp-type-inspector/
    ├── cpp-diagnostic-context/
    └── cpp-static-checker/
└── services/
    └── cpp-clangd-service/
└── libraries/
    └── cpp-build-log-filter/
```

`services/cpp-clangd-service` 不是 SKILL，它是常驻 clangd 服务进程。`cpp-symbol-scout`、`cpp-reference-finder`、`cpp-call-hierarchy`、`cpp-type-inspector` 默认连接该服务，避免每次 CLI 调用都重新初始化 clangd。

`libraries/cpp-build-log-filter` 不是 SKILL，它是纯 Python 工具库：输入整段 CMake/Make/C++ 构建日志文本，输出过滤后的关键信息文本，便于 AI Agent 降低编译输出的上下文占用。

## 安装到 Codex CLI

依赖安装请先阅读 [DEPENDENCIES.md](DEPENDENCIES.md)。

```bash
REPO=/home/cheng/workspace/cpp-symbol-scout
mkdir -p ~/.codex/skills
ln -sfn "$REPO/skills/cpp-symbol-scout" ~/.codex/skills/cpp-symbol-scout
ln -sfn "$REPO/skills/cpp-include-finder" ~/.codex/skills/cpp-include-finder
ln -sfn "$REPO/skills/cpp-include-analyzer" ~/.codex/skills/cpp-include-analyzer
ln -sfn "$REPO/skills/cpp-reference-finder" ~/.codex/skills/cpp-reference-finder
ln -sfn "$REPO/skills/cpp-call-hierarchy" ~/.codex/skills/cpp-call-hierarchy
ln -sfn "$REPO/skills/cpp-type-inspector" ~/.codex/skills/cpp-type-inspector
ln -sfn "$REPO/skills/cpp-diagnostic-context" ~/.codex/skills/cpp-diagnostic-context
ln -sfn "$REPO/skills/cpp-static-checker" ~/.codex/skills/cpp-static-checker
```

使用时可以显式指定：

```text
使用 $cpp-symbol-scout 查找 Foo::bar 的实现。
使用 $cpp-include-finder 查找 Node 应该 include 哪个头文件。
使用 $cpp-include-analyzer 分析 scene/main/node.h 的 include 影响。
使用 $cpp-reference-finder 查找 Node::add_child 的真实引用。
使用 $cpp-call-hierarchy 分析 Node::add_child 的调用层级。
使用 $cpp-type-inspector 查看某个 C++ 表达式的精确类型。
使用 $cpp-diagnostic-context 分析这段 C++ 编译错误日志。
使用 $cpp-static-checker 对这次 C++ 改动运行 clang-tidy 静态检查。
```

## 安装到 OpenCode

全局安装：

```bash
REPO=/home/cheng/workspace/cpp-symbol-scout
mkdir -p ~/.config/opencode/skills
ln -sfn "$REPO/skills/cpp-symbol-scout" ~/.config/opencode/skills/cpp-symbol-scout
ln -sfn "$REPO/skills/cpp-include-finder" ~/.config/opencode/skills/cpp-include-finder
ln -sfn "$REPO/skills/cpp-include-analyzer" ~/.config/opencode/skills/cpp-include-analyzer
ln -sfn "$REPO/skills/cpp-reference-finder" ~/.config/opencode/skills/cpp-reference-finder
ln -sfn "$REPO/skills/cpp-call-hierarchy" ~/.config/opencode/skills/cpp-call-hierarchy
ln -sfn "$REPO/skills/cpp-type-inspector" ~/.config/opencode/skills/cpp-type-inspector
ln -sfn "$REPO/skills/cpp-diagnostic-context" ~/.config/opencode/skills/cpp-diagnostic-context
ln -sfn "$REPO/skills/cpp-static-checker" ~/.config/opencode/skills/cpp-static-checker
```

项目本地安装：

```bash
REPO=/home/cheng/workspace/cpp-symbol-scout
mkdir -p .opencode/skills
ln -sfn "$REPO/skills/cpp-symbol-scout" .opencode/skills/cpp-symbol-scout
ln -sfn "$REPO/skills/cpp-include-finder" .opencode/skills/cpp-include-finder
ln -sfn "$REPO/skills/cpp-include-analyzer" .opencode/skills/cpp-include-analyzer
ln -sfn "$REPO/skills/cpp-reference-finder" .opencode/skills/cpp-reference-finder
ln -sfn "$REPO/skills/cpp-call-hierarchy" .opencode/skills/cpp-call-hierarchy
ln -sfn "$REPO/skills/cpp-type-inspector" .opencode/skills/cpp-type-inspector
ln -sfn "$REPO/skills/cpp-diagnostic-context" .opencode/skills/cpp-diagnostic-context
ln -sfn "$REPO/skills/cpp-static-checker" .opencode/skills/cpp-static-checker
```

如果 OpenCode 对 skill 加载有权限限制，需要在项目的 `opencode.json` 中允许对应 skill。

## CLI 最小用法

所有 CLI 都可以通过 editable install 安装，也可以直接用 `PYTHONPATH=src` 从各自 SKILL 目录运行。

`cpp-symbol-scout`：

```bash
cd /home/cheng/workspace/cpp-symbol-scout/services/cpp-clangd-service
PYTHONPATH=src python3 -B -m cpp_clangd_service start --project /path/to/cpp/project --clangd /usr/bin/clangd-18 --wait

cd /home/cheng/workspace/cpp-symbol-scout/skills/cpp-symbol-scout
PYTHONPATH=src python3 -B -m cpp_symbol_scout query 'Namespace::Class::method' --project /path/to/cpp/project --timeout 1 -n 1

PYTHONPATH=src python3 -B -m cpp_symbol_scout members 'Namespace::Class' --project /path/to/cpp/project --access public --json
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

`cpp-reference-finder`：

```bash
cd /home/cheng/workspace/cpp-symbol-scout/services/cpp-clangd-service
PYTHONPATH=src python3 -B -m cpp_clangd_service start --project /path/to/cpp/project --clangd /usr/bin/clangd-18 --wait

cd /home/cheng/workspace/cpp-symbol-scout/skills/cpp-reference-finder
PYTHONPATH=src python3 -B -m cpp_reference_finder find 'Namespace::Class::method' --project /path/to/cpp/project --json
```

`cpp-call-hierarchy`：

```bash
cd /home/cheng/workspace/cpp-symbol-scout/skills/cpp-call-hierarchy
PYTHONPATH=src python3 -B -m cpp_call_hierarchy find 'Namespace::Class::method' --project /path/to/cpp/project --incoming --outgoing
```

`cpp-type-inspector`：

```bash
cd /home/cheng/workspace/cpp-symbol-scout/skills/cpp-type-inspector
PYTHONPATH=src python3 -B -m cpp_type_inspector at path/to/file.cpp --line 120 --column 18 --project /path/to/cpp/project --json
```

`cpp-diagnostic-context`：

```bash
cd /home/cheng/workspace/cpp-symbol-scout/skills/cpp-diagnostic-context
PYTHONPATH=src python3 -B -m cpp_diagnostic_context analyze build.log --project /path/to/cpp/project
```

`cpp-static-checker`：

```bash
cd /home/cheng/workspace/cpp-symbol-scout/skills/cpp-static-checker
PYTHONPATH=src python3 -B -m cpp_static_checker check --project /path/to/cpp/project --changed --json -n 50
```

## 验证

验证 SKILL 元数据：

```bash
python3 /home/cheng/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/cpp-symbol-scout
python3 /home/cheng/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/cpp-include-finder
python3 /home/cheng/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/cpp-include-analyzer
python3 /home/cheng/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/cpp-reference-finder
python3 /home/cheng/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/cpp-call-hierarchy
python3 /home/cheng/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/cpp-type-inspector
python3 /home/cheng/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/cpp-diagnostic-context
python3 /home/cheng/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/cpp-static-checker
```

运行单元测试：

```bash
cd /home/cheng/workspace/cpp-symbol-scout/skills/cpp-symbol-scout
PYTHONPATH=src python3 -B -m unittest discover -s tests -v

cd /home/cheng/workspace/cpp-symbol-scout/skills/cpp-include-finder
PYTHONPATH=src python3 -B -m unittest discover -s tests -v

cd /home/cheng/workspace/cpp-symbol-scout/skills/cpp-include-analyzer
PYTHONPATH=src python3 -B -m unittest discover -s tests -v

cd /home/cheng/workspace/cpp-symbol-scout/skills/cpp-reference-finder
PYTHONPATH=src python3 -B -m unittest discover -s tests -v

cd /home/cheng/workspace/cpp-symbol-scout/skills/cpp-call-hierarchy
PYTHONPATH=src python3 -B -m unittest discover -s tests -v

cd /home/cheng/workspace/cpp-symbol-scout/skills/cpp-type-inspector
PYTHONPATH=src python3 -B -m unittest discover -s tests -v

cd /home/cheng/workspace/cpp-symbol-scout/skills/cpp-diagnostic-context
PYTHONPATH=src python3 -B -m unittest discover -s tests -v

cd /home/cheng/workspace/cpp-symbol-scout/skills/cpp-static-checker
PYTHONPATH=src python3 -B -m unittest discover -s tests -v
```

## 设计原则

- 各 SKILL 独立演进，避免做成一个超大工具。
- 每个 SKILL 都优先面向 AI Agent 的稳定、可重复工作流。
- CLI 使用 Python 标准库为主，便于在不同 C++ 项目中直接运行。
- 大型项目场景下优先复用 `cpp-clangd-service`、clangd 索引和服务内缓存，减少 AI 反复全文搜索的成本。
