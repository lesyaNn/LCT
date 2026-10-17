"""Shared preview service. Call only AFTER the owning entity's access checks."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
from threading import BoundedSemaphore, Lock
from collections import OrderedDict
import time

from fastapi import HTTPException
from fastapi.responses import JSONResponse

from app.modules.workflow_attachments.storage import StorageError, StorageObjectNotFound

_slots = BoundedSemaphore(2)
_cache = OrderedDict()
_cache_lock = Lock()
MAX_BYTES = 50 * 1024 * 1024


def preview_response(storage, key: str, filename: str, offset: int = 0, source_factory=None):
    cache_key = (id(storage), key, filename, offset)
    with _cache_lock:
        cached = _cache.get(cache_key)
        if cached and time.monotonic() - cached[0] < 60:
            return JSONResponse(cached[1], headers={"Cache-Control": "no-store"})
    if not _slots.acquire(blocking=False):
        raise HTTPException(503, "Предпросмотр занят. Повторите попытку.")
    try:
        # Spool remotely stored files to a bounded temporary file, never RAM.
        with tempfile.TemporaryDirectory(prefix='crm-preview-') as directory:
            path = Path(directory) / ('source' + Path(filename).suffix.lower())
            total = 0
            deadline = time.monotonic() + 8
            with (source_factory() if source_factory else storage.open_stream(key)) as source, path.open('wb') as target:
                while chunk := source.read(64 * 1024):
                    total += len(chunk)
                    if total > MAX_BYTES or time.monotonic() > deadline:
                        return JSONResponse({"kind": "unsupported", "message": "Файл слишком большой для быстрого предпросмотра. Используйте скачивание."}, headers={"Cache-Control": "no-store"})
                    target.write(chunk)
            try:
                worker = Path(__file__).with_name('preview_worker.py')
                result = subprocess.run([sys.executable, str(worker), str(path), filename, str(offset)],
                                        capture_output=True, timeout=6, check=True)
                payload = json.loads(result.stdout)
            except (subprocess.SubprocessError, ValueError):
                payload = {"kind": "error", "message": "Не удалось подготовить предпросмотр за отведённое время. Файл можно скачать."}
            encoded_size = len(json.dumps(payload))
            if payload.get("kind") not in ("error", "unsupported"):
                with _cache_lock:
                    _cache[cache_key] = (time.monotonic(), payload, encoded_size)
                    _cache.move_to_end(cache_key)
                    while len(_cache) > 24 or sum(item[2] for item in _cache.values()) > 24 * 1024 * 1024:
                        _cache.popitem(last=False)
            return JSONResponse(payload, headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})
    except (StorageObjectNotFound, FileNotFoundError):
        raise HTTPException(404, "Файл недоступен") from None
    except StorageError:
        raise HTTPException(503, "Хранилище временно недоступно") from None
    finally:
        _slots.release()
