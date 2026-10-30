/minions:spec

## Context
The export button times out on large accounts. Evidence:
- Exports over 10,000 rows fail after 30 seconds.

## Goal
Stream large exports.

## Acceptance criteria
- AC1: An export of 50,000 rows completes without a timeout.
- AC2: An export of 10 rows still downloads as one file.

## Coverage declaration
Failure paths: AC1
Authorization: N/A — no authorization change
Empty & loading states: N/A — no user interface change

## Technical Notes
Stream rows from the export query.

## Implementation outline
1. Replace the buffered export with a stream.

## Assumptions
The export query supports a cursor.

## Dependencies
None.

## Blocks
None.

## Out of Scope
New export formats.

## Test Plan
Test 10-row and 50,000-row exports.

## Out of Scope for Tests
Load testing.
