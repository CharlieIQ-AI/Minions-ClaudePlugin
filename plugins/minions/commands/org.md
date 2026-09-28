---
description: Show or switch the organization this Minions connection works in
argument-hint: [organization name]
---
Use the Minions skill's Organizations section for `$ARGUMENTS`.
If `$ARGUMENTS` is empty, call `list_orgs` and report the active organization and the others available; change nothing.
Otherwise match `$ARGUMENTS` against the `list_orgs` result; if it is not there, say so and call no tool. Call `switch_org` only after the user explicitly confirms the switch, then report the organization now active and remind them that repositories and tasks are now read from that organization.
