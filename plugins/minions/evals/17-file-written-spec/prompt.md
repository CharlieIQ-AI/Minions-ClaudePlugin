File this complete specification exactly as written, after checking it against the written-spec pre-flight. Use the live repository facts and ask me to confirm any choices before filing.

## Context
The service currently drops duplicate health events. Evidence:
- Duplicate event ids appear in the event stream.
- Consumers expect one event per id.

## Goal
Deduplicate health events by event id.

## Acceptance criteria
- AC1: Events with the same id are emitted once.
- AC2: Events with different ids remain separate.

## Coverage declaration
Failure paths: AC1
Authorization: N/A — no authorization change
Empty & loading states: N/A — no user interface

## Technical Notes
Add deduplication at the event boundary.

## Implementation outline
1. Track ids at the event boundary.
2. Emit only the first event for each id.

## Assumptions
The existing event id is stable.

## Dependencies
None.

## Blocks
None.

## Out of Scope
Changing event payloads.

## Test Plan
Test duplicate and distinct ids.

## Out of Scope for Tests
Load testing.

Use repo-python, Build from main, Merge into main, and enable auto-merge if the live settings allow it. Preserve this text as written.