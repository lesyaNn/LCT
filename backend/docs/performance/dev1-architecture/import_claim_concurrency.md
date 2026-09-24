# Import claim concurrency

PG16.15 runtime smoke: 10 queued jobs, 4 concurrent claim loops.

Result: 10 unique claimed IDs, no duplicate claim, no lost eligible job.
The code path uses `FOR UPDATE SKIP LOCKED` plus an atomic status/attempt
update; stale claims are requeued until the three-attempt limit.
