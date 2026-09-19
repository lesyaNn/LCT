"""Task queue: Redis hash in prod, in-process mirror for demo/tests.

Contract (P0-4 fix):
* routers enqueue a job and record its lifecycle
  (queued -> running -> done | failed) — a job NEVER stays "queued"
  forever after an attempt;
* ``job_failed`` exists alongside ``job_done`` (previously an exception
  in ``execute_import`` left the job "queued" with no trace);
* ``idempotency_key`` dedups repeated POSTs (same file + mapping +
  options returns the existing job instead of a duplicate insert);
* jobs persist in Redis (``rtk:jobs`` hash, 24h TTL) so a restart does
  not lose status; the in-process dict is only a fallback mirror and
  every fallback is logged (no silent ``except: pass``).
"""
import json
import logging
import time
import uuid

from app.infrastructure import redis as r

logger = logging.getLogger("rtk")

QUEUE_KEY = "rtk:jobs"
RESULT_TTL_SECONDS = 24 * 3600
_local_jobs: dict[str, dict] = {}


def _store(job: dict) -> None:
    _local_jobs[job["id"]] = job
    client = r.get_client()
    if client is None:
        return
    try:
        client.hset(QUEUE_KEY, job["id"], json.dumps(job, default=str))
        client.expire(QUEUE_KEY, RESULT_TTL_SECONDS)
    except Exception:
        logger.warning("redis hset failed for job %s — local mirror only", job["id"])


def _load(job_id: str) -> dict | None:
    client = r.get_client()
    if client is not None:
        try:
            raw = client.hget(QUEUE_KEY, job_id)
            if raw:
                return json.loads(raw)
        except Exception:
            logger.warning("redis hget failed for job %s — trying local mirror", job_id)
    return _local_jobs.get(job_id)


def enqueue(job_type: str, payload: dict) -> str:
    key = payload.get("idempotency_key")
    if key:
        for job in list(_local_jobs.values()):
            if job.get("payload", {}).get("idempotency_key") == key and job.get("status") in (
                "queued", "running", "done",
            ):
                return job["id"]
        client = r.get_client()
        if client is not None:
            try:
                for raw in client.hvals(QUEUE_KEY):
                    job = json.loads(raw)
                    if job.get("payload", {}).get("idempotency_key") == key and job.get(
                        "status"
                    ) in ("queued", "running", "done"):
                        _local_jobs[job["id"]] = job
                        return job["id"]
            except Exception:
                logger.warning("redis idempotency scan failed — proceeding without dedup")
    job_id = uuid.uuid4().hex[:12]
    job = {
        "id": job_id,
        "type": job_type,
        "payload": payload,
        "status": "queued",
        "created_at": time.time(),
    }
    _store(job)
    client = r.get_client()
    if client is not None:
        try:
            client.rpush(QUEUE_KEY + ":pending", json.dumps(job, default=str))
        except Exception:
            logger.warning("redis rpush failed for job %s — worker must use local mirror", job_id)
    return job_id


def job_status(job_id: str) -> dict | None:
    return _load(job_id)


def job_running(job_id: str) -> None:
    job = _load(job_id) or {"id": job_id, "type": "unknown", "payload": {}}
    job["status"] = "running"
    _store(job)


def job_done(job_id: str, result: dict):
    job = _load(job_id) or {"id": job_id, "type": "unknown", "payload": {}}
    job.update(status="done", result=result)
    _store(job)


def job_failed(job_id: str, error: str) -> None:
    job = _load(job_id) or {"id": job_id, "type": "unknown", "payload": {}}
    job.update(status="failed", error=error)
    _store(job)


def dequeue() -> dict | None:
    client = r.get_client()
    if client is not None:
        try:
            raw = client.lpop(QUEUE_KEY + ":pending")
            if raw:
                job = json.loads(raw)
                job["status"] = "running"
                _store(job)
                return job
        except Exception:
            logger.warning("redis dequeue failed — trying local mirror")
    for job in _local_jobs.values():
        if job["status"] == "queued":
            job["status"] = "running"
            _store(job)
            return job
    return None
