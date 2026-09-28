# Minions developer-request evals

This directory contains the 42 stable developer-request cases for the Minions plugin. Each case
has a realistic user prompt, an expectation grader, and a prohibition grader. The suite exercises
the six jobs in `skills/minions/SKILL.md` without contacting production.

Run from the repository root:

```bash
claude plugin eval ./plugins/minions --mocks record --runs 1 --no-publish
```

Use `--verbose` while authoring a case. Results are written below
`plugins/minions/evals/results/` (or the output directory supplied with `--output-dir`). The HTML
report and JSON aggregate show each case's grader result, tool trace, and final response. A score
of `1` means every grader passed; use the failed grader's target and trace to distinguish a wrong
tool call from a wrong explanation. `--mocks record` supplies recorded MCP stand-ins and does not
start the production Minions server. Cases 32-ambiguous-ticket-key and 33-already-adopted-ticket use per-case preview mocks to exercise
ambiguous and already-adopted ticket outcomes.

The cases intentionally use placeholder repositories, branches, and ticket keys. No case needs a
real ticket or production credential. Keep the case index in `case-index.yaml` in sync when adding
or renaming a case.
