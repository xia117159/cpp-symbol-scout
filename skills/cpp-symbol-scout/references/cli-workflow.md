# CLI Workflow Reference

## Preconditions

- Python 3.10 or newer.
- `clangd` on `PATH`, or pass `--clangd /path/to/clangd`.
- A C/C++ project with `compile_commands.json` or `compile_flags.txt`.

Generate a compile database with common build systems:

```bash
# CMake
cmake -S . -B build -DCMAKE_EXPORT_COMPILE_COMMANDS=ON

# Make or other compiler-invoking builds when Bear is available
bear -- make -j"$(nproc)"

# SCons projects that support compiledb generation
scons compiledb=yes compiledb_gen_only=yes
```

If the database is outside the project root, pass the directory:

```bash
cpp-clangd-service start --project "$PROJECT_ROOT" --compile-commands-dir "$PROJECT_ROOT/build" --wait
```

## Service Lifecycle

Start once per project root:

```bash
cpp-clangd-service start --project "$PROJECT_ROOT" --wait
```

Check readiness and cache size:

```bash
cpp-clangd-service status --project "$PROJECT_ROOT"
```

Stop when finished:

```bash
cpp-clangd-service stop --project "$PROJECT_ROOT"
```

`cpp-symbol-scout start/status/stop` also forwards to `cpp-clangd-service` for compatibility. The service keeps one clangd process alive, so repeated queries reuse clangd initialization, background index state, and the tool's in-memory cache.

## Query Patterns

Find a class or struct:

```bash
cpp-symbol-scout query 'ClassName' --project "$PROJECT_ROOT" --timeout 1 -n 1
```

Find a method or function:

```bash
cpp-symbol-scout query 'method_name' --project "$PROJECT_ROOT" --timeout 4 -n 5
```

Prefer qualified names when the project has many overloads or common method names:

```bash
cpp-symbol-scout query 'Namespace::ClassName::method_name' --project "$PROJECT_ROOT" -n 3
```

Return only the first source snippet:

```bash
cpp-symbol-scout query 'ClassName' --project "$PROJECT_ROOT" --source-only
```

Return machine-readable results:

```bash
cpp-symbol-scout query 'ClassName' --project "$PROJECT_ROOT" --json
```

Each human-readable result includes symbol kind, full name, resolution mode, elapsed time, file path, line, column, and the extracted snippet.

## Performance Target

The 1-second target applies after:

- the service is already running;
- clangd initialization has completed;
- the background index is warm enough for the queried symbol, or the relevant file has already been opened;
- the project compile database is valid.

For first queries on very large repositories, use a longer timeout once, then retry with `--timeout 1`.
