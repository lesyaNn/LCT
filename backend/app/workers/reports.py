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
    """Execute queued ``xlsx_import`` jobs out-of-band (P0-4 worker path).

    Each job payload carries file_id + mapping + options (written by the
    router), so the worker can run the same ``execute_import`` without HTTP.
    Returns the number of jobs handled.
    """
    from app.db.session import SessionLocal
    from app.infrastructure import task_queue
    from app.modules.imports import service

    handled = 0
    while True:
        job = task_queue.dequeue()
        if not job:
            break
        if job.get("type") != "xlsx_import":
            task_queue.job_done(job["id"], {"skipped": True})
            handled += 1
            continue
        payload = job.get("payload", {})
        db = SessionLocal()
        try:
            summary = service.execute_import(
                db,
                payload["file_id"],
                payload.get("mapping", {}),
                update_existing=payload.get("update_existing", False),
                dry_run=payload.get("dry_run", False),
            )
        except service.ImportValidationError as exc:
            task_queue.job_failed(job["id"], str(exc))
        except Exception as exc:
            task_queue.job_failed(job["id"], f"{type(exc).__name__}: {exc}")
        else:
            task_queue.job_done(job["id"], summary)
        finally:
            db.close()
        handled += 1
    return handled


def run_integrations_once() -> int:
    return 0


if __name__ == "__main__":
    import time
    while True:
        n = run_reports_once()
        time.sleep(2 if n == 0 else 0)
