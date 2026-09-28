# Minions Claude Code plugin

## What this plugin installs

The plugin installs a `minions` MCP server connection for Claude Code, the `minions` skill
(`skills/minions/SKILL.md` — filing work, clearing blocked work, reporting status, diagnosing runs,
setting up a repository), plus a SessionStart version-check hook in `hooks/hooks.json` that helps users update it, and sixteen slash commands:

- `/task` — File a work request with Minions
- `/unblock` — Review and unblock Minions work
- `/status` — Report Minions work status
- `/runs` — Report how Minions runs are looking
- `/setup-repo` — Set up a repository for Minions
- `/spec` — File an already-written spec with Minions verbatim
- `/why` — Explain what happened on a Minions ticket
- `/fix-ci` — Review a waiting CI auto-fix and decide it
- `/answer` — Answer a Minions clarification question
- `/merge` — Merge a Minions task that is ready
- `/depends` — Make one Minions task wait on another
- `/pause` — Pause a Minions task
- `/resume` — Resume a paused Minions task
- `/delete` — Delete a Minions task
- `/bugs` — List open Minions bugs
- `/org` — Show or switch the organization this Minions connection works in.

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
