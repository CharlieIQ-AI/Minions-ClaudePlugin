---
description: Make one Minions task wait on another
argument-hint: [ticket] on [ticket]
---
Use the Minions skill's Clear blocked work section for `$ARGUMENTS`.
Parse `$ARGUMENTS` as `<ticket> on <ticket>`; print usage and call no tool when malformed.
Take an action only after the user explicitly chooses it.