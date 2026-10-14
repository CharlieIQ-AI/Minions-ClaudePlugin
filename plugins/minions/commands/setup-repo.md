---
description: Set up a repository for Minions
argument-hint: [repo label]
---
Use the Minions skill to walk through the repo-setup checklist.
When the repository is not registered yet, follow the skill's "Register a repository" steps:
list the connected providers, list that provider's repositories, let the user choose one, then
register it. Never type a repository coordinate from memory.
Use `$ARGUMENTS` as the repo when it is present; otherwise use the repository in the current session.
Offer a MINIONS.md draft for review and explain what it would change.
Do not write repository files or settings until the user explicitly confirms the specific changes. After confirmation, walk the setup order: `add_repo` → `set_repo_settings` (stack label first, chosen from `list_stack_labels`, so `stack_label_has_image` is true before anything else) → `set_repo_branches` → `set_repo_scripts` → `set_repo_secret` → `get_repo_setup` to confirm `dispatchable`. Before storing a credential, ask whether other repositories share it; if they do, use `set_org_secret` once (scoped to all repositories or the selected `repoLabels`) instead of `set_repo_secret` per repository. Creation requires the repo to have an assigned tracker board; `list_repos` shows it as `board`. If it is null, ask the user to assign one with `set_repo_board`, using a board id from `list_tracker_boards` (or, on an Optional-mode repo, offer an internal-only task with `trackerBoard: "none"`) before filing. Repository setup is open to org admins and to the lead of a team with access to the repository; a team lead sees and may assign only the boards their team selected, and cannot clear a repository's board.
