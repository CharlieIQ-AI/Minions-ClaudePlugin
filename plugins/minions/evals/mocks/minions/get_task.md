---
expect:
  key: string
---
{"key":"{{input.key}}","title":"Task status","status":"In Progress","repo":"repo-python","type":"story","prUrl":null,"parentKey":null,"blocked":{"type":"ci_confirm","summary":"`pytest-logic` failed on c36a61b with 12 failing tests, above this repo's threshold of 10, so the Minions paused before auto-fixing. Approve auto-fix to let the Minions try, or Leave as-is to handle it yourself.","ciFix":{"failingChecks":["pytest-logic"],"commitSha":"c36a61b","failingTestCount":12,"threshold":10,"runUrl":"https://github.com/example/repo/actions/runs/123","options":[{"action":"approve","label":"Approve auto-fix"},{"action":"dismiss","label":"Leave as-is"}]}},"urls":{"minions":"https://minions.invalid/tasks/42","tracker":"https://tracker.invalid/browse/{{input.key}}","pr":null}}
