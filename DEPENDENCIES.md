# 依赖安装手册

本文档说明本仓库七个 SKILL 的运行依赖和推荐安装方式。

## 基础依赖

所有 SKILL 都需要：

- Linux/macOS/WSL 等类 Unix 环境；
- Python 3.10 或更高版本；
- Git；
- 可访问目标 C/C++ 项目源码。

Ubuntu/Debian：

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv git
```

可选但推荐创建虚拟环境：

```bash
cd /home/cheng/workspace/cpp-symbol-scout
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
```

## clangd 相关依赖

以下工具基于 clangd 查询 C/C++ 语义信息，因此额外需要 clangd 和编译数据库：

- `cpp-symbol-scout`
- `services/cpp-clangd-service`
- `cpp-reference-finder`
- `cpp-call-hierarchy`
- `cpp-type-inspector`

- clangd；
- 目标项目的 `compile_commands.json` 或 `compile_flags.txt`。

Ubuntu/Debian 安装 clangd：

```bash
sudo apt update
sudo apt install -y clangd
clangd --version
```

如果系统提供带版本号的 clangd，也可以确认：

```bash
clangd-18 --version
```

## 准备编译数据库

CMake 项目：

```bash
cmake -S /path/to/project -B /path/to/project/build -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
```

Make 项目可使用 Bear：

```bash
sudo apt install -y bear
cd /path/to/project
bear -- make -j"$(nproc)"
```

SCons 项目如果支持 compiledb：

```bash
cd /path/to/project
scons compiledb=yes compiledb_gen_only=yes
```

生成完成后，应能在项目根目录或构建目录中看到：

```text
compile_commands.json
```

如果编译数据库不在项目根目录，使用 clangd 相关工具时传入：

```bash
--compile-commands-dir /path/to/project/build
```

## 安装 CLI

所有工具互相独立，可以按需安装。

```bash
cd /home/cheng/workspace/cpp-symbol-scout/skills/cpp-symbol-scout
python3 -m pip install -e .

cd /home/cheng/workspace/cpp-symbol-scout/skills/cpp-include-finder
python3 -m pip install -e .

cd /home/cheng/workspace/cpp-symbol-scout/skills/cpp-include-analyzer
python3 -m pip install -e .

cd /home/cheng/workspace/cpp-symbol-scout/skills/cpp-reference-finder
python3 -m pip install -e .

cd /home/cheng/workspace/cpp-symbol-scout/skills/cpp-call-hierarchy
python3 -m pip install -e .

cd /home/cheng/workspace/cpp-symbol-scout/skills/cpp-type-inspector
python3 -m pip install -e .

cd /home/cheng/workspace/cpp-symbol-scout/skills/cpp-diagnostic-context
python3 -m pip install -e .

cd /home/cheng/workspace/cpp-symbol-scout/services/cpp-clangd-service
python3 -m pip install -e .
```

也可以不安装，直接从各自 SKILL 目录运行：

```bash
PYTHONPATH=src python3 -B -m cpp_symbol_scout --help
PYTHONPATH=src python3 -B -m include_finder --help
PYTHONPATH=src python3 -B -m include_analyzer --help
PYTHONPATH=src python3 -B -m cpp_reference_finder --help
PYTHONPATH=src python3 -B -m cpp_call_hierarchy --help
PYTHONPATH=src python3 -B -m cpp_type_inspector --help
PYTHONPATH=src python3 -B -m cpp_diagnostic_context --help
PYTHONPATH=src python3 -B -m cpp_clangd_service --help
```

## 快速验证

验证 CLI：

```bash
cpp-symbol-scout --help
include-finder --help
include-analyzer --help
cpp-reference-finder --help
cpp-call-hierarchy --help
cpp-type-inspector --help
cpp-diagnostic-context --help
cpp-clangd-service --help
```

验证公共 clangd 服务和 `cpp-symbol-scout`：

```bash
cpp-clangd-service start --project /path/to/cpp/project --clangd /path/to/clangd --wait
cpp-symbol-scout query 'SymbolName' --project /path/to/cpp/project -n 1
cpp-clangd-service stop --project /path/to/cpp/project
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
```

## 说明

- `cpp-include-finder`、`cpp-include-analyzer`、`cpp-diagnostic-context` 只使用 Python 标准库，不依赖 clangd。
- clangd 相关工具默认复用 `cpp-clangd-service`；首次用于大型项目时，clangd 需要时间建立索引，重复查询和精确位置查询通常更稳定。
- 如果目标项目缺少编译数据库，clangd 相关工具的查询质量和稳定性会明显下降。
