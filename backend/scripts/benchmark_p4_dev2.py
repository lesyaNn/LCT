"""P4-13-01 opt-in benchmark against an ISOLATED running integration stack.

Reads P4_BENCHMARK_URL (default http://127.0.0.1:8000) and P4_BENCHMARK_TOKEN.
Requires P4_BENCHMARK_ALLOW_WRITES=1: creates ten report jobs/artifacts. Never
run on production. Exporters/shared filter must already be connected. Results
go to stdout as JSON; tokens/response error bodies are never printed.
"""

import asyncio
import json
import os
import statistics
import time

import httpx


async def benchmark():
    if os.getenv("P4_BENCHMARK_ALLOW_WRITES") != "1":
        raise SystemExit("Set P4_BENCHMARK_ALLOW_WRITES=1 for a disposable test stack")
    token = os.getenv("P4_BENCHMARK_TOKEN")
    if not token:
        raise SystemExit("Set P4_BENCHMARK_TOKEN (Keycloak access token)")
    results = {}
    async with httpx.AsyncClient(
        base_url=os.getenv("P4_BENCHMARK_URL", "http://127.0.0.1:8000"),
        headers={"Authorization": f"Bearer {token}"},
        timeout=60,
    ) as client:

        async def timed(method, path, **kwargs):
            start = time.perf_counter()
            response = await client.request(method, path, **kwargs)
            if response.is_error:
                raise RuntimeError(f"{method} {path}: HTTP {response.status_code}")
            return response, (time.perf_counter() - start) * 1000

        for name in ("overview", "matrix"):
            _, first = await timed("GET", f"/api/v1/analytics/{name}")
            samples = [(await timed("GET", f"/api/v1/analytics/{name}"))[1] for _ in range(10)]
            results[name] = {
                "first_ms": round(first, 2),
                "warm_p95_ms": round(sorted(samples)[9], 2),
                "warm_median_ms": round(statistics.median(samples), 2),
            }
        submitted = await asyncio.gather(
            *[
                timed(
                    "POST", "/api/v1/reports", json={"format": "json", "filters": {}, "columns": []}
                )
                for _ in range(10)
            ]
        )
        pending = {response.json()["job_id"] for response, _ in submitted}
        if len(pending) != 10 or any(response.status_code != 202 for response, _ in submitted):
            raise AssertionError("Expected ten independent 202 jobs")
        health_samples = []
        deadline = time.monotonic() + 180
        while pending:
            health_samples.append((await timed("GET", "/health"))[1])
            if time.monotonic() >= deadline:
                raise AssertionError("Report jobs timed out")
            for job_id in list(pending):
                response, _ = await timed("GET", f"/api/v1/reports/{job_id}")
                state = response.json()["status"]
                if state == "failed":
                    raise AssertionError("A report job failed (check server logs)")
                if state == "ready":
                    artifact, _ = await timed("GET", f"/api/v1/reports/{job_id}/download")
                    assert artifact.content
                    pending.remove(job_id)
            if pending:
                await asyncio.sleep(3)
        results["jobs"] = {
            "completed": 10,
            "max_submit_ms": round(max(t for _, t in submitted), 2),
            "max_health_ms": round(max(health_samples), 2),
        }
    print(json.dumps(results, indent=2))
    assert results["overview"]["warm_p95_ms"] < 100
    assert results["overview"]["first_ms"] < 500
    assert results["matrix"]["first_ms"] < 1000
    assert results["jobs"]["max_health_ms"] < 1000


if __name__ == "__main__":
    asyncio.run(benchmark())
