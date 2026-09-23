"""Optional durable queue recovery: python -m app.workers.report_jobs [--once].

Run on the same shared P4_REPORT_DIRECTORY as the API. Claims use SQL compare-
and-swap, so duplicate dispatch by an API BackgroundTask is safe. No changes to
the legacy import worker/queue (Dev-3's ownership).
"""

import argparse
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from sqlalchemy import select, update

from app.db.session import SessionLocal
from app.models.report_job import ReportJob
from app.modules.report_jobs.service import cleanup_expired, run_job, utcnow


def run_once() -> int:
    with SessionLocal() as db:
        # A crashed process cannot leave a job building forever. Do not retry
        # automatically: renderer idempotence is not part of Dev-1's contract.
        db.execute(
            update(ReportJob)
            .where(
                ReportJob.status == "building",
                ReportJob.started_at < utcnow() - timedelta(minutes=30),
            )
            .values(
                status="failed",
                completed_at=utcnow(),
                error_message="Report worker timed out. Submit a new request.",
            )
        )
        db.commit()
        ids = list(
            db.scalars(
                select(ReportJob.id)
                .where(
                    ReportJob.status == "queued",
                    ReportJob.expires_at > utcnow(),
                )
                .order_by(ReportJob.created_at)
                .limit(20)
            )
        )
    with ThreadPoolExecutor(max_workers=4) as pool:
        return sum(pool.map(run_job, ids))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    next_cleanup = 0.0
    while True:
        if time.monotonic() >= next_cleanup:
            cleanup_expired()
            next_cleanup = time.monotonic() + 86400
        run_once()
        if args.once:
            break
        time.sleep(2)


if __name__ == "__main__":
    main()
