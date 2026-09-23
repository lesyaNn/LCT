from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Response
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.modules.analytics.integration import FilterProvider, get_filter_provider
from app.modules.report_jobs import service
from app.modules.report_jobs.schemas import JobAccepted, JobRead, ReportRequest

router = APIRouter(prefix="/reports", tags=["report-jobs"])


@router.post("", status_code=202, response_model=JobAccepted)
def create_report(
    request: ReportRequest,
    tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
    provider: FilterProvider = Depends(get_filter_provider),
    renderer=Depends(service.get_renderer),
):
    job = service.submit(db, request, user, provider, renderer)
    # A sync task is offloaded to Starlette's thread pool, not the async API loop.
    # The durable queue can also be drained by the standalone recovery worker.
    tasks.add_task(service.run_job, job.id, provider=provider, renderer=renderer)
    return JobAccepted(job_id=job.id)


@router.get("/{job_id}", response_model=JobRead)
def report_status(
    job_id: UUID,
    response: Response,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    job = service.get_job(db, job_id, user)
    response.headers["Cache-Control"] = "no-store"
    if job.status in {"queued", "building"}:
        response.headers["Retry-After"] = "3"
    return service.describe(job)


@router.get("/{job_id}/download", response_class=FileResponse)
def download_report(
    job_id: UUID, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)
):
    job = service.get_job(db, job_id, user)
    return FileResponse(
        service.downloadable(job),
        media_type=service.MEDIA_TYPES[job.format],
        filename=f"report_{job.id}.{job.format}",
        headers={"Cache-Control": "no-store"},
    )
