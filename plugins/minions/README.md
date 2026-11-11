# Minions Claude Code plugin

## Secret references

When setting a repository secret, provide a local reference rather than pasting the credential into chat. Use `env:NAME` for an environment variable, `file:PATH` for a UTF-8 file, or `keychain:SERVICE/ACCOUNT` for an operating-system keychain entry. macOS uses Keychain Access, Linux uses Secret Service (`secret-tool`), and Windows uses Credential Manager, where the generic credential's target name is the literal `SERVICE/ACCOUNT` (for example `cmdkey /generic:npm/ci /user:ci /pass`). The plugin resolves and stages the value locally, then asks for confirmation before writing it to Minions.

Never put a credential in a prompt or transcript.

## What this plugin installs

The plugin installs a `minions` MCP server connection for Claude Code, the `minions` skill
(`skills/minions/SKILL.md` — filing work, clearing blocked work, reporting status, diagnosing runs,
setting up a repository), plus SessionStart version-check and PreToolUse secret-reference and local-attachment upload hooks in `hooks/hooks.json`, the task watch (PostToolUse and SessionStart hooks in `hooks/hooks.json` and a background monitor in `monitors/monitors.json`), and twenty slash commands:

- `/task` — File a work request with Minions
- `/unblock` — Review and unblock Minions work
- `/status` — Report Minions work status
- `/runs` — Report how Minions runs are looking
- `/reports` — Report Minions usage and analytics numbers
- `/setup-repo` — Set up a repository for Minions
- `/spec` — File an already-written spec with Minions verbatim
- `/why` — Explain what happened on a Minions ticket
- `/fix-ci` — Review a waiting CI auto-fix and decide it
- `/answer` — Answer a Minions clarification question
- `/merge` — Merge a Minions task that is ready
- `/depends` — Make one Minions task wait on another
- `/pause` — Pause a Minions task
- `/resume` — Resume a paused Minions task
- `/delete` — Delete a Minions task or feature
- `/restore` — Restore a removed Minions task or feature
- `/watch` — Watch a Minions task and alert me when it needs me
- `/unwatch` — Stop watching a Minions task
- `/bugs` — List open Minions bugs
- `/org` — Show or switch the organization this Minions connection works in.

## Watching tasks

The plugin can watch the tasks you hand off from a session and tell you the moment one needs
you: a question to answer, a blocker, a CI auto-fix to decide, a handback or PR feedback, a
sign-off, CI failing at review, a task paused too long, or work ready for you to merge. When one
does, Claude sends a desktop notification (skipped while you are at the terminal), shows what the
task needs with its full context, and offers the action. Nothing is changed without your answer.

- **Starting.** After you create, adopt, start or resume a task, Claude offers to watch it.
  `/watch [ticket key]` starts one any time, and `/unwatch [ticket key]` stops it. A watch ends
  on its own when the task merges, reaches Done or is removed, with one line saying so.
- **Settings** (`/plugin configure minions`): **Watch tasks** is `ask` (the default: offer
  first), `auto` (start without asking) or `off`. **Watch reminder (minutes)** repeats the alert
  while the same thing still needs you, every 60 minutes by default; `0` turns reminders off.
  A watch keeps the reminder setting it started with: a change applies from the next `/watch`
  or the next task Claude starts watching for you.
- **Also reported, without a notification:** a watched task now waiting on another task, and a
  watched task finishing.
- **Next session.** Watches belong to the open Claude Code window: `/clear`, `/compact` and
  `/resume` keep them running. When you start Claude Code again in the same folder, Claude
  offers to keep watching the tasks the last session left open.
- **How it works.** A background monitor (`monitors/monitors.json`, `hooks/watch_poller.py`)
  asks Minions about the watched tasks once a minute and prints only when one changes in a way
  that matters, so a quiet watch costs nothing. It uses a read-only watch token from the
  `watch_tasks` tool, valid 12 hours and accepted only by `GET /api/mcp/watch`; the plugin
  keeps it in its data folder (`watch/<session id>.json`) and out of the conversation, and asks
  for a new one when it expires. The monitor stops on its own once its Claude Code window is
  closed. A feature is not watched; `/watch` on a feature offers to watch its tasks.
- **Limits.** Alerts arrive only while a Claude Code session is open. Desktop notifications are
  not available on Bedrock, Vertex or Foundry; the watch still reports in the terminal there.

## Install from the marketplace

In Claude Code, add the marketplace and install the plugin:

```text
/plugin marketplace add charlieiq-ai/minions-claudeplugin
/plugin install minions@minions
```

Anyone working in this repository is offered the plugin automatically through the committed
`.claude/settings.json`.

## Use a non-production Minions host

The default MCP endpoint is `https://minions.charlieiq.ai/api/mcp`. To target staging or test,
run the same command used by the Minions profile page, replacing `<host>` with
`staging.minions.charlieiq.ai` or `test.minions.charlieiq.ai`:

```bash
claude mcp add --transport http minions https://<host>/api/mcp
```

You can also edit the `url` in a local copy of `.mcp.json`.

## Version check on session start

On every `SessionStart`, the hook compares the installed `plugin.json` version with the one served by your Minions host's `/api/plugin/version` (the host from your `minions` MCP configuration, else production). It prints a notice only when a newer version exists and says nothing when you are current or offline; it asks the server at most once every 24 hours and repeats a pending notice from its cache in between. It never runs the update itself — run `claude plugin update minions@minions` and then `/reload-plugins`, or ask Claude to run it.

## Run the developer-request eval suite

The plugin includes 42 developer-request cases under `evals/`. They exercise filing work,
clearing blockers, reporting status, diagnosing runs, repository setup, plugin updates, and the destructive-action safety gate.
Each case has an expectation and a mechanical prohibition; MCP responses come from local mocks,
so the suite does not contact a production Minions server or require a real ticket.

From the repository root, run one inexpensive pass with:

```bash
claude plugin eval ./plugins/minions --mocks record --runs 1 --no-publish
```

Use `--verbose` to inspect tool traces while developing a case. The command writes an HTML report
and `aggregate-result.json` below `plugins/minions/evals/results/` by default. Open the HTML report
to review each case's expectation/prohibition grader and its trace; a score of `1` means all
configured graders passed. Pass `--output-dir <path>` or `--report <path>` when you need a stable
artifact location. Keep `evals/case-index.yaml` in sync with the case directories.

The suite intentionally uses placeholder repositories, branches, and ticket keys. Do not run it
with `--mocks off` unless you deliberately want to authorize the real MCP server.

## Migration note

Personal permission allow-lists and `additionalDirectories` belong in
`.claude/settings.local.json`. If you already have an untracked `.claude/settings.json`, move
its contents to `.claude/settings.local.json` (or delete the file) before pulling this change.
Otherwise, `git pull` fails with `untracked working tree file '.claude/settings.json' would be
overwritten`. The committed settings file is shared and stays minimal.
