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
Do not write repository files or settings until the user explicitly confirms the specific changes.
