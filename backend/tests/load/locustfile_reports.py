"""P5-14-02: нагрузка генерации отчётов — 10 параллельных запросов.

Самый тяжёлый endpoint: POST /api/v1/reports (202) -> poll статуса ->
GET /api/v1/reports/{job_id}/download. Фильтры валидны по контракту
ReportRequest (пустой UnifiedFilter + columns=None = все колонки).

Запуск:
  locust -f backend/tests/load/locustfile_reports.py \\
    --host=http://localhost:8000 -u 10 -r 2 -t 5m --headless

Цели: 100% успешных генераций, 0% 5xx, p95 < 60s (зависит от данных).
"""
from __future__ import annotations

import os
import time

try:
    from locust import HttpUser, between, task
except ImportError:  # pragma: no cover - импорт только под locust
    HttpUser = object  # type: ignore[assignment,misc]

    def between(*_a, **_k):  # type: ignore[no-redef]
        return None

    def task(fn=None, **_k):  # type: ignore[no-redef]
        return fn if fn else (lambda f: f)


class ReportUser(HttpUser):  # type: ignore[valid-type,misc]
    wait_time = between(5, 15)
    host = "http://localhost:8000"

    token: str = os.getenv("LOCUST_TOKEN", "")
    university_ids: list[str] = []

    def on_start(self):
        if self.token:
            self.client.headers.update({"Authorization": f"Bearer {self.token}"})
        try:
            resp = self.client.get("/api/v1/universities")
            data = resp.json()
            if isinstance(data, list):
                ReportUser.university_ids = [str(u["id"]) for u in data[:3] if u.get("id")]
        except Exception:
            pass

    @task
    def create_xlsx_report(self):
        with self.client.post(
            "/api/v1/reports",
            json={
                "format": "xlsx",
                "filters": {"university_ids": self.university_ids},
                "columns": None,
            },
            catch_response=True,
            name="/reports",
        ) as response:
            if response.status_code != 202:
                response.failure(f"Create failed: {response.status_code}")
                return
            try:
                job_id = response.json().get("job_id")
            except Exception:
                response.failure("No job_id in 202 response")
                return
            if not job_id:
                response.failure("Empty job_id")
                return
            for _ in range(30):
                time.sleep(2)
                poll = self.client.get(f"/api/v1/reports/{job_id}", name="/reports/{id}")
                if poll.status_code != 200:
                    response.failure(f"Poll failed: {poll.status_code}")
                    return
                try:
                    status = poll.json().get("status")
                except Exception:
                    response.failure("Bad poll JSON")
                    return
                if status == "ready":
                    dl = self.client.get(
                        f"/api/v1/reports/{job_id}/download", name="/reports/{id}/download"
                    )
                    if dl.status_code == 200:
                        response.success()
                    else:
                        response.failure(f"Download failed: {dl.status_code}")
                    return
                if status == "failed":
                    response.failure("Report job failed")
                    return
            response.failure("Report timeout (60s)")
