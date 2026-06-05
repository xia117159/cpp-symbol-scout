# Skill Integration Reference

This repository is a skill collection. Install each skill directory separately:

- `skills/cpp-symbol-scout`
- `skills/cpp-include-finder`
- `skills/cpp-include-analyzer`

`cpp-symbol-scout` is independent from the include skills. Install the include skills only when the agent needs header discovery or include graph analysis.

## Codex CLI

Install globally:

```bash
REPO=/path/to/cpp-symbol-scout
mkdir -p ~/.codex/skills
ln -sfn "$REPO/skills/cpp-symbol-scout" ~/.codex/skills/cpp-symbol-scout
ln -sfn "$REPO/skills/cpp-include-finder" ~/.codex/skills/cpp-include-finder
ln -sfn "$REPO/skills/cpp-include-analyzer" ~/.codex/skills/cpp-include-analyzer
```

Invoke explicitly with `$cpp-symbol-scout`, `$cpp-include-finder`, or `$cpp-include-analyzer`, or describe a task that matches the skill descriptions.

`agents/openai.yaml` is Codex-facing UI metadata. It is not required by the CLI runtime.

## OpenCode

OpenCode discovers skills from global and project-local directories. Global install:

```bash
REPO=/path/to/cpp-symbol-scout
mkdir -p ~/.config/opencode/skills
ln -sfn "$REPO/skills/cpp-symbol-scout" ~/.config/opencode/skills/cpp-symbol-scout
ln -sfn "$REPO/skills/cpp-include-finder" ~/.config/opencode/skills/cpp-include-finder
ln -sfn "$REPO/skills/cpp-include-analyzer" ~/.config/opencode/skills/cpp-include-analyzer
```

Project-local install:

```bash
REPO=/path/to/cpp-symbol-scout
mkdir -p .opencode/skills
ln -sfn "$REPO/skills/cpp-symbol-scout" .opencode/skills/cpp-symbol-scout
ln -sfn "$REPO/skills/cpp-include-finder" .opencode/skills/cpp-include-finder
ln -sfn "$REPO/skills/cpp-include-analyzer" .opencode/skills/cpp-include-analyzer
```

Claude-compatible and agent-compatible OpenCode paths are also supported:

```bash
mkdir -p ~/.claude/skills ~/.agents/skills
ln -sfn /path/to/cpp-symbol-scout/skills/cpp-symbol-scout ~/.claude/skills/cpp-symbol-scout
ln -sfn /path/to/cpp-symbol-scout/skills/cpp-symbol-scout ~/.agents/skills/cpp-symbol-scout
```

If OpenCode permissions are restrictive, allow the required skills in `opencode.json`:

```json
{
  "permission": {
    "skill": {
      "cpp-symbol-scout": "allow",
      "cpp-include-finder": "allow",
      "cpp-include-analyzer": "allow"
    }
  }
}
```

## Portable CLI Use From A Skill

Agents should not assume the Python package is globally installed. Prefer this resolution order:

1. If `cpp-symbol-scout --version` works, use the installed command.
2. If the current directory has `src/cpp_symbol_scout`, run with `PYTHONPATH=src python3 -B -m cpp_symbol_scout`.
3. Otherwise locate the skill folder under Codex/OpenCode skill directories and run with `PYTHONPATH="$SCOUT/src"`.
4. Install editable with `python3 -m pip install -e "$SCOUT"` only when persistent CLI access is useful.
