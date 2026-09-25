# Audit outbox concurrency

PG16.15 runtime smoke: 10 pending rows, 4 concurrent relay loops.

Result: all 10 published exactly once and no duplicate `audit_events` rows.
The outbox UUID is the sink UUID, `dedupe_key` is unique, and claims use
`FOR UPDATE SKIP LOCKED` with a transaction-wide publish transition.
