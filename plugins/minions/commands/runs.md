---
description: Report how Minions runs are looking
argument-hint: [mine|org] [hours]
---
Use the Minions skill to report how the runs are looking without changing anything. Parse `$ARGUMENTS`: a first word of `mine` or `org` is the scope (default mine); a number is the window in hours (default 24, 1–168). Ask the skill for the fleet overview and report: tasks by status; runs by role and outcome with total cost; active runs, calling out any over 30 minutes; failures grouped by error summary; stuck queue rows; and the blocker count. Say when the overview is empty. Keep the report read-only; if a follow-up action is requested, get explicit confirmation before writing anything.
