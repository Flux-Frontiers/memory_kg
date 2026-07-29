"""
cmd_hooks.py

CLI command for installing MemoryKG git hooks and Claude Code auto-ingest hooks:

  install-hooks           — install the pre-commit snapshot hook into .git/hooks/
  install-hooks --claude  — also install Claude Code hooks into .claude/settings.json
  install-hooks --global  — install Claude Code hooks into ~/.claude/settings.json

  Author: Eric G. Suchanek, PhD
  Last Revision: 2026-04-25
"""

# pylint: disable=import-outside-toplevel

from __future__ import annotations

import stat
from pathlib import Path

import click

from memory_kg.cli.group import cli

# ---------------------------------------------------------------------------
# Pre-commit hook (embedded so this module is self-contained when installed)
# ---------------------------------------------------------------------------

_PRE_COMMIT_HOOK = """\
#!/usr/bin/env bash
# MemoryKG pre-commit hook — keeps local index in sync and captures metrics
# snapshots BEFORE quality checks run.
# Installed by: memorykg install-hooks
# Skip with: DOCKG_SKIP_SNAPSHOT=1 git commit ...
set -euo pipefail

[ "${DOCKG_SKIP_SNAPSHOT:-0}" = "1" ] && exit 0

REPO_ROOT="$(git rev-parse --show-toplevel)"

cd "$REPO_ROOT"

# Capture the tree hash of the staged index NOW — before any tool modifies files.
TREE_HASH=$(git write-tree)
BRANCH=$(git rev-parse --abbrev-ref HEAD)

# Rebuild local MemoryKG index to keep it in sync with staged content.
"$REPO_ROOT/.venv/bin/memorykg" build || exit 1

# Snapshot MemoryKG (version auto-detected from installed package).
"$REPO_ROOT/.venv/bin/memorykg" snapshot save \\
    --repo . \\
    --tree-hash "$TREE_HASH" \\
    --branch "$BRANCH" \\
  || { echo "[memorykg] snapshot skipped (run 'memorykg build' to initialize)" >&2; }

# Stage snapshot directory so it is included in the commit.
git add .memorykg/snapshots/ 2>/dev/null || true

# Run pre-commit framework checks (ruff, mypy, detect-secrets, etc.) AFTER
# snapshots are captured and staged. Delegates to .pre-commit-config.yaml so
# quality checks stay in one place.
PRECOMMIT="$REPO_ROOT/.venv/bin/pre-commit"
if [ -x "$PRECOMMIT" ]; then
    "$PRECOMMIT" run || exit 1
elif command -v pre-commit &>/dev/null; then
    pre-commit run || exit 1
fi

exit 0
"""

# ---------------------------------------------------------------------------
# Claude Code auto-ingest hook scripts (written to ~/.agentkg/hooks/)
# ---------------------------------------------------------------------------

_USER_PROMPT_HOOK = """\
#!/bin/bash
# AGENT-KG USER PROMPT HOOK
# Ingests the user turn into the AgentKG conversation graph.
# Installed by: memorykg install-hooks --global / --claude

INPUT=$(cat)
PROMPT=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('prompt',''))" 2>/dev/null)

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo ".")
if [ ! -d "$REPO_ROOT/.agentkg" ]; then
    echo "{}"
    exit 0
fi

AGENT_KG="$REPO_ROOT/.venv/bin/agent-kg"

if [ -n "$PROMPT" ]; then
    "$AGENT_KG" ingest "$PROMPT" --role user --repo "$REPO_ROOT" 2>/dev/null || true
fi

echo "{}"
"""

