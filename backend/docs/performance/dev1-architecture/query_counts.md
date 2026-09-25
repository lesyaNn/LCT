# Query-count results

Environment: PostgreSQL 16.15, representative fixture with 100 universities and
100 materialized `health_score_current` rows.

Measured SELECT counts (repeated with N=5 and N=100; values were identical):

- catalog health count/page: **3** (count, page, and the ORM refresh query); N=5: 3, N=100: 3.
- ranking window + total: **2**; N=5: 2, N=100: 2.
- analytics dataset `fetch_rows` (`university`, `health_score`): **1**; N=5: 1, N=100: 1.
- streamed dataset `iterate_rows` (same columns): **1**; N=5: 1, N=100: 1.

Health collection work is therefore bounded and does not grow linearly with
the number of universities. The catalog extra statement is ORM bookkeeping,
not a per-row query.
