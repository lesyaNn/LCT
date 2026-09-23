"""CI entry point for Dev-2. --require-postgres prevents a misleading skip-only pass."""

import argparse
import os
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-postgres", action="store_true")
    args = parser.parse_args()
    if args.require_postgres and not os.getenv("TEST_DATABASE_URL", "").startswith("postgresql"):
        raise SystemExit("A dedicated PostgreSQL TEST_DATABASE_URL is required (schema is reset)")
    raise SystemExit(
        subprocess.call(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "tests/test_p4_dev2_analytics.py",
                "tests/test_p4_dev2_jobs.py",
                "tests/test_p4_dev2_postgres.py",
            ],
            cwd=Path(__file__).resolve().parent.parent,
            env={**os.environ, "PYTHONPATH": "."},
        )
    )


if __name__ == "__main__":
    main()
