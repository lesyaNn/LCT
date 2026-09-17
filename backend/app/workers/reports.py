"""Background workers (§18): reports / imports / integrations."""
import io

from app.infrastructure import task_queue


def run_reports_once() -> int:
    handled = 0
    while True:
        job = task_queue.dequeue()
        if not job:
            break
        if job["type"] == "export_xlsx":
            rows = job["payload"].get("rows", [])
            try:
                import openpyxl
                wb = openpyxl.Workbook()
                ws = wb.active
                if rows:
                    ws.append(list(rows[0].keys()))
                    for r in rows:
                        ws.append(list(r.values()))
                buf = io.BytesIO()
                wb.save(buf)
                task_queue.job_done(job["id"], {"bytes": len(buf.getvalue()), "rows": len(rows)})
            except Exception as e:  # pragma: no cover
                task_queue.job_done(job["id"], {"error": str(e)})
        elif job["type"] == "notify":
            task_queue.job_done(job["id"], {"sent": True})
        else:
            task_queue.job_done(job["id"], {"skipped": True})
        handled += 1
    return handled


def run_imports_once() -> int:
    return 0


def run_integrations_once() -> int:
    return 0


if __name__ == "__main__":
    import time
    while True:
        n = run_reports_once()
        time.sleep(2 if n == 0 else 0)
