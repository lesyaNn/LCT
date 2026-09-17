"""Task queue: Redis list in prod, synchronous in-process fallback for demo.

HTTP never waits for heavy work: routers enqueue, workers execute.
"""
import json
import uuid

from app.infrastructure import redis as r

QUEUE_KEY = "rtk:jobs"
_local_jobs: dict[str, dict] = {}


def enqueue(job_type: str, payload: dict) -> str:
    job_id = uuid.uuid4().hex[:12]
    job = {"id": job_id, "type": job_type, "payload": payload, "status": "queued"}
    _local_jobs[job_id] = job
    try:
        if r._client:
            r._client.rpush(QUEUE_KEY, json.dumps(job))
    except Exception:
        pass
    # Demo fallback: mark ready; worker endpoint picks it up synchronously.
    return job_id


def job_status(job_id: str) -> dict | None:
    return _local_jobs.get(job_id)


def job_done(job_id: str, result: dict):
    if job_id in _local_jobs:
        _local_jobs[job_id].update(status="done", result=result)


def dequeue() -> dict | None:
    try:
        if r._client:
            raw = r._client.lpop(QUEUE_KEY)
            if raw:
                return json.loads(raw)
    except Exception:
        pass
    for job in _local_jobs.values():
        if job["status"] == "queued":
            job["status"] = "running"
            return job
    return None
