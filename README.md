# Minions plugin for Claude Code

Connect Claude Code to [Minions](https://minions.charlieiq.ai) so you can file work, clear
blocked work, report status and set up repositories without leaving your terminal.

## Install

```text
/plugin marketplace add charlieiq-ai/minions-claudeplugin
/plugin install minions@minions
```

Then authenticate: the plugin adds an MCP connection to your Minions host and Claude Code
walks you through sign-in on first use. Every call is attributed to you and scoped to your
organization.

You do **not** need access to any private repository to install this.

## What you get

Slash commands for the everyday flow — `/task`, `/spec`, `/status`, `/unblock`, `/answer`,
`/fix-ci`, `/merge`, `/why`, `/runs`, `/bugs`, `/pause`, `/resume`, `/depends`, `/org`,
`/setup-repo`, `/delete` — plus a `minions` skill that teaches Claude the pipeline's rules,
and a session hook that tells you when a newer plugin version is available.

The plugin itself lives in [`plugins/minions/`](plugins/minions); see its
[README](plugins/minions/README.md) for configuration, the update check and how to point at
a non-production host.

## License

MIT. See [LICENSE](LICENSE).
