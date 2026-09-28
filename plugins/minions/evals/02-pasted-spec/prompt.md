Paste this exact engineering specification into the task without rewriting it:

Context: The service emits duplicate health events.
Goal: Deduplicate health events by event id.
Acceptance criteria:
- Events with the same id are emitted once.
- Events with different ids remain separate.
Technical Notes: Add the deduplication at the event boundary.

Do not summarize or improve the text.