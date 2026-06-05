# Skill Integration Reference

This repository is also a skill folder because it contains `SKILL.md` at the root. Install it by copying or symlinking the repository directory to a client-supported skill location.

The repository also contains two standalone skill folders under `tools/`:

- `tools/cpp-include-finder`
- `tools/cpp-include-analyzer`

Install those subdirectories separately when you want include lookup or include graph analysis skills.

## Codex CLI

Install globally:

```bash
mkdir -p ~/.codex/skills
ln -sfn /path/to/cpp-symbol-scout ~/.codex/skills/cpp-symbol-scout
ln -sfn /path/to/cpp-symbol-scout/tools/cpp-include-finder ~/.codex/skills/cpp-include-finder
ln -sfn /path/to/cpp-symbol-scout/tools/cpp-include-analyzer ~/.codex/skills/cpp-include-analyzer
```

Invoke it by asking Codex to use `$cpp-symbol-scout` for C/C++ symbol lookup or by describing a task that matches the skill description.
Invoke the include tools with `$cpp-include-finder` or `$cpp-include-analyzer`.

`agents/openai.yaml` is Codex-facing UI metadata. It is not required by the CLI runtime.

## OpenCode

OpenCode discovers skills from global and project-local directories. Global install:

```bash
mkdir -p ~/.config/opencode/skills
ln -sfn /path/to/cpp-symbol-scout ~/.config/opencode/skills/cpp-symbol-scout
ln -sfn /path/to/cpp-symbol-scout/tools/cpp-include-finder ~/.config/opencode/skills/cpp-include-finder
ln -sfn /path/to/cpp-symbol-scout/tools/cpp-include-analyzer ~/.config/opencode/skills/cpp-include-analyzer
```

Project-local install:

```bash
mkdir -p .opencode/skills
ln -sfn /path/to/cpp-symbol-scout .opencode/skills/cpp-symbol-scout
ln -sfn /path/to/cpp-symbol-scout/tools/cpp-include-finder .opencode/skills/cpp-include-finder
ln -sfn /path/to/cpp-symbol-scout/tools/cpp-include-analyzer .opencode/skills/cpp-include-analyzer
```

Claude-compatible and agent-compatible OpenCode paths are also supported:

```bash
mkdir -p ~/.claude/skills ~/.agents/skills
ln -sfn /path/to/cpp-symbol-scout ~/.claude/skills/cpp-symbol-scout
ln -sfn /path/to/cpp-symbol-scout ~/.agents/skills/cpp-symbol-scout
```

If OpenCode permissions are restrictive, allow this skill in `opencode.json`:

```json
{
  "permission": {
    "skill": {
      "cpp-symbol-scout": "allow"
    }
  }
}
```

## Portable CLI Use From A Skill

Agents should not assume the Python package is globally installed. Prefer this resolution order:

1. If `cpp-symbol-scout --version` works, use the installed command.
2. If the current repository has `src/cpp_symbol_scout`, run with `PYTHONPATH=src python3 -B -m cpp_symbol_scout`.
3. Otherwise locate the skill folder under Codex/OpenCode skill directories and run with `PYTHONPATH="$SCOUT/src"`.
4. Install editable with `python3 -m pip install -e "$SCOUT"` only when persistent CLI access is useful.
