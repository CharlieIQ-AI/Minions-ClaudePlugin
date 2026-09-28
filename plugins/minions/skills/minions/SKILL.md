---
name: minions
description: Use Minions for filing work, clearing blocked work, reporting status, or setting up a repository, or updating the plugin.
---

# Minions developer guide

This skill covers six developer jobs:

1. **File work** — create or adopt a task with a grounded specification.
2. **Clear blocked work** — identify the parked state and choose the corresponding action.
3. **Report status** — inspect tasks and runs without changing them.
4. **Diagnose a run** — read one ticket's latest run and say what happened.
5. **Set up a repository** — check dispatch prerequisites and prepare repository guidance.
6. **Update the plugin** — run the plugin update when the user asks for it or accepts the version notice.

At the start of every session, call `minions_guide` once and use its `tools` list and `version` as the current tool inventory. Do not rely on a remembered tool list.

The Minions MCP server instructions are authoritative. Follow them when they are more recent or
more specific than this skill. This skill is a longer working guide, not a replacement for those
instructions. Do not restate connection setup; see `plugins/minions/README.md` for that.

## Consent and safety

These are user-controlled operations. Never answer a clarification, approve a CI fix, merge,
pause, or delete anything without the user's explicit decision. Reading status and setup facts is
safe; any tool that changes work requires the user's decision immediately before the action.
This rule covers every slash command in `commands/`, including `/spec`, `/why`, `/fix-ci`,
`/answer`, `/merge`, `/depends`, `/pause`, `/resume`, `/delete`, `/unblock`, and `/bugs`; call a mutating tool
(`create_task`, `resolve_ci_fix`, `answer_clarification`, `merge_task`, `merge_feature`, `set_dependency`, `set_task_owner`,
`pause_task`, `resume_task`, `delete_task`, `switch_org`, or `dismiss_tracker_sync`) only when that explicit decision immediately precedes it. A deletion reason chosen by the assistant on the user's behalf does not count as consent; the user must name the reason.

On an error result, read `error.code` first and branch on it: `not_found` means say the task is not visible to this connection; `permission_denied` means say so and stop; `not_in_window`, `already_merged`, `stale_plan_version`, `ambiguous`, `in_progress`, and `idempotency_conflict` mean relay the message and follow its instruction; `partial_failure` means list `details.steps`; fall back to the message when `structuredContent` is absent.

Use the live results returned by the MCP. Do not infer a repository, branch, policy, ticket state,
blocker, or threshold from this document or from an earlier conversation.

## Organizations

Every tool acts in this connection's **active organization** — the one chosen on the consent screen
when the assistant was connected, or the one `switch_org` last set. `list_repos` names it in its
`org` field; read that back to the user when it matters. A user who belongs to several
organizations may ask to work in another one:

- Call `list_orgs` to see the organizations the user can act in; `active: true` marks the current
  one. Use it when the user names an organization you do not recognise, when a repository they
  expect is missing from `list_repos`, or when they ask which organization they are working in.
- Call `switch_org` only after the user explicitly asks to work in a named organization that
  `list_orgs` returned. It applies from the next call: call `list_repos` again afterwards rather
  than reusing an earlier result. Never switch to guess where a repository might live.
- If the organization is not in `list_orgs`, say so; membership is managed in the web application.

## File work

### Start with live repository facts

Call `list_repos` **first**, before asking the user to choose filing options. Use its result as the
source of truth:

- Ask the user to choose a repo from the returned repositories.
- After they choose, offer only branches in that repo's `branches` list, including its default
  branch when it is present. Ask separately for **Build from** (the fork point) and **Merge into**
  (the destination); "base branch" is ambiguous and must be clarified with the user.
- Ask the user whether to enable auto-merge, using the repo's live auto-merge settings, and read
  the creation result's `resolved` values back to them rather than assuming the request won.
- If `auto_merge_policy` is `never`, do not offer auto-merge at all. Do not present it as a
  choice, a default, or an implied option.
- Respect `auto_merge_available` and any other capability fields returned for that repo.

Do not write repository names, branch names, or organization names into a prompt or example.
Render the values from `list_repos` at run time. If the requested repo or branch is not in the
result, ask the user to choose again rather than guessing.

### Create or adopt a task

For a new task, collect the user's request and the choices above, then call `create_task` only
after the user has made the required decisions. Generate a fresh `clientRequestId` for every
`create_task`, `adopt_ticket`, and `create_feature` call. For an existing ticket, call
`preview_ticket` first, show the user what would be adopted, and read `eligibleForAdoption`; when it
is false, relay `ineligibleReasons` verbatim and do not call `adopt_ticket`. If the result has
`code: "ambiguous"`, ask the user for the ticket URL and call nothing else. Prefer the ticket URL
when the user has one, because a bare key can match more than one connected board. Call
`adopt_ticket` only after they explicitly choose to adopt an eligible ticket. Never use `create_task` to duplicate an existing ticket. For `create_task`, `adopt_ticket`, and
`create_feature`, report the returned `minionsUrl` as the Minions page to open; keep the returned
tracker `url` as the tracker link and report it second. For a feature, include the feature link and
each child story's `minionsUrl` when reporting the created result.

### Recover a lost create response

When a create response is not received, call `get_submission` with the generated
`clientRequestId` first. If no id was sent, call `list_my_tasks` and match the title before
retrying. A null task key means the tracker write failed and must not be recreated. Never call a
create tool again until this recovery check says that nothing was created.

Before retrying, preserve the same id and original payload when the submission failed or became
stale; a succeeded submission must be replayed rather than creating another task.

Use `verbatimSpec` only when the user supplied a complete, already-written specification and wants
that text preserved as written. Do not set `verbatimSpec` merely because a request is detailed;
ordinary requests should be sent as prose so Minions can plan them. A preserved specification
must not be silently rewritten or split.

### Make the specification survive planning

When asking Minions to plan ordinary prose, include the facts needed to produce a complete spec.
The spec must contain all of these sections:

- Context
- Goal
- Acceptance criteria
- Coverage declaration
- Technical Notes
- Implementation outline
- Assumptions
- Dependencies
- Blocks
- Out of Scope
- Test Plan
- Out of Scope for Tests

A coverage declaration line needs a colon and must name the ACs that cover it, for example:
`Failure paths: AC3`. Use the same form for `Authorization:` and `Empty & loading states:`;
when a surface truly does not apply, state `N/A` and give a reason. Do not ask for an acceptance
criterion that can be verified only by production measurement. Make ordered work explicit with a
`dependsOnJiraKey` value; a Dependencies paragraph by itself does not create an execution
blocker.

Keep acceptance criteria observable and independently verifiable. Record assumptions instead of
hiding decisions in prose, identify blocks separately from dependencies, and state what is out of
scope. If a required fact is unknown and changes the implementation, ask the user before filing
rather than inventing it.

## File a written spec

- If the argument is empty, ask for the complete spec text or a file path and stop.
- Run this pre-flight over the supplied text: every `## Coverage declaration` line uses the colon
  form (`Failure paths:`, `Authorization:`, `Empty & loading states:`) and cites `AC<n>` or
  `N/A — <reason>`; no acceptance criterion requires a result that can be verified only by
  production measurement or post-deploy observation (move it to a `Post-deploy note` under Out of
  Scope or a follow-up); Context is
  short, about ten lines, with evidence as one list; and every ticket key under `## Dependencies`
  is also passed as `dependsOnJiraKey`.
- Confirm repo, Build from, Merge into, and auto-merge from `list_repos` according to the live
  repository facts above, never from the spec text.
- If any check fails, show the specific failing line and amended text, and do not call
  `create_task` until the user accepts it.
- After the user accepts the pre-flight, call `create_task` with `verbatimSpec: true` and the
  accepted text unchanged; read the returned `resolved` values back to the user. Report the
  returned `minionsUrl` as the link to open the task, followed by the tracker `url`.

## Clear blocked work

First call `list_blockers` and inspect the live task state. Use each item's `url` when reporting the
blocked task or feature. Map the blocker to exactly one action, then explain what that action will do
and ask for the user's explicit decision before calling it:

| Blocker or parked state | Tool |
| --- | --- |
| Clarification question | `answer_clarification` |
| CI-fix decision | `resolve_ci_fix` |
| Hand-back to the requester | `resolve_handback` |
| Proposed feature split that should remain one task | `keep_single_task` |
| Merge Problem | `merge_task`, but only after the underlying cause is fixed |
| Rework requested by review | `request_changes` |
| Feature review needs another attempt | `retry_feature_review` |
| A task should stop for now | `pause_task` |
| A paused task should continue | `resume_task` |
| One task must wait on another | `set_dependency` (key = the waiting task, dependsOnJiraKey = the task it waits on) |
| Tracker mirror out of step (`tracker_sync`) | `dismiss_tracker_sync` — hides the notice only; the fix for the underlying error is the tracker's workflow configuration |

For a hand-back, read `handback.recommendedStatus` and `resumeStatuses` from `list_blockers`. Unless the user chooses another resume status, name that destination in the confirmation question (for example, "resume at Ready for Test, building on the human commits?") and pass it as `targetStatus` to `resolve_handback`; report the returned `status` and `statusSource` afterwards.

A Merge Problem is not solved by repeatedly calling `merge_task`: inspect the cause, have it fixed,
then merge. For parked states not represented by one of those actions, use the web application;
the remaining resolution steps are web-app actions, not substitute MCP calls. Do not call an action
just to discover what it would do when the user has not decided.

- `/fix-ci` — from `list_blockers` or `get_task`, find a blocker with type `ci_confirm` and read its
  `ciFix` fields: failing checks, commit, failing-test count versus threshold, and run URL. Present
  the two `options` labels (`Approve auto-fix` and `Leave as-is`), then call `resolve_ci_fix` with
  `action: approve` or `dismiss` only after the user picks one. Do not look in comments or a job log
  for the failing check for this blocker.
- `/answer` — show the ticket's open question(s) and options from `list_blockers` (type
  `clarification`, carrying `storyId` and `clarificationId`), then call `answer_clarification` only
  with the user's stated answer.
- `/merge` — call `get_task` first; at `Merge Problem`, refuse `merge_task` until the user confirms
  the cause is fixed; otherwise call it only after the user's explicit decision.
- `/depends` — parse `<A> on <B>` (two ticket keys separated by the word `on`); on anything else
  print a usage line and call no tool. Otherwise call `get_task` for both, then `set_dependency` with
  `key: A` and `dependsOnJiraKey: B` after the user's decision.
- `/pause` and `/resume` — call `get_task` first; if the task is already paused (for pause) or not
  paused (for resume), report that and call nothing; otherwise call the mutating tool only after the
  user's decision.
- `/org` — with no argument, call `list_orgs` and report the active organization and the others
  available; with a name, match it against `list_orgs` and call `switch_org` only after the user
  confirms the switch, then report the organization now active.
- `/unblock` — with a key, call `list_blockers` with `key` for that task; when its only blocker is
  `tracker_sync`, present `dismiss_tracker_sync` as the single available action, explain that it hides
  the notice and does not change the tracker, and call it only after the user's explicit confirmation.
  When the user only asks what the notice means, explain and call nothing.

### Change finished work

Call `get_task` and check `canRequestChanges` before changing finished work. If it is false, report
the task's current status and call nothing. If it is true, explain that the task will return to Planning
with the user's instructions, obtain the user's explicit decision, and then call `request_changes`.
`reviewCycleLimit` is optional when the user wants to raise the per-ticket review-cycle cap.

## Delete a task

Call `get_task` for the key. If the item is a feature (`type` is `epic`, or the result shows child
tasks), say `Features must be deleted from the web app, not through the MCP.` and call nothing.
Otherwise, show the task's `key`, `title`, `status`, and `repo`, then present these valid reasons:

- Duplicate
- Scope changed
- Agent could not complete
- Created by mistake
- Superseded

Ask which reason applies and whether to add an optional `note`. Call `delete_task` with `key`,
`reason`, and the optional `note` only after the user has named a reason and explicitly confirmed.
If `$ARGUMENTS` is empty, ask for the ticket key and call nothing.

After a successful call, report the returned `steps`. If the tool errors with `could not be fully deleted. Failed steps: …`, repeat the failed steps verbatim and say the delete can be retried from the task page in the web app. If it says `You do not have permission to delete this task.`, report that refusal and do not retry with a different reason. Relay `Features must be deleted from the web app, not through the MCP.` verbatim rather than paraphrasing it.

## Features

- Read a feature with `get_feature` before advising or acting.
- Report `phase` and `paused` first.
- Relay an unavailable action's `reason` verbatim.
- Pass `expectedPlanVersion` from the last `get_feature` on every `add_feature_wave`.
- Land with `merge_feature` only after the user's explicit decision.

## Report status

Status reporting is read-only. Use `list_my_tasks` for the caller's own work and `list_tasks` for a request about someone else's work or a repo's work (pass `owner`/`creator` as the email the user supplies, or `"me"`; pass `repo` from `list_repos` when the user names one). When a result carries a non-null `nextCursor` and the user asks for more, call the same tool again with that `cursor`.

### Typed tool results

Every tool result is typed by its published `outputSchema`. Read `structuredContent` when it is present, and do not re-derive or invent fields that the schema does not declare.

### Follow changes

When the user asks "what changed", "anything new since…", or to follow work, call `list_changes` with the `nextCursor` kept from earlier in the conversation, or the stored `serverTime` when the last `nextCursor` was null, instead of `list_my_tasks`. Keep the returned `nextCursor` (or `serverTime`) in the conversation for the next ask. Read detail ONLY for the keys returned: use `get_task` for a `task` change, `get_task_activity` for a `job` change, and `get_feature` for a `feature` change; never call `get_task` for a key not in the change list. Follow the polling guidance: no more than one `list_changes` per 60 seconds, `list_blockers` every few minutes, and no tight loops. `(kind, key, at)` is the idempotency key, so a repeated entry is not a new change.

### Change a task's owner

Call `get_task` and read `actions.setOwner`; if `allowed` is false, report the `reason` and call nothing. Otherwise state the task key and the new owner by name and call `set_task_owner` only after the user explicitly confirms that named owner.

Status reporting is read-only. Use the narrowest read needed:

- Use `get_task` for the current task state and summary. Read `paused`, `owner`, `actions`, and `blocked` from its result rather than inferring them from `status`; report a paused task as paused first and never as simply done or in progress. When `blocked.ciFix` is present, report its failing checks, commit, count versus threshold, run URL, and the Approve auto-fix / Leave as-is choice. Include `urls.minions` whenever you report the task. Report an unavailable action with its `reason` verbatim instead of attempting it, and request `includeBuildPlan` only when the user asks about the plan.
- Use `list_my_tasks` row `url` when reporting a task from that list.
- Use `get_task_activity` for the lifecycle and action history.
- Use `get_job_log` **or** `get_task_comments` only when a run failed and its details are needed.

Do not use status checks as a pretext to change a task. A run marked `retrying` or `incomplete` is
recovering on its own; report that fact and do not manually retry it. If the live result is empty
or stale, say so and ask the user what they want to inspect rather than filling in missing facts.
`list_open_bugs` lists open bug reports read-only; it is restricted to super admins, so relay the
tool's error as the answer when it refuses.

For fleet-level questions — "how are the runs looking", "what is running", "what failed today" — call `get_pipeline_overview` (scope `mine` or `org`, `windowHours` 1–168, default 24) once instead of walking tasks one by one. Report tasks by status, runs by role and outcome with cost, active runs (call out any over 30 minutes), failures grouped by error summary, stuck queue rows, and the blocker count. Runs marked `retrying` or `incomplete` are self-recovering — report them, do not retry them. For detail on one blocked or failed ticket, use `list_blockers` or `/why <ticket>`. The overview is read-only. For "how are the repos doing" or "which repos have problems", super admins call `get_pipeline_health` (read-only; optional `day`, `repo`, `orgId`) for the daily per-repo health report, and relay the tool's error as the answer when it refuses.

## Diagnose a run

This flow is read-only. Read in this order: `get_task`, then `get_task_activity`, then `get_job_log`
for the newest entry in `jobs[]` (use that entry's `id` as `jobId`), and then `get_task_comments`. Read `paused`, `owner`, `actions`, and `blocked` from `get_task` rather than inferring them from `status`; report a paused task as paused first and never as simply done or in progress. When `blocked.ciFix` is present, report its failing checks, commit, count versus threshold, run URL, and the Approve auto-fix / Leave as-is choice. Include `urls.minions` in the report. Report an unavailable action with its `reason` verbatim instead of attempting it, and request `includeBuildPlan` only when the user asks about the plan.
Report the run's agent role, outcome/status, recorded `errorSummary`, the agent's own verification
lines quoted from its `[<role>-bot]` comment, and exactly one next action the user can take (an
existing command or a web-app step). When no run failed, report the latest run the same way. A
`retrying` or `incomplete` run is self-recovering: report it and do not re-dispatch, pause, or retry.
If a read returns empty or an error, say so and stop; never guess a status, job id, or option label.

## Set up a repository

Call the read-only `get_repo_setup` tool for the selected repo and use its live result. Do not
edit repository settings from this skill. Check each of the following:

1. **Stack label gate:** `stack_label_has_image` must be true. A repo without a stack label mapped
to a runner image is not dispatchable; do not promise that work will run until this is fixed in
the web app.
2. **Startup Script:** non-JavaScript dependencies and tools belong in the repo's Startup Script.
The built-in dependency installer handles JavaScript lockfiles; it is not a Python or other
language package installer.
3. **Build Script:** treat the Build Script as a list of checks to run, not as an installer.
Keep installation and verification separate when explaining setup.
4. **CI auto-fix:** read the live `auto_fix_ci` setting and `ci_fix_confirm_threshold`. Explain
whether CI auto-fix is enabled, what threshold is configured for asking for confirmation, and that
an automatic fix must not be approved without the user's explicit decision. Do not assume a
threshold from a default: repository settings override it.
5. **MINIONS.md:** when drafting repository guidance, include a distinct section for each role:
`Planner`, `Plan Reviewer`, `Builder`, `Test Author`, and `Reviewer`. Keep the guidance grounded in
that repository's actual commands and conventions; do not copy connection instructions into it.

Report missing setup facts and point the user to the web application for settings changes. This
skill can explain and check setup, but it cannot edit repo settings.

## Update the plugin

When the user asks to update the plugin, or accepts the SessionStart version notice (including an
`additionalContext` line reading `Minions plugin version check`), run `claude plugin update minions@minions`
via the shell, report the command's result verbatim, and tell the user to run `/reload-plugins` or
start a new session for the update to take effect. Never run `claude plugin update` unasked, and run
no other `claude plugin` subcommand as part of this job.