_STOP_HOOK = """\
#!/bin/bash
# AGENT-KG STOP HOOK
# Ingests the assistant turn, periodically consolidates, and snapshots.
# Installed by: memorykg install-hooks --global / --claude

CONSOLIDATE_INTERVAL=20
STATE_DIR="$HOME/.agentkg/hook_state"
mkdir -p "$STATE_DIR"

INPUT=$(cat)
SESSION_ID=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('session_id','unknown'))" 2>/dev/null)
MSG=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('last_assistant_message',''))" 2>/dev/null)
TRANSCRIPT_PATH=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('transcript_path',''))" 2>/dev/null)
TRANSCRIPT_PATH="${TRANSCRIPT_PATH/#\\~/$HOME}"

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo ".")
if [ ! -d "$REPO_ROOT/.agentkg" ]; then
    echo "{}"
    exit 0
fi

AGENT_KG="$REPO_ROOT/.venv/bin/agent-kg"

if [ -n "$MSG" ]; then
    "$AGENT_KG" ingest "$MSG" --role assistant --repo "$REPO_ROOT" --no-embed 2>/dev/null || true
fi

EXCHANGE_COUNT=0
if [ -f "$TRANSCRIPT_PATH" ]; then
    EXCHANGE_COUNT=$(python3 - "$TRANSCRIPT_PATH" <<'PYEOF'
import json, sys
count = 0
with open(sys.argv[1]) as f:
    for line in f:
        try:
            entry = json.loads(line)
            msg = entry.get('message', {})
            if isinstance(msg, dict) and msg.get('role') == 'user':
                content = msg.get('content', '')
                if isinstance(content, str) and '<command-message>' in content:
                    continue
                count += 1
        except Exception:
            pass
print(count)
PYEOF
2>/dev/null)
fi

LAST_CONSOLIDATE_FILE="$STATE_DIR/${SESSION_ID}_last_consolidate"
LAST_CONSOLIDATE=0
[ -f "$LAST_CONSOLIDATE_FILE" ] && LAST_CONSOLIDATE=$(cat "$LAST_CONSOLIDATE_FILE")
SINCE_LAST=$((EXCHANGE_COUNT - LAST_CONSOLIDATE))

echo "[$(date '+%H:%M:%S')] Stop session=$SESSION_ID exchanges=$EXCHANGE_COUNT since_last_consolidate=$SINCE_LAST" >> "$STATE_DIR/hook.log"

if [ "$SINCE_LAST" -ge "$CONSOLIDATE_INTERVAL" ] && [ "$EXCHANGE_COUNT" -gt 0 ]; then
    echo "$EXCHANGE_COUNT" > "$LAST_CONSOLIDATE_FILE"
    echo "[$(date '+%H:%M:%S')] Triggering consolidation at exchange $EXCHANGE_COUNT" >> "$STATE_DIR/hook.log"
    "$AGENT_KG" prune --repo "$REPO_ROOT" --force >> "$STATE_DIR/hook.log" 2>&1 &
fi

"$AGENT_KG" snapshot --repo "$REPO_ROOT" --label "session-end" 2>/dev/null &

echo "{}"
"""

_PRECOMPACT_HOOK = """\
#!/bin/bash
# AGENT-KG PRE-COMPACT HOOK
# Runs prune synchronously before context compaction so no turns are lost.
# Installed by: memorykg install-hooks --global / --claude

STATE_DIR="$HOME/.agentkg/hook_state"
mkdir -p "$STATE_DIR"

INPUT=$(cat)
SESSION_ID=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('session_id','unknown'))" 2>/dev/null)

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo ".")
if [ ! -d "$REPO_ROOT/.agentkg" ]; then
    echo "{}"
    exit 0
fi

AGENT_KG="$REPO_ROOT/.venv/bin/agent-kg"

echo "[$(date '+%H:%M:%S')] PreCompact triggered for session $SESSION_ID" >> "$STATE_DIR/hook.log"
"$AGENT_KG" prune --repo "$REPO_ROOT" --force >> "$STATE_DIR/hook.log" 2>&1
"$AGENT_KG" snapshot --repo "$REPO_ROOT" --label "pre-compact" 2>/dev/null
echo "[$(date '+%H:%M:%S')] PreCompact complete for session $SESSION_ID" >> "$STATE_DIR/hook.log"

echo "{}"
"""

# Maps Claude Code event → (script filename, hook config dict)
_CLAUDE_HOOK_SCRIPTS: dict[str, tuple[str, str]] = {
    "UserPromptSubmit": (
        "agent_kg_user_prompt_hook.sh",
        _USER_PROMPT_HOOK,
    ),
    "Stop": (
        "agent_kg_stop_hook.sh",
        _STOP_HOOK,
    ),
    "PreCompact": (
        "agent_kg_precompact_hook.sh",
        _PRECOMPACT_HOOK,
    ),
}

_HOOK_TIMEOUTS: dict[str, int | None] = {
    "UserPromptSubmit": None,
    "Stop": 30,
    "PreCompact": 60,
}


def _write_claude_hook_scripts(hooks_dir: Path) -> None:
    """Write the three agent-kg shell scripts to hooks_dir."""
    hooks_dir.mkdir(parents=True, exist_ok=True)
    for filename, content in _CLAUDE_HOOK_SCRIPTS.values():
        script_path = hooks_dir / filename
        script_path.write_text(content)
        mode = script_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
        script_path.chmod(mode)


