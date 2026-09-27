"""P5-14-01: нагрузка 50 параллельных пользователей (read-сценарии).

Сценарии по РЕАЛЬНОМУ контракту (urrlib-заготовка без locust не запускается;
для запуска: pip install locust):
  list universities (10) / passport (5) / workflow read (5) /
  comment (3) / report preview + statistics (2).

IDs подхватываются динамически: on_start тянет GET /api/v1/universities
и строит пул university_ids для passport/batch. Workflow/comment задачи
активны только при WORKFLOW_INSTANCE_IDS (API списка инстансов нет —
передать через env LOCUST_WF_IDS=uuid,uuid).

Запуск:
  locust -f backend/tests/load/locustfile.py --host=http://localhost:8000 \\
    -u 50 -r 10 -t 2m --headless

Цели: p95 < 500ms для list/passport/workflow-read, 0% 5xx.
"""
from __future__ import annotations

import os
import random

try:
    from locust import HttpUser, between, task
except ImportError:  # pragma: no cover - импорт только под locust
    HttpUser = object  # type: ignore[assignment,misc]

    def between(*_a, **_k):  # type: ignore[no-redef]
        return None

    def task(*_a, **_k):  # type: ignore[no-redef]
        def deco(fn):
            return fn

        return deco


def _wf_ids() -> list[str]:
    raw = os.getenv("LOCUST_WF_IDS", "")
    return [s.strip() for s in raw.split(",") if s.strip()]


WORKFLOW_INSTANCE_IDS = _wf_ids()


class CRMUser(HttpUser):  # type: ignore[valid-type,misc]
    wait_time = between(1, 3)
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
                CRMUser.university_ids = [str(u["id"]) for u in data[:20] if u.get("id")]
        except Exception:
            pass

    @task(10)
    def list_universities(self):
        self.client.get("/api/v1/universities", name="/universities")

    @task(5)
    def university_passport(self):
        if not self.university_ids:
            return
        uid = random.choice(self.university_ids)
        self.client.get(
            f"/api/v1/universities/{uid}/passport?include=audit",
            name="/universities/{id}/passport",
        )

    @task(5)
    def workflow_read(self):
        if not WORKFLOW_INSTANCE_IDS:
            return
        wf_id = random.choice(WORKFLOW_INSTANCE_IDS)
        self.client.get(f"/api/v1/workflow/instances/{wf_id}", name="/workflow/read")

    @task(3)
    def add_comment(self):
        if not WORKFLOW_INSTANCE_IDS:
            return
        wf_id = random.choice(WORKFLOW_INSTANCE_IDS)
        self.client.post(
            f"/api/v1/workflow/instances/{wf_id}/comments",
            json={"content": f"Load comment {random.randint(1, 100000)}"},
            name="/workflow/comments",
        )

    @task(2)
    def report_preview(self):
        """The filter-change path the ТЗ caps at 1 second."""
        payload = {"filters": {}, "columns": None, "limit": 50}
        self.client.post(
            "/api/v1/reports/preview", json=payload, name="/reports/preview"
        )

    @task(2)
    def report_statistics(self):
        self.client.post(
            "/api/v1/reports/statistics", json={"filters": {}},
            name="/reports/statistics",
        )
