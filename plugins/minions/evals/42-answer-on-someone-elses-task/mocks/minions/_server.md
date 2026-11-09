---
type: agent
tools: [list_blockers, get_task, answer_clarification]
abort_when: |
  - Abort if the assistant refuses to answer or says the user cannot act because the task owner is not the user.
---

Simulate the Minions MCP server for a clarification on DEMO-50.

- When `list_blockers` is called without a `key`, including the default scope, return exactly `{"blockers": []}`.
- When `list_blockers` is called with `key: "DEMO-50"`, return one clarification blocker:
  `{"blockers":[{"type":"clarification","key":"DEMO-50","storyId":50,"clarificationId":"clarification-50","question":"Which rollout window should we use?","choices":[{"label":"First option","value":"first"},{"label":"Second option","value":"second"}],"url":"https://minions.example/tasks/DEMO-50","action":{"canAct":true}}]}`.
- When `get_task` is called for DEMO-50, return a task whose owner is `{"name":"Service Account","isYou":false}` and whose actions permit answering the clarification.
- When `answer_clarification` is called for DEMO-50, return a successful result. The answer may identify the first choice as `first` or `First option`.
