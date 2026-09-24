#!/usr/bin/env python3
"""P5-17-01: smoke-тест полного стека CRM (только stdlib, без установки пакетов).

Проверяет РЕАЛЬНЫЙ контракт (см. backend/app/api/router.py):
  1. GET /health (liveness, без префикса)
  2. GET /api/v1/auth/me (токен валиден)
  3. GET /api/v1/universities (список, JSON-массив)
  4. GET /api/v1/universities/{id}/passport?include=health_score,audit
  5. GET /api/v1/universities/health-score?ids=... (batch)
  6. POST /api/v1/reports (202) + poll GET /api/v1/reports/{job_id}
  7. GET /api/v1/workflow/instances/{id} + transition (только с --instance/--stage)

Аутентификация: --token <Keycloak access token> (скопировать из браузера
после логина во frontend; у клиента rtk-frontend нет direct grants, поэтому
логин паролем из скрипта невозможен — это ограничение realm, а не скрипта).

Запуск:
  python3 scripts/smoke_test.py --token <token> [--base http://localhost:8000]
  python3 scripts/smoke_test.py --token <token> --instance <uuid> --stage <uuid>
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


class Fail(Exception):
    pass


class Smoke:
    def __init__(self, base: str, token: str) -> None:
        self.base = base.rstrip("/")
        self.token = token
        self.university_id: str | None = None
        self.steps_ok = 0

    def req(self, method: str, path: str, body: dict | None = None):
        data = json.dumps(body).encode() if body is not None else None
        r = urllib.request.Request(
            self.base + path,
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json",
                **({"Content-Type": "application/json"} if body is not None else {}),
            },
        )
        try:
            with urllib.request.urlopen(r, timeout=30) as resp:
                raw = resp.read().decode()
                return resp.status, (json.loads(raw) if raw else None)
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()[:500]

    def check(self, name: str, cond: bool, detail: str = "") -> None:
        if not cond:
            raise Fail(f"{name}: {detail}")
        self.steps_ok += 1
        print(f"  PASS {name}" + (f" ({detail})" if detail else ""))

    def run(self, instance_id: str | None, stage_id: str | None) -> int:
        print("=== CRM Smoke Test ===")
        try:
            s, b = self.req("GET", "/health")
            self.check("health", s == 200, f"HTTP {s}")

            s, b = self.req("GET", "/api/v1/auth/me")
            self.check("auth/me", s == 200, f"HTTP {s} user={(b or {}).get('username') if isinstance(b, dict) else b}")

            s, b = self.req("GET", "/api/v1/universities")
            ok = s == 200 and isinstance(b, list) and len(b) > 0
            self.check("list universities", ok, f"HTTP {s} count={len(b) if isinstance(b, list) else '?' }")
            assert isinstance(b, list)
            first = b[0]
            self.university_id = str(first.get("id"))
            ids = ",".join(str(u.get("id")) for u in b[:10])

            s, b = self.req(
                "GET",
                f"/api/v1/universities/{self.university_id}/passport"
                "?include=" + urllib.parse.quote("health_score,audit"),
            )
            self.check("passport", s == 200, f"HTTP {s}")

            s, b = self.req("GET", "/api/v1/universities/health-score?ids=" + urllib.parse.quote(ids))
            self.check("health-score batch", s == 200, f"HTTP {s}")

            s, b = self.req(
                "POST",
                "/api/v1/reports",
                {"format": "xlsx", "filters": {}, "columns": None},
            )
            self.check("report create", s == 202, f"HTTP {s}")
            job_id = (b or {}).get("job_id") if isinstance(b, dict) else None
            if job_id:
                ready = False
                for _ in range(30):
                    time.sleep(2)
                    s2, b2 = self.req("GET", f"/api/v1/reports/{job_id}")
                    st = (b2 or {}).get("status") if isinstance(b2, dict) else None
                    if st == "ready":
                        ready = True
                        break
                    if st == "failed":
                        break
                self.check("report ready", ready, f"job={job_id}")
            else:
                print("  SKIP report poll (no job_id; worker может быть остановлен)")

            if instance_id:
                s, b = self.req("GET", f"/api/v1/workflow/instances/{instance_id}")
                self.check("workflow read", s == 200, f"HTTP {s}")
                if stage_id:
                    s, b = self.req(
                        "POST",
                        f"/api/v1/workflow/instances/{instance_id}/transition",
                        {"target_instance_stage_id": stage_id, "comment": "smoke test"},
                    )
                    self.check("workflow transition", s == 200, f"HTTP {s}")
                else:
                    print("  SKIP transition (no --stage)")
            else:
                print("  SKIP workflow (no --instance; список инстансов API не отдаёт)")
        except Fail as e:
            print(f"  FAIL {e}")
            print(f"=== SMOKE FAILED ({self.steps_ok} ok) ===")
            return 1
        print(f"=== SMOKE PASSED ({self.steps_ok} ok) ===")
        return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="CRM smoke test (P5-17-01)")
    ap.add_argument("--token", required=True, help="Keycloak access token (из браузера)")
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--instance", default=None, help="workflow instance UUID (опционально)")
    ap.add_argument("--stage", default=None, help="target instance-stage UUID (опционально)")
    a = ap.parse_args()
    return Smoke(a.base, a.token).run(a.instance, a.stage)


if __name__ == "__main__":
    sys.exit(main())
