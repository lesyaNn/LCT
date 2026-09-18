"""Thin wrapper: ``python scripts/seed_demo.py`` (P1-09-01 entry point).

Canonical implementation lives in ``app.db.seed`` (``python -m app.db.seed``).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.seed import main

if __name__ == "__main__":
    main()
