# Troubleshooting Reference

## clangd Is Missing

Check:

```bash
clangd --version || clangd-18 --version || clangd-17 --version
```

Install clangd with the system package manager, or pass the executable explicitly:

```bash
cpp-symbol-scout start --project "$PROJECT_ROOT" --clangd /path/to/clangd --wait
```

## Compile Database Is Missing

The tool requires `compile_commands.json` or `compile_flags.txt` by default. Generate one with the project's build system, then pass `--compile-commands-dir` if the file is not in the project root.

Use `--allow-missing-compile-db` only for degraded debugging, not for reliable symbol lookup.

## Daemon Fails To Become Ready

Run:

```bash
cpp-symbol-scout status --project "$PROJECT_ROOT"
```

If status cannot connect, start with a longer wait:

```bash
cpp-symbol-scout start --project "$PROJECT_ROOT" --wait --wait-timeout 30
```

The start command prints the daemon log path. Inspect that log for clangd startup errors, invalid compile database paths, or permission issues.

## No Results

Try these in order:

```bash
cpp-symbol-scout query 'ExactSymbolName' --project "$PROJECT_ROOT" --timeout 4 -n 5
cpp-symbol-scout query 'Namespace::Class::method' --project "$PROJECT_ROOT" --timeout 4 -n 5
cpp-symbol-scout query 'SymbolName' --project "$PROJECT_ROOT" --direct --timeout 8 -n 5
```

Also confirm the queried symbol exists in files covered by the compile database. Header-only symbols and generated files may require opening or indexing the relevant file once.

## Queries Are Slower Than 1 Second

Common causes:

- clangd is still building the background index;
- the first query opened a large translation unit;
- the symbol name is too broad, causing many candidates;
- the compile database points at stale or missing build paths;
- direct mode is being used.

Use the daemon, prefer qualified names, and retry after the first successful lookup. For very large projects, the first indexing pass can take minutes.
