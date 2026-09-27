"""Deprecated alias: use ``app.infrastructure.keydb`` instead.

``app.infrastructure.redis`` теперь является тем же объектом модуля, что и
``app.infrastructure.keydb`` (KeyDB wire-совместим с Redis, клиент тот же
``redis-py``). Оставлено, чтобы старые импорты
``from app.infrastructure import redis`` продолжали работать без правок.
Новые импорты — напрямую ``from app.infrastructure import keydb``.
"""
import sys

import app.infrastructure.keydb as _keydb

sys.modules[__name__] = _keydb
