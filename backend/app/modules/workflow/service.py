"""Workflow service: statuses live in DB, transitions validated (see §10)."""
from sqlalchemy.orm import Session

from app.core.exceptions import BadTransition, NotFound
from app.modules.workflow.models import Task, Workflow, WorkflowStatus, WorkflowTransition
from app.modules.workflow.schemas import TaskIn, WorkflowCreate

DEFAULT_STATUSES = [
    ("new", "Новый вуз", 0),
    ("contact", "Контакт установлен", 1),
    ("docs_requested", "Документы запрошены", 2),
    ("teachers_prep", "Подготовка преподавателей", 3),
    ("program_prep", "Подготовка программы", 4),
    ("ready", "Готов к запуску", 5),
    ("launched", "Программа запущена", 6),
]


def ensure_seed(db: Session):
    if db.query(WorkflowStatus).count() == 0:
        for code, name, pos in DEFAULT_STATUSES:
            db.add(WorkflowStatus(code=code, name=name, position=pos))
        db.commit()
        by_code = {s.code: s.id for s in db.query(WorkflowStatus).all()}
        codes = [c for c, _, _ in DEFAULT_STATUSES]
        for a, b in zip(codes, codes[1:]):
            db.add(WorkflowTransition(from_status_id=by_code[a], to_status_id=by_code[b]))
        db.commit()


class WorkflowService:
    def __init__(self, db: Session):
        self.db = db
        ensure_seed(db)

    def statuses(self) -> list[WorkflowStatus]:
        return self.db.query(WorkflowStatus).order_by(WorkflowStatus.position).all()

    def create(self, data: WorkflowCreate) -> Workflow:
        st = self.db.query(WorkflowStatus).filter_by(code=data.status_code).first()
        if not st:
            raise NotFound("Unknown status code")
        wf = Workflow(university_id=data.university_id, program_id=data.program_id, status_id=st.id)
        self.db.add(wf)
        self.db.commit()
        self.db.refresh(wf)
        return wf

    def change_status(self, workflow_id: int, to_code: str, user_roles: list[str]) -> Workflow:
        wf = self.db.get(Workflow, workflow_id)
        if not wf:
            raise NotFound("Workflow not found")
        target = self.db.query(WorkflowStatus).filter_by(code=to_code).first()
        if not target:
            raise NotFound("Unknown target status")
        tr = self.db.query(WorkflowTransition).filter_by(
            from_status_id=wf.status_id, to_status_id=target.id).first()
        if not tr:
            raise BadTransition(f"Transition {wf.status_id} -> {target.id} not allowed")
        if tr.required_role and tr.required_role not in (user_roles or []) and "admin" not in (user_roles or []):
            raise BadTransition(f"Need role {tr.required_role}")
        wf.status_id = target.id
        self.db.commit()
        self.db.refresh(wf)
        return wf

    def create_task(self, data: TaskIn) -> Task:
        t = Task(**data.model_dump())
        self.db.add(t)
        self.db.commit()
        self.db.refresh(t)
        return t

    def complete_task(self, task_id: int) -> Task:
        from datetime import datetime, timezone
        t = self.db.get(Task, task_id)
        if not t:
            raise NotFound("Task not found")
        t.status = "done"
        t.completed_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(t)
        return t
