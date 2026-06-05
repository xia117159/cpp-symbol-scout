# cpp-symbol-scout

cpp-symbol-scout 是一个基于 clangd 的 C/C++ 符号查询工具，同时也是一个可复用的 AI Agent Skill。它可以通过类名、函数名、方法名、限定名等输入，快速定位定义或实现位置，并返回完整源码片段。

这个仓库包含两部分：

- Python CLI：`cpp-symbol-scout`，通过常驻 daemon 复用 clangd 进程和索引缓存。
- 通用 Skill：根目录 `SKILL.md`，可安装到 Codex CLI 或 OpenCode 的技能目录中。

仓库还包含两个独立的 C++ include 工具 Skill，位于 `tools/`：

- `tools/cpp-include-finder`：查找类型、枚举、typedef、using alias 对应的推荐 include。
- `tools/cpp-include-analyzer`：分析 include 图、fan-in/fan-out、重复 include、未解析 include 和 include 循环。

## 方案概览

推荐工作流如下：

1. 为目标 C/C++ 项目准备 `compile_commands.json` 或 `compile_flags.txt`。
2. 启动 `cpp-symbol-scout` daemon。
3. 通过 CLI 或 AI Agent Skill 发起符号查询。
4. 对同一项目反复查询时复用同一个 clangd 进程，降低初始化和索引成本。

1 秒内返回结果的前提是 daemon 已启动、clangd 已初始化，并且 background index 已经覆盖相关符号。首次索引大型项目时可能需要数分钟，这是 clangd 的正常行为。

## 安装 CLI

在仓库根目录执行：

```bash
python3 -m pip install -e .
```

也可以不安装，直接通过 `PYTHONPATH` 运行：

```bash
PYTHONPATH=src python3 -B -m cpp_symbol_scout --help
```

确认 clangd 可用：

```bash
clangd --version
```

如果系统安装的是带版本号的命令，也可以使用：

```bash
clangd-18 --version
```

## 准备编译数据库

CMake 项目：

```bash
cmake -S . -B build -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
```

Make 或其他编译命令可通过 Bear 生成：

```bash
bear -- make -j"$(nproc)"
```

SCons 项目如果支持 compiledb：

```bash
scons compiledb=yes compiledb_gen_only=yes
```

如果编译数据库不在项目根目录，启动 daemon 时传入：

```bash
cpp-symbol-scout start --project /path/to/project --compile-commands-dir /path/to/project/build --wait
```

## 使用 CLI

启动 daemon：

```bash
cpp-symbol-scout start --project /path/to/project --wait
```

查看状态：

```bash
cpp-symbol-scout status --project /path/to/project
```

查询类或结构体：

```bash
cpp-symbol-scout query 'ClassName' --project /path/to/project --timeout 1 -n 1
```

查询函数或方法：

```bash
cpp-symbol-scout query 'method_name' --project /path/to/project --timeout 4 -n 5
```

查询限定名：

```bash
cpp-symbol-scout query 'Namespace::ClassName::method_name' --project /path/to/project -n 3
```

只输出第一个结果的源码片段：

```bash
cpp-symbol-scout query 'ClassName' --project /path/to/project --source-only
```

输出 JSON：

```bash
cpp-symbol-scout query 'ClassName' --project /path/to/project --json
```

停止 daemon：

```bash
cpp-symbol-scout stop --project /path/to/project
```

直接查询模式用于排查 clangd 链路，不适合性能敏感查询：

```bash
cpp-symbol-scout query 'ClassName' --direct --project /path/to/project --timeout 8 -n 1
```

## 安装为 Codex CLI Skill

将本仓库软链接到 Codex CLI 的技能目录：

```bash
mkdir -p ~/.codex/skills
ln -sfn /home/cheng/workspace/cpp-symbol-scout ~/.codex/skills/cpp-symbol-scout
```

使用时可以在请求中显式写：

```text
使用 $cpp-symbol-scout 帮我查找 Foo::bar 的实现位置和源码片段。
```

也可以直接描述 C/C++ 符号查询任务，由技能描述触发。

如果还要安装 include 工具 Skill，将各自子目录作为独立 Skill 链接：

```bash
ln -sfn /home/cheng/workspace/cpp-symbol-scout/tools/cpp-include-finder ~/.codex/skills/cpp-include-finder
ln -sfn /home/cheng/workspace/cpp-symbol-scout/tools/cpp-include-analyzer ~/.codex/skills/cpp-include-analyzer
```

## 安装为 OpenCode Skill

OpenCode 支持从项目或全局目录加载 `SKILL.md`。全局安装：

```bash
mkdir -p ~/.config/opencode/skills
ln -sfn /home/cheng/workspace/cpp-symbol-scout ~/.config/opencode/skills/cpp-symbol-scout
```

项目本地安装：

```bash
mkdir -p .opencode/skills
ln -sfn /home/cheng/workspace/cpp-symbol-scout .opencode/skills/cpp-symbol-scout
```

如果 OpenCode 权限配置限制了技能加载，在 `opencode.json` 中允许该技能：

```json
{
  "permission": {
    "skill": {
      "cpp-symbol-scout": "allow"
    }
  }
}
```

## Skill 内容结构

核心入口：

- `SKILL.md`：技能元数据和核心工作流。
- `agents/openai.yaml`：Codex 侧展示元数据。
- `references/cli-workflow.md`：CLI、daemon、查询方式细节。
- `references/integration.md`：Codex CLI 与 OpenCode 安装方式。
- `references/troubleshooting.md`：clangd、编译数据库、性能和无结果排查。
- `tools/cpp-include-finder/SKILL.md`：include 查找 Skill。
- `tools/cpp-include-analyzer/SKILL.md`：include 图分析 Skill。

AI Agent 使用该 Skill 时，会优先使用已安装的 `cpp-symbol-scout` 命令；如果命令不存在，则通过本仓库的 `PYTHONPATH=src python3 -B -m cpp_symbol_scout` 运行。

## 常用参数

`--project`

C/C++ 项目根目录。默认是当前目录，也可以通过环境变量 `CPP_CLANGD_PROJECT` 设置。

`--clangd`

clangd 可执行文件路径。不传时会自动查找 `clangd`、`clangd-18` 等常见命令。

`--compile-commands-dir`

`compile_commands.json` 或 `compile_flags.txt` 所在目录。如果文件在项目根目录，一般不需要传。

`--timeout`

单次查询的 daemon 侧预算，单位为秒。

`-n` / `--limit`

返回候选数量。

`--json`

输出 JSON，便于脚本或 Agent 消费。

`--source-only`

只输出第一个结果的源码片段。

`--direct`

临时启动 clangd 执行一次查询，主要用于调试。

## 实现概要

daemon 会持有一个长期运行的 clangd 进程，并通过 LSP 请求完成查询。主要使用的 LSP 能力包括：

- `workspace/symbol`
- `textDocument/documentSymbol`
- `textDocument/definition`
- `textDocument/implementation`

当 clangd 的 background index 尚未完成时，工具会使用 `documentSymbol` 作为 fallback。重复查询结果会缓存在 daemon 内存中。

## 验证

运行单元测试：

```bash
PYTHONPATH=src python3 -B -m unittest discover -s tests -v
```

验证 Skill frontmatter：

```bash
python3 /home/cheng/.codex/skills/.system/skill-creator/scripts/quick_validate.py .
python3 /home/cheng/.codex/skills/.system/skill-creator/scripts/quick_validate.py tools/cpp-include-finder
python3 /home/cheng/.codex/skills/.system/skill-creator/scripts/quick_validate.py tools/cpp-include-analyzer
```