def _merge_claude_settings(settings_path: Path, hooks_dir: Path, force: bool) -> bool:
    """Merge agent-kg hook entries into a Claude Code settings.json.

    :param settings_path: Path to the settings.json to update.
    :param hooks_dir: Directory where the hook scripts were written.
    :param force: Overwrite existing hook entries.
    :return: True if settings were updated.
    """
    import json  # pylint: disable=import-outside-toplevel

    settings_path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict = {}
    if settings_path.exists():
        try:
            existing = json.loads(settings_path.read_text())
        except json.JSONDecodeError:
            click.echo(f"  Warning: could not parse {settings_path} — skipping.", err=True)
            return False

    existing_hooks = existing.setdefault("hooks", {})
    updated = False

    for event, (filename, _content) in _CLAUDE_HOOK_SCRIPTS.items():
        script_path = hooks_dir / filename
        timeout = _HOOK_TIMEOUTS[event]
        entry: dict = {"type": "command", "command": str(script_path)}
        if timeout is not None:
            entry["timeout"] = timeout
        hook_block = {"hooks": [entry]}

        if event in existing_hooks and not force:
            click.echo(f"  {event} already in {settings_path} (use --force to overwrite)")
            continue

        existing_hooks[event] = [hook_block]
        updated = True

    if updated:
        settings_path.write_text(json.dumps(existing, indent=2) + "\n")

    return updated


@cli.command("install-hooks")
@click.option(
    "--repo",
    default=".",
    type=click.Path(exists=True),
    show_default=True,
    help="Repository root.",
)
@click.option(
    "--force",
    is_flag=True,
    help="Overwrite existing hooks.",
)
@click.option(
    "--claude",
    "claude_hooks",
    is_flag=True,
    help="Install Claude Code auto-ingest hooks into .claude/settings.json (project scope).",
)
@click.option(
    "--global",
    "global_hooks",
    is_flag=True,
    help="Install Claude Code auto-ingest hooks into ~/.claude/settings.json (all repos).",
)
def install_hooks(repo: str, force: bool, claude_hooks: bool, global_hooks: bool) -> None:
    """Install MemoryKG git and/or Claude Code auto-ingest hooks.

    Git pre-commit hook (always installed):
      1. Rebuilds local MemoryKG index before each commit
      2. Captures a metrics snapshot keyed by tree hash
      3. Stages .memorykg/snapshots/ atomically
      4. Runs pre-commit framework checks (ruff, mypy, detect-secrets)

    Claude Code hooks (--claude or --global):
      Writes three shell scripts to ~/.agentkg/hooks/ and registers them in
      the target settings.json:

      \\b
        UserPromptSubmit  ingest every user turn (with embeddings)
        Stop              ingest assistant turns + periodic consolidation + snapshot
        PreCompact        synchronous prune + snapshot before context compression

      Use --claude for project scope (.claude/settings.json) or --global for
      all repos (~/.claude/settings.json).

    Example:
        memorykg install-hooks --repo . --global
    """
    repo_root = Path(repo).resolve()
    git_dir = repo_root / ".git"

    if not git_dir.is_dir():
        click.echo(f"Error: {repo_root} is not a git repository.", err=True)
        raise SystemExit(1)

    # ── Git pre-commit hook ───────────────────────────────────────────────────
    hooks_dir = git_dir / "hooks"
    hooks_dir.mkdir(exist_ok=True)
    hook_path = hooks_dir / "pre-commit"

    if hook_path.exists() and not force:
        click.echo(f"  pre-commit hook already exists: {hook_path}")
        click.echo("  Use --force to overwrite.")
    else:
        hook_path.write_text(_PRE_COMMIT_HOOK)
        mode = hook_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
        hook_path.chmod(mode)
        click.echo(f"OK Installed pre-commit hook: {hook_path}")
        click.echo("   Skip with: DOCKG_SKIP_SNAPSHOT=1 git commit ...")

    # ── Claude Code hooks ─────────────────────────────────────────────────────
    targets: list[Path] = []
    if global_hooks:
        targets.append(Path.home() / ".claude" / "settings.json")
    if claude_hooks:
        targets.append(repo_root / ".claude" / "settings.json")

    if not targets:
        return

    agentkg_hooks_dir = Path.home() / ".agentkg" / "hooks"
    _write_claude_hook_scripts(agentkg_hooks_dir)
    click.echo(f"OK Wrote hook scripts to: {agentkg_hooks_dir}")

    for settings_path in targets:
        updated = _merge_claude_settings(settings_path, agentkg_hooks_dir, force=force)
        if updated:
            click.echo(f"OK Claude Code hooks written to: {settings_path}")
            click.echo("   Turns will be auto-ingested on UserPromptSubmit, Stop, and PreCompact.")
        else:
            click.echo(f"   No changes needed in {settings_path}.")
