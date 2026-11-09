---
description: Answer a Minions clarification question
argument-hint: "[ticket key]"
---
Use the Minions skill's Clear blocked work section for `$ARGUMENTS`.
When `$ARGUMENTS` names a ticket, call `list_blockers` with `key` set to that ticket key.
If `$ARGUMENTS` is empty, ask for the ticket key.
Show the choices and take an action only after the user explicitly chooses one.