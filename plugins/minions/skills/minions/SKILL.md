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
`/answer`, `/merge`, `/depends`, `/pause`, `/resume`, `/delete`, `/restore`, `/unblock`, and `/bugs`; call a mutating tool
(`create_task`, `resolve_ci_fix`, `retry_pr_responder`, `resolve_pr_feedback`, `answer_clarification`, `accept_recommended_answers`, `merge_task`, `merge_feature`, `set_dependency`, `set_task_owner`,
`pause_task`, `resume_task`, `delete_task`, `restore_task`, `delete_feature`, `restore_feature`, `switch_org`, `dismiss_tracker_sync`, or `sign_off_task`) only when that explicit decision immediately precedes it. A deletion reason chosen by the assistant on the user's behalf does not count as consent; the user must name the reason.

On an error result (`isError: true`), parse `content[0].text` as JSON and read `error.code` first; branch on it: `not_found` means say the task is not visible to this connection; `permission_denied` means say so and stop; `not_in_window`, `already_merged`, `stale_plan_version`, `ambiguous`, `in_progress`, `idempotency_conflict`, and `already_removed` mean relay the message and follow its instruction; `partial_failure` means list `details.steps`; an error result never carries `structuredContent`; `error.message` is the text to relay.

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
- An org admin sees and manages every team with `list_teams`, `add_team_member`, and `remove_team_member`. `list_team_members` shows a team's members and pending invites to the same people who may manage it; `list_user_teams` shows the teams a person is on (own teams for anyone; org admins read anyone in the organization; a lead reading someone else sees only the teams the lead leads). Org admins also invite people with `invite_user`. A team lead sees only the teams they lead in `list_teams` and may add or remove members of those teams; inviting people is for org admins. Any other team operation is managed in the web application.
- Each team member has a level on each repository and tracker board their team uses: Member (the default), View (reads the settings) or Edit (changes them). `get_repo_access` and `get_board_access` list who holds which level and need View; an org admin sets one with `set_repo_access` or `set_board_access`. Ask the user before changing a level.

## File work

### Start with live repository facts

Call `list_repos` **first**, before asking the user to choose filing options. Use its result as the
source of truth:

- Ask the user to choose a repo from the returned repositories, or up to five repos for one
  multi-repo task.
- For each chosen repo, offer only branches in that repo's `branches` list, including its default
  branch when it is present. Ask separately for **Build from** (the fork point) and **Merge into**
  (the destination); "base branch" is ambiguous and must be clarified with the user.
- For one repo, call `create_task` with `repoId`, `mergeIntoBranch`, and `buildFromBranch`. For
  2–5 repos, pass `repos` instead, one entry per repo with its own `repoId`, `mergeIntoBranch`,
  and optional `buildFromBranch`; the first entry is the primary repo. `repos` refuses fewer than
  two entries and cannot be combined with `repoId` or the top-level branch fields.
- Relay any returned `warnings` to the user. A multi-repo task builds on the primary repo's runner
  image, so a warning names repos whose image differs; creation still succeeded.
- Ask the user whether to enable auto-merge, using the repo's live auto-merge settings, and read
  the creation result's `resolved` values back to them rather than assuming the request won.
- If `auto_merge_policy` is `never`, do not offer auto-merge at all. Do not present it as a
  choice, a default, or an implied option.
- Respect `auto_merge_available` and any other capability fields returned for that repo.
- Call `list_board_fields` for the chosen repo (the primary repo of a multi-repo task) before
  filing. When it returns fields, ask the user to choose a value for every `required` field from
  its `options`, offering its `defaults` when it has them, and list the other fields with their
  defaults so the user can change any of them. Pass the answers as `customFields`, keyed by field
  name. Never pick a required value on the user's behalf. When `stale` is true, say the options may
  be out of date. After creating, read `resolved.customFields` back with the branches, naming any
  value whose `source` is `default`.
- Creation requires an assigned tracker board; `board` shows it. If `board` is null, ask the user to assign one before filing (with `set_repo_board`, using a board id from `list_tracker_boards`), or offer `trackerBoard: "none"` for an internal-only task on an Optional-mode repo.

Do not write repository names, branch names, or organization names into a prompt or example.
Render the values from `list_repos` at run time. If the requested repo or branch is not in the
result, ask the user to choose again rather than guessing.

### Create or adopt a task

For a new task, collect the user's request and the choices above, then call `create_task` only
after the user has made the required decisions. Generate a fresh `clientRequestId` for every
`create_task`, `adopt_ticket`, and `create_feature` call. To add evidence after a task exists,
call `attach_files` with inline base64 `files` or HTTPS `urls`; it accepts up to five files at
10 MB each, the same document and image types as `create_task`, and turns ZIPs into design
bundles. URLs must be public HTTPS endpoints and are fetched for at most 15 seconds. For an
attachment failure, read the returned validation or not-found error and do not retry with a
larger or unsafe input. `attach_files` also takes a feature's epic key; every task in the feature
gets the files on its next run.

**Whenever files are attached** (on `create_task`, `create_feature` or `attach_files`), ask the
user two questions per file before calling, and never answer them yourself:

1. "Should agents get this file itself, or only read it?" — if itself, set `agentAccess: true` on
   that file; the Builder and Test Author then get the file as attached. An unflagged file is
   reference only (its text or a preview) and its original is not kept.
2. For each file agents get: "Should it be added to your repo?" — put the answer in the request
   text (`story`, the pasted spec, or the feature's description) in words, with the path if the
   user gave one, e.g. "Add `brief.pdf` to the repo at `public/downloads/brief.pdf`" or "Agents use
   `brief.pdf`; do not add it to the repo". The Planner records it; nothing else does.

Before filing a written spec, ask whether the work already has a tracker ticket. If it does, call
`preview_ticket` first and show the user the matched Jira, Azure DevOps, GitLab, GitHub Projects, or
ClickUp ticket, including whether it is an epic and any existing children. Read
`eligibleForAdoption`; when it is false, relay `ineligibleReasons` verbatim and do not adopt. If the
result has `code: "ambiguous"`, ask for the ticket URL and call nothing else. Prefer the ticket URL
when the user has one, because a bare reference can match more than one connected board. Act on the
ticket only after the user explicitly confirms it. To file an authored spec on it, call `create_task`
with `existingTicket` set to that ticket and the complete spec in `story` with `verbatimSpec: true`,
so its `dependsOnJiraKey` and `files` are kept; the server preserves the spec for ordinary stories,
while an epic keeps its spec split-able and attaches its existing children. To take on the ticket
with no authored spec, call `adopt_ticket`, and the ticket's own description is used. Never call
`create_task` without `existingTicket` for work that already has a ticket: that files a duplicate.
For `create_task`, `adopt_ticket`, and
`create_feature`, report the returned `minionsUrl` as the Minions page to open; keep the returned
tracker `url` as the tracker link and report it second. For a feature, include the feature link and
each child story's `minionsUrl` when reporting the created result.

### Product feedback

Use `submit_product_feedback`, `list_my_product_feedback`, `get_product_feedback`, and
`reply_to_product_feedback` to file feedback about Minions, read the team's replies, and respond.
Use `link_feedback_task` or `unlink_feedback_task` to manage a visible task link on an item; only the
item's reporter or a super admin may call either tool, and ask the user before making the change.
`list_my_product_feedback` accepts `scope: "mine"` (the default) or `scope: "org"`; an org admin or a
member with the feedback-reader permission may use the org scope to list every report in the active organization.
Organization admins can use `set_feedback_viewer` to grant or revoke that read-only permission.
Files use the same inline base64 `files` shape as `attach_files`, without `agentAccess`. Reading
another member's report does not grant reply, upload, or task-link permissions.

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

## Investigate before filing

Research is an open-ended, code-aware investigation of a repository: it reads the real code and
answers with `file:line` citations. It is READ-ONLY — it never changes anything. Use it when the
user wants to understand how something works, what is and is not covered, or whether a behaviour
is a bug, and especially when they have no access to the code themselves.

- `start_research` opens a thread across up to 5 distinct repositories. Pass the question and the
  `repoLabels` to investigate (from `list_repos`), plus `refs` when each repository should be read
  at a chosen branch (`{repoLabel: branch}`). `ref` is the primary repository's compatibility
  shorthand; do not pass both `ref` and `refs`. `ref` and `refs` carry only branch overrides, so
  null means the repository's default branch; `branches` reports the effective branch per
  repository resolved at creation, and `commitSha` reports the commit the latest completed
  code-aware turn read, null until one has. `ask_research` adds a follow-up or redirects it;
  the whole thread and its stored `refs` are carried into each answer.
- **Answers are not instant and this is normal.** Both tools return as soon as the question is
  recorded, with `state: "running"`. Poll `get_research_thread` until `state` is `"idle"` and a new
  assistant message is present. A code-aware turn commonly takes 20-150 seconds, longer on the
  first question about a repository. Never report a running turn as a failure or a hang; tell the
  user it is still working and keep polling.
- `state` is `"abandoned"` when a turn was started and never finished — ask again. It is
  `"failed"` when the last turn errored; `error` says why, and asking again retries.
- `list_research_threads` and `get_research_thread` show the stored `refs` alongside the
  organization's investigations and the tickets each produced. Their `branches` entries show
  the effective branch resolved at creation, and `commitSha` is the commit the latest completed
  code-aware turn read (null until one has).
- One turn at a time per thread: `ask_research` returns `in_progress` if one is already running.

### Turning research into work

When the user is ready to act on what was found:

1. `summarize_research` distils the thread into its conclusions, preserving every `file:line`
   citation.
2. File the task as usual (`create_task`), using that summary as the Context so the pipeline
   inherits the evidence instead of a retelling.
3. `link_research_ticket` records the ticket against the thread, so the investigation behind the
   work stays findable.

## File a written spec

- If the argument is empty, ask for the complete spec text or a file path and stop.
- Ask whether this work already has a tracker ticket and wait for the answer before calling any
  create tool. If it has one, preview and confirm it as described under **Create or adopt a task**.
- Run this pre-flight over the supplied text: every `## Coverage declaration` line uses the colon
  form (`Failure paths:`, `Authorization:`, `Empty & loading states:`) and cites `AC<n>` or
  `N/A — <reason>`; no acceptance criterion requires a result that can be verified only by
  production measurement or post-deploy observation (move it to a `Post-deploy note` under Out of
  Scope or a follow-up); Context is
  short, about ten lines, with evidence as one list; and every ticket key under `## Dependencies`
  is also passed as `dependsOnJiraKey`.
- Confirm repo, Build from, Merge into, auto-merge, and the board's custom fields from
  `list_repos` and `list_board_fields` according to the live repository facts above, never from
  the spec text.
- If any check fails, show the specific failing line and amended text, and do not call
  `create_task` until the user accepts it.
- When the user attaches files to the spec, ask the two attachment questions under **Create or adopt
  a task** and set `agentAccess` per file. The repo decision must already be in the spec's words;
  if it is not, show the line to add and wait for the user to accept it.
- After the user accepts the pre-flight, call `create_task` with `verbatimSpec: true` and the
  accepted text unchanged, and with `existingTicket` set to the confirmed ticket when the work
  already has one; read the returned `resolved` values and any `warnings` back to the user. Report the
  returned `minionsUrl` as the link to open the task, followed by the tracker `url`.

## Clear blocked work

First call `list_blockers` and inspect the live task state. Use each item's `url` when reporting the
blocked task or feature. Map the blocker to exactly one action, then explain what that action will do
and ask for the user's explicit decision before calling it:

| Blocker or parked state | Tool |
| --- | --- |
| Clarification question | `answer_clarification` |
| Recommended answers available | Present each `recommendedAnswers` question and answer, ask for confirmation, then call `accept_recommended_answers` with the task key. |
| CI-fix decision | `resolve_ci_fix` |
| CI auto-fix stuck (hit its attempt cap) | `resolve_ci_fix` with `action: retry` — resets the counters and re-runs CI on the code host; on a feature it also sets auto-merge back on |
| PR review needs you (`pr_response`, the PR responder hit its attempt cap) | `retry_pr_responder` — resets the attempt count; the watcher queues the responder on its next check, within about 10 minutes, while the task is in review (`inReview: false` means it resumes when the task is back in review). A paused task keeps the reset and runs once resumed. Replying on the pull request also restarts it |
| PR feedback waiting for approval (blocker type pr_feedback) | `resolve_pr_feedback` — approve or decline each item in `prFeedback.items`, or approve all; approved items start within about 10 minutes. |
| Provider-reported failing CI (`ci_failed`) | Call `refresh_ci` to re-read the state, then, after the user's confirmation, call `run_ci_fixer` against the stored failing run |
| Hand-back to the requester | `resolve_handback` |
| Proposed feature split accepted as a feature | Show the proposed breakdown, ask for the user's decision, then call `convert_to_feature` (optionally with edited `waves` and required `autoMerge`) |
| Proposed feature split that should remain one task | `keep_single_task` — call it when the user rejects the breakdown |
| Merge Problem | `merge_task`, but only after the underlying cause is fixed |
| Rework requested by review | `request_changes` |
| Feature review needs another attempt | `retry_feature_review` |
| A task should stop for now | `pause_task` |
| A paused task should continue | `resume_task` |
| One task must wait on another | `set_dependency` (key = the waiting task, dependsOnJiraKey = the task it waits on) |
| Tracker mirror out of step (`tracker_sync`) | `dismiss_tracker_sync` — hides the notice only; the fix for the underlying error is the tracker's workflow configuration |
| Acceptance criteria only a person can confirm (`signoff`) | `sign_off_task` — show each line of `signoffAcs` and ask the user to approve or deny. `decision: "approve"` only after they say they checked every one; `decision: "deny"` needs their reason, which sends the task back to Planning as its feedback. `merge_task` is refused until they decide |

For a hand-back, read `handback.recommendedStatus` and `resumeStatuses` from `list_blockers`. Unless the user chooses another resume status, name that destination in the confirmation question (for example, "resume at Ready for Test, building on the human commits?") and pass it as `targetStatus` to `resolve_handback`; report the returned `status` and `statusSource` afterwards.

A Merge Problem is not solved by repeatedly calling `merge_task`: inspect the cause, have it fixed,
then merge. A `ci_failed` blocker means the provider's live pull-request checks are failing: report
its `get_task.ci` check names, commit, and run URL, then call `refresh_ci` to re-read the state.
After the user confirms, call `run_ci_fixer` to start a fixer against the stored failing run.
It is visible even when CI auto-fix is disabled, and `resolve_ci_fix` does not apply
unless the blocker is specifically `ci_confirm` or a CI auto-fix stuck blocker (`action: retry`). For parked states not represented by one of those actions, use the web application;
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

### Review a triage verdict

When `get_task` returns a non-null `triage` object, present its classification, confidence, summary,
evidence, related keys, draft reproduction, and missing information. For a bug report awaiting review,
explain the two clarification options exactly as returned by the task: `Plan it as a bug` or
`Close — expected behavior`. Ask the user which option they choose before calling
`answer_clarification`; if they choose to provide more information, pass that text as the answer.
After three triage runs, only the two named options can be accepted.
- `/merge` — call `get_task` first; at `Merge Problem`, refuse `merge_task` until the user confirms
  the cause is fixed. When `blocked.type` is `ci_failed`, name the reported checks and refuse the
  merge until the user confirms they are green; otherwise call it only after the user's explicit decision.
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

Use `add_task_note` when the user wants to tell the agents something without stopping or sending the task back; it needs no confirmation beyond the user having stated the note.

## Delete a task or feature

Call `get_task` for the key. If the item is a feature (`type` is `epic`, or the result shows child
tasks), use `delete_feature` with the epic key instead of `delete_task`; everything below applies to
both. Show the item's `key`, `title`, `status`, and `repo`, then present these valid reasons:

- Duplicate
- Scope changed
- Agent could not complete
- Created by mistake
- Superseded
- Expected behavior

Ask which reason applies and whether to add an optional `note`. Then ask which mode the user wants:

- `full` (default): close the pull request (the branch stays) and move the ticket to Removed.
- `minions_only`: leave the pull request open and the ticket in its current status; Minions stops
  working on it, removes the ai-pilot label, and comments on both.

Call `delete_task` (or `delete_feature`) with `key`, `reason`, `mode`, and the optional `note` only
after the user has named a reason and a mode and explicitly confirmed. If `$ARGUMENTS` is empty, ask
for the ticket key and call nothing. Tasks that were waiting on the removed task are released.

After a successful call, report the returned `steps`. On `partial_failure`, list `details.steps`
verbatim and say that calling the same tool again retries only the failed steps. If it says
`You do not have permission to delete this task.`, report that refusal and do not retry with a
different reason. On `in_progress`, another request is already running the removal: wait and check
again, do not call it twice.

To retry a removal that did not finish, call `delete_task` (or `delete_feature`) again directly with
the same key once the user asks. `get_task` does not show removed tasks, so do not look the task up
first. A retry keeps the mode the item was removed with.

## Restore a removed task or feature

Call `restore_task` (or `restore_feature` for an epic key) only after the user explicitly asks for
it. A full delete is reversed (the pull request is reopened if its branch still exists, and the
ticket moves back to its status before removal); a `minions_only` removal gets its ai-pilot label
back. Restoring a feature also restores the tasks removed with it; tasks removed separately stay
removed, and a task whose feature is still removed cannot be restored on its own (restore the
feature). Restored work comes back paused: tell the user to resume it with `resume_task` when
ready. The exception is a task whose pull request was merged after removal: it comes back as Done,
with nothing to resume. Tasks released by the removal are not made to wait on it again. On
`partial_failure`, list `details.steps` and say that calling the tool again retries them. On
`in_progress`, another request is already running it: wait, do not call it twice.

## Start over on a task

When a user asks to start a task over, call `get_task` first and confirm that it is a task rather than a
feature. Explain the two `reset_task` modes and ask which one they want:

- `plan` (default): discard Minions' plan and learned state while keeping the branch and pull request.
- `everything`: also close an open pull request unmerged and clear the branch and pull-request fields.

Start over re-reads the tracker's current title, description and `repo-*` labels and shows a preview
of title or repo changes before confirmation. If the labels name different repos, `plan` is refused:
choose `everything` to move the task to those repos.

Ask whether to resume `now` (Planning) or `later` (Backlog, paused), and obtain the user's explicit
confirmation before calling `reset_task` with the chosen `mode`, `resume`, and optional `note`. Do not
start over a Done task or one whose pull request is merged; relay the returned refusal. A partial failure
records its steps: report `details.steps` and say that `reset_task` with `retry: true` retries only failed
steps. On `in_progress`, another start-over or undo is already running; wait and do not call it twice.

## Features

- Read a feature with `get_feature` before advising or acting.
- Report `phase` and `paused` first.
- Relay an unavailable action's `reason` verbatim.
- Pass `expectedPlanVersion` from the last `get_feature` on every `add_feature_wave`.
- For caller-authored features, use either `planDocument` or 1–10 `waves` entries; set each wave's `verbatimSpec` independently when its text must be preserved as written.
- When feature-sized work already has a tracker ticket, call `preview_ticket` and confirm the ticket with the user, then call `create_feature` with `existingTicket` set to it: the ticket becomes the feature's epic, and no new epic is created. For an epic, ask which of `preview_ticket`'s `children` to include and whether any has its own spec. Give each included child a wave with its `childKey`: omit `description` to use the child's own text, or pass the spec as `description` with `verbatimSpec: true`. Waves without `childKey` create new tickets. Tell the user about every key in the returned `untouchedChildren`: those children were left out of the feature.
- For a feature across several repos, pass `create_feature` a `repos` array (2–5 entries, each with its own Merge into and Build from branches, the first the primary) instead of `repoId`, and give each wave the `repos` labels it changes; ask the user which repos each wave changes when it is not clear. With `existingTicket` on a GitHub issue, the issue's own repo must be the first entry.
- To bring a child the feature left out into it later, call `add_feature_wave` with a wave whose `childKey` is that child (from `preview_ticket` on the feature's epic key), with the same description rules as above.
- Land with `merge_feature` only after the user's explicit decision.

## Report status

Status reporting is read-only. Use `list_my_tasks` for the caller's own work and `list_tasks` for a request about someone else's work or a repo's work (pass `owner`/`creator` as the email the user supplies, or `"me"`; pass `repo` from `list_repos` when the user names one). When a result carries a non-null `nextCursor` and the user asks for more, call the same tool again with that `cursor`.

### Typed tool results

Every success result is typed by its published `outputSchema`. Read `structuredContent` when it is present (success results only), and do not re-derive or invent fields that the schema does not declare.

### Follow changes

When the user asks "what changed", "anything new since…", or to follow work, call `list_changes` with the `nextCursor` kept from earlier in the conversation, or the stored `serverTime` when the last `nextCursor` was null, instead of `list_my_tasks`. Keep the returned `nextCursor` (or `serverTime`) in the conversation for the next ask. Read detail ONLY for the keys returned: use `get_task` for a `task` change, `get_task_activity` for a `job` change, and `get_feature` for a `feature` change; never call `get_task` for a key not in the change list. Follow the polling guidance: no more than one `list_changes` per 60 seconds, `list_blockers` every few minutes, and no tight loops. `(kind, key, at)` is the idempotency key, so a repeated entry is not a new change.

### Change a task's owner

Call `get_task` and read `actions.setOwner`; if `allowed` is false, report the `reason` and call nothing. Otherwise state the task key and the new owner by name and call `set_task_owner` only after the user explicitly confirms that named owner.

Status reporting is read-only. Use the narrowest read needed:

- Use `get_task` for the current task state and summary. Read `paused`, `owner`, `actions`, and `blocked` from its result rather than inferring them from `status`; report a paused task as paused first and never as simply done or in progress. When `get_task.ci` is failing or pending, report its failing checks, commit, and run URL and say the code host blocks the merge until CI passes; when `blocked.type` is `ci_failed`, report that blocker too. Do not imply that auto-fix is enabled. When `blocked.ciFix` is present, report its failing checks, commit, count versus threshold, run URL, and the Approve auto-fix / Leave as-is choice. Include `urls.minions` whenever you report the task. Report an unavailable action with its `reason` verbatim instead of attempting it, and request `includeBuildPlan` only when the user asks about the plan.
- Use `list_my_tasks` row `url` when reporting a task from that list.
- Use `get_task_activity` for the lifecycle and action history.
- Use `get_test_runs` for recorded test-container commands and their output; pass `jobId` when inspecting one run.
- Use `get_job_log` **or** `get_task_comments` only when a run failed and its details are needed.

Do not use status checks as a pretext to change a task. A run marked `retrying` or `incomplete` is
recovering on its own; report that fact and do not manually retry it. If the live result is empty
or stale, say so and ask the user what they want to inspect rather than filling in missing facts.
`list_open_bugs` lists open bug reports read-only; it is restricted to super admins, so relay the
tool's error as the answer when it refuses. Super admins can reply with `reply_to_bug` and change
status with `set_bug_status`; both are super-admin only, and ask the user before either write.

For fleet-level questions — "how are the runs looking", "what is running", "what failed today" — call `get_pipeline_overview` (scope `mine` or `org`, `windowHours` 1–168, default 24) once instead of walking tasks one by one. Report tasks by status, runs by role and outcome with cost, active runs (call out any over 30 minutes), failures grouped by error summary, stuck queue rows, and the blocker count. Runs marked `retrying` or `incomplete` are self-recovering — report them, do not retry them. For detail on one blocked or failed ticket, use `list_blockers` or `/why <ticket>`. The overview is read-only. For "how are the repos doing" or "which repos have problems", super admins call `get_pipeline_health` (read-only; optional `day`, `repo`, `orgId`) for the daily per-repo health report, and relay the tool's error as the answer when it refuses.

## Diagnose a run

This flow is read-only. Read in this order: `get_task`, then `get_task_activity`, then `get_job_log`
for the newest entry in `jobs[]` (use that entry's `id` as `jobId`), and then `get_task_comments`. Read `paused`, `owner`, `actions`, and `blocked` from `get_task` rather than inferring them from `status`; report a paused task as paused first and never as simply done or in progress. When `get_task.ci` is failing or pending, report its failing checks, commit, and run URL and say the code host blocks the merge until CI passes; when `blocked.type` is `ci_failed`, report that blocker too. Do not imply that auto-fix is enabled. When `blocked.ciFix` is present, report its failing checks, commit, count versus threshold, run URL, and the Approve auto-fix / Leave as-is choice. Include `urls.minions` in the report. Report an unavailable action with its `reason` verbatim instead of attempting it, and request `includeBuildPlan` only when the user asks about the plan.
Report the run's agent role, outcome/status, recorded `errorSummary`, the agent's own verification
lines quoted from its `[<role>-bot]` comment, and exactly one next action the user can take (an
existing command or a web-app step). When no run failed, report the latest run the same way. A
`retrying` or `incomplete` run is self-recovering: report it and do not re-dispatch, pause, or retry.
If a read returns empty or an error, say so and stop; never guess a status, job id, or option label.

## Register a repository

Only when the repository is not yet in Minions. Never type a coordinate from memory - choose one
from a live listing, because a mistyped coordinate registers cleanly and then fails when an agent
tries to clone it.

1. Call `list_code_connections` to see which code providers the organization has connected.
2. Call `list_provider_repos` for the chosen provider with that provider's scope
(`githubInstallationId` / `gitlabGroupPath` / `bitbucketWorkspace` / `adoProject`, plus `adoOrgUrl`
from `azureDevOpsConnections` when more than one Azure DevOps organization is connected). Narrow with
`query` when `truncated` is true rather than asking for a larger page. A row with `alreadyAdded`
is already registered: report its `label` instead of offering to add it again.
3. Read the result honestly. `connected: false` means connect the provider first. A non-null
`error` means the list could not be vouched for - say so rather than reporting the repository as
absent. For GitHub, `cache.fetchedAt` is when that list was last refreshed and `cache.neverFetched`
means it has never been, so say when the listing may be stale.
4. Confirm the chosen repository with the user, then call `add_repo` with the row's `identifier`
as that provider's coordinate and its `defaultBranch` (for Azure DevOps, the same `adoOrgUrl` and
`adoProject` the listing used). Never substitute a guessed branch for a
null `defaultBranch`; ask instead.
5. Report that initial ingest has been queued and that the repository is not usable for work
until it completes.

## Set up a repository

Call the read-only `get_repo_setup` tool for the selected repo and use its live result. Do not
write repository settings until the user explicitly confirms the specific changes. After confirmation,
walk `add_repo` → `set_repo_settings` (stack label first, from `list_stack_labels`) → `set_repo_branches` → `set_repo_scripts`
(MIN-2958) → `set_repo_secret` → `get_repo_setup` to confirm `dispatchable`. After significant architectural changes, or when `get_repo_setup` shows a failed or skipped ingest, offer `ingest_repo` and call it only after the user confirms; it queues the background regeneration and reports its queue position. To remove a repository secret, call `list_repo_secrets`, confirm the exact secret list with the user, then call `delete_repo_secret`; check inherited organization secrets before deleting an override. Check each of the following:

1. **Stack label gate:** `stack_label_has_image` must be true. A repo without a stack label mapped
to a runner image is not dispatchable; do not promise that work will run until this is fixed in
the web app.
2. **Startup Script:** non-JavaScript dependencies and tools belong in the repo's Startup Script.
The built-in dependency installer handles JavaScript lockfiles; it is not a Python or other
language package installer. If a private dependency needs a credential, ask an organization admin where the credential lives (an environment variable, file, or OS keychain entry) and pass that reference (`env:NAME`, `file:PATH` or `keychain:SERVICE/ACCOUNT`) as the value of `set_repo_secret`; the Minions Claude Code plugin resolves it locally. Never ask the user to paste a credential into chat or put it in the repository.
Before storing it, ask whether the same credential is used by other repositories in the organization. If it is, store it once with `set_org_secret` (the same reference rules) with `scope: "all"`, or `scope: "selected"` and the `repoLabels` it serves, rather than once per repository; check `list_org_secrets` first, since an existing org secret may already cover it. A repository's own secret with the same kind and name overrides the org one for that repository.

3. **Build Script:** treat the Build Script as a list of checks to run, not as an installer.
Keep installation and verification separate when explaining setup.
4. **Live environment:** when the organization feature is enabled and a Docker host is registered, use `set_repo_settings.liveEnvironment` to choose whether tasks start the repository's compose file, its services, and its host. `get_repo_setup` reports the saved live-environment settings.

5. **CI auto-fix:** read the live `auto_fix_ci` setting and `ci_fix_confirm_threshold`. Explain
whether CI auto-fix is enabled, what threshold is configured for asking for confirmation, and that
an automatic fix must not be approved without the user's explicit decision. Do not assume a
threshold from a default: repository settings override it.
6. **Visual evidence:** screenshots are off for every repository until someone turns them on.
`get_repo_setup` reports the switch and the latest capture check, which proves screenshots work on
the repository's runner image. Offer `run_capture_check` when no check has run or the last one is
out of date, and call it only after the user confirms; it queues the check. Turn screenshots on with
`set_repo_settings` and `visualEvidenceEnabled` only after the user confirms and only while the latest
check passed; the server refuses it otherwise. A check that reports the stack is not supported
cannot be fixed by retrying.
7. **MINIONS.md:** when drafting repository guidance, put anything that applies to every agent
under a `General` section, then add a distinct section per role only where the guidance differs:
`Planner`, `Plan Reviewer`, `Builder`, `Test Author`, and `Reviewer`. `General` reaches every role,
including one with no section of its own. Do not rely on text above the first heading instead: that
preamble ends at the first unrecognised heading, and a document title is an unrecognised heading, so
guidance placed there is discarded. Keep the guidance grounded in that repository's actual commands
and conventions; do not copy connection instructions into it.

Report missing setup facts and point the user to the web application for settings changes. This
skill can explain and check setup, but it cannot edit repo settings.

## Update the plugin

When the user asks to update the plugin, or accepts the SessionStart version notice (including an
`additionalContext` line reading `Minions plugin version check`), run `claude plugin update minions@minions`
via the shell, report the command's result verbatim, and tell the user to run `/reload-plugins` or
start a new session for the update to take effect. Never run `claude plugin update` unasked, and run
no other `claude plugin` subcommand as part of this job.
