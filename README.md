# cpp-symbol-scout 使用说明

cpp-symbol-scout 是一个基于 clangd 的 C++ 符号查询 CLI 工具。它可以通过类名、函数名、方法名等符号名称，查询定义位置并返回完整源码片段。

本工具的推荐使用方式：

1. 为 C++ 项目准备 `compile_commands.json`。
2. 启动一个常驻 `cpp-symbol-scout` daemon。
3. 后续查询都通过 CLI 连接 daemon，复用同一个 clangd 进程和索引缓存。

## 性能说明

1 秒内返回结果的前提是：

- daemon 已经启动；
- clangd 已完成初始化；
- 项目的 background index 已经构建，或相关文件已经被查询缓存；
- 不是首次启动大型项目索引。

首次启动 Godot 这种大型 C++ 项目时，clangd 会在后台索引大量文件，可能持续数分钟，CPU 占用较高，这是正常现象。索引完成后，常用符号查询会明显变快。

## 当前机器状态

当前机器已确认：

- `clangd-18` 已安装，可执行文件为 `/usr/bin/clangd-18`。
- Godot 项目路径为 `/home/cheng/godotengine/godot-master`。
- Godot 的 `compile_commands.json` 已生成：
  `/home/cheng/godotengine/godot-master/compile_commands.json`
- 如需重新生成 Godot 编译数据库，需要系统安装 SCons，或在本仓库创建本地 `.venv` 后安装 SCons。

## 安装本工具

在 `/home/cheng/workspace/cpp-symbol-scout` 下执行：

```bash
python3 -m pip install -e .
```

如果不想安装到 Python 环境，也可以直接用 `PYTHONPATH` 运行：

```bash
PYTHONPATH=src python3 -B -m cpp_symbol_scout --help
```

## 生成 Godot 编译数据库

如果 Godot 的 `compile_commands.json` 不存在，先生成它。

进入 Godot 项目：

```bash
cd /home/cheng/godotengine/godot-master
```

如果系统已有 `scons`，可以执行：

```bash
scons compiledb=yes compiledb_gen_only=yes platform=linuxbsd target=editor dev_build=yes tests=no -j2
```

如果系统没有 `scons`，可以在本仓库创建本地虚拟环境：

```bash
cd /home/cheng/workspace/cpp-symbol-scout
python3 -m venv .venv
.venv/bin/python -m pip install SCons
```

然后再生成 Godot 编译数据库：

```bash
cd /home/cheng/godotengine/godot-master
/home/cheng/workspace/cpp-symbol-scout/.venv/bin/scons compiledb=yes compiledb_gen_only=yes platform=linuxbsd target=editor dev_build=yes tests=no -j2
```

生成成功后应看到：

```text
/home/cheng/godotengine/godot-master/compile_commands.json
```

## 启动 daemon

在 `/home/cheng/workspace/cpp-symbol-scout` 下执行：

```bash
PYTHONPATH=src python3 -B -m cpp_symbol_scout start --project /home/cheng/godotengine/godot-master --wait
```

启动成功时会看到类似：

```text
daemon ready: 127.0.0.1:55490
```

查看 daemon 状态：

```bash
PYTHONPATH=src python3 -B -m cpp_symbol_scout status --project /home/cheng/godotengine/godot-master
```

停止 daemon：

```bash
PYTHONPATH=src python3 -B -m cpp_symbol_scout stop --project /home/cheng/godotengine/godot-master
```

## 查询符号

查询类：

```bash
PYTHONPATH=src python3 -B -m cpp_symbol_scout query Node --project /home/cheng/godotengine/godot-master --timeout 1 -n 1
```

查询另一个类：

```bash
PYTHONPATH=src python3 -B -m cpp_symbol_scout query EditorNode --project /home/cheng/godotengine/godot-master --timeout 1 -n 1
```

查询方法名：

```bash
PYTHONPATH=src python3 -B -m cpp_symbol_scout query _save_scene --project /home/cheng/godotengine/godot-master --timeout 4 -n 2
```

只输出第一个结果的源码片段：

```bash
PYTHONPATH=src python3 -B -m cpp_symbol_scout query EditorNode --project /home/cheng/godotengine/godot-master --source-only
```

输出 JSON：

```bash
PYTHONPATH=src python3 -B -m cpp_symbol_scout query Node --project /home/cheng/godotengine/godot-master --json
```

## 不使用 daemon 的直接查询模式

direct 模式会在当前进程临时启动 clangd，适合调试安装和 LSP 链路：

```bash
PYTHONPATH=src python3 -B -m cpp_symbol_scout query Node --direct --project /home/cheng/godotengine/godot-master --timeout 8 -n 1
```

注意：direct 模式每次都要启动 clangd，不适合追求 1 秒内响应的大型项目查询。

## 常用参数

`--project`

C++ 项目根目录。默认是 `/home/cheng/godotengine/godot-master`。

`--clangd`

clangd 可执行文件路径。不传时工具会自动查找 `clangd`、`clangd-18` 等常见命令。

`--compile-commands-dir`

`compile_commands.json` 或 `compile_flags.txt` 所在目录。如果文件在项目根目录，一般不需要传。

`--timeout`

单次查询的 daemon 侧预算，单位为秒。

`-n` / `--limit`

返回候选数量。

`--json`

输出 JSON，便于其他脚本消费。

`--source-only`

只输出第一个结果的源码片段。

## 实现概要

cpp-symbol-scout daemon 会持有一个长期运行的 clangd 进程，并通过 LSP 请求完成查询。

主要使用的 LSP 能力包括：

- `workspace/symbol`
- `textDocument/documentSymbol`
- `textDocument/definition`
- `textDocument/implementation`

当 clangd 的 background index 尚未完成时，工具会使用 `documentSymbol` 作为 fallback，优先保证能查到当前符号的定义片段。重复查询会缓存在 daemon 内存中。

## 验证命令

运行单元测试：

```bash
PYTHONPATH=src python3 -B -m unittest discover -s tests -v
```

当前已验证：

- `Node` 查询可以返回 `scene/main/node.h` 中的完整 `class Node` 定义。
- `EditorNode` 查询可以返回 `editor/editor_node.h` 中的完整 `class EditorNode` 定义。
- 缓存后的 `Node` / `EditorNode` 查询可在 1 秒内返回。
