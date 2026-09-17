from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.modules.workflow.schemas import ChangeStatus, StatusOut, TaskIn, TaskOut, WorkflowCreate, WorkflowOut
from app.modules.workflow.service import WorkflowService

router = APIRouter(prefix="/workflows", tags=["workflows"])
tasks_router = APIRouter(prefix="/tasks", tags=["tasks"])


def _svc(db: Session = Depends(get_db)) -> WorkflowService:
    return WorkflowService(db)


@router.get("/statuses", response_model=list[StatusOut])
def list_statuses(svc: WorkflowService = Depends(_svc),
                  _u: CurrentUser = Depends(get_current_user)):
    return svc.statuses()


@router.post("", response_model=WorkflowOut, status_code=201)
def create_workflow(data: WorkflowCreate, svc: WorkflowService = Depends(_svc),
                    _u: CurrentUser = Depends(get_current_user)):
    return svc.create(data)


@router.post("/{workflow_id}/status", response_model=WorkflowOut)
def change_status(workflow_id: int, data: ChangeStatus, svc: WorkflowService = Depends(_svc),
                  user: CurrentUser = Depends(get_current_user)):
    return svc.change_status(workflow_id, data.to_status_code, user.roles or [])


@tasks_router.post("", response_model=TaskOut, status_code=201)
def create_task(data: TaskIn, svc: WorkflowService = Depends(_svc),
                _u: CurrentUser = Depends(get_current_user)):
    return svc.create_task(data)


@tasks_router.post("/{task_id}/complete", response_model=TaskOut)
def complete_task(task_id: int, svc: WorkflowService = Depends(_svc),
                  _u: CurrentUser = Depends(get_current_user)):
    return svc.complete_task(task_id)
