# cpp-symbol-scout

`cpp-symbol-scout` is a Python CLI for fast C++ symbol lookup backed by a persistent
`clangd` process. It accepts class, function, method, and other symbol names and
returns candidate definition locations plus source snippets.

The intended fast path is:

1. start one daemon per project;
2. let `clangd` build or load its background index;
3. run many cheap `query` commands against the already initialized daemon.

The 1 second target applies to warm queries after the daemon is running and the
project index is available. First startup and first indexing of a large project
can take much longer because that work is done by `clangd`.

## Requirements

- Python 3.10 or newer.
- `clangd` installed and available in `PATH`, available as a versioned command
  such as `clangd-18`, or passed with `--clangd`.
- A usable `compile_commands.json` or `compile_flags.txt`.

For Godot, generate a compilation database first. If the file is not in the
project root, pass its directory with `--compile-commands-dir`.

This repository defaults to `/home/cheng/godotengine/godot-master` for local
testing. On this machine, `clangd-18` is installed and Godot's
`compile_commands.json` has been generated in the project root.

## Godot Setup

Godot can generate its compilation database through SCons:

```bash
cd /home/cheng/godotengine/godot-master
scons compiledb=yes compiledb_gen_only=yes platform=linuxbsd target=editor dev_build=yes tests=no -j2
```

If `scons` is not installed system-wide, create a local virtual environment:

```bash
cd /home/cheng/workspace/cpp-symbol-scout
python3 -m venv .venv
.venv/bin/python -m pip install SCons
cd /home/cheng/godotengine/godot-master
/home/cheng/workspace/cpp-symbol-scout/.venv/bin/scons compiledb=yes compiledb_gen_only=yes platform=linuxbsd target=editor dev_build=yes tests=no -j2
```

## Install

```bash
python3 -m pip install -e .
```

## Usage

Start the daemon:

```bash
cpp-symbol-scout start --project /home/cheng/godotengine/godot-master --wait
```

Query a symbol:

```bash
cpp-symbol-scout query --project /home/cheng/godotengine/godot-master Node
cpp-symbol-scout query --project /home/cheng/godotengine/godot-master EditorNode::save_scene
```

Print JSON:

```bash
cpp-symbol-scout query Node --json
```

Print only the first source snippet:

```bash
cpp-symbol-scout query EditorNode::save_scene --source-only
```

Show daemon state:

```bash
cpp-symbol-scout status --project /home/cheng/godotengine/godot-master
```

Stop the daemon:

```bash
cpp-symbol-scout stop --project /home/cheng/godotengine/godot-master
```

## Commands

- `start`: starts a background daemon. Use `--foreground` for debugging.
- `query`: sends a symbol lookup request to the daemon.
- `status`: prints daemon status, socket path, log path, and cache size.
- `stop`: stops the daemon for the selected project.

Common options:

- `--project`: project root. Defaults to `/home/cheng/godotengine/godot-master`.
- `--clangd`: path to `clangd`; defaults to `CLANGD` or `clangd`.
- `--compile-commands-dir`: directory containing `compile_commands.json`.
- `--allow-missing-compile-db`: useful for small experiments, not recommended for
  large real projects.

## How It Works

The CLI talks to a local daemon over `127.0.0.1`. The daemon owns a single
initialized `clangd` process, issues LSP requests such as `workspace/symbol`,
`textDocument/documentSymbol`, `textDocument/definition`, and
`textDocument/implementation`, then extracts a complete class/function snippet
from the source file.

Repeated queries are cached in daemon memory. Restarting the daemon clears this
Python-side cache, while `clangd` may still reuse its own background index files.
