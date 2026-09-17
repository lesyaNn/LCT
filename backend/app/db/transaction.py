"""Transactional helper: `with transaction(db): ...`."""
from contextlib import contextmanager


@contextmanager
def transaction(db):
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
