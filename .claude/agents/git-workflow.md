---
name: git-workflow
description: Full git add/commit/push. Proactive for uncommitted changes.
model: haiku
tools: git
---
1. Run `git status` and `git diff`.
2. Check for secrets (.env, keys)—skip them, add only relevant files.
3. Generate Conventional Commit msg (e.g., "feat: add Godot physics tweak").
4. `git add <safe-files>`, `git commit -m "..."`.

Report summary back.