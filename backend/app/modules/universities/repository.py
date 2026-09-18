from sqlalchemy.orm import Session

from app.modules.universities.models import University
from app.modules.universities.schemas import UniversityCreate, UniversityUpdate


class UniversityRepository:
    def __init__(self, db: Session):
        self.db = db

    def list(self, q: str | None = None, region: str | None = None) -> list[University]:
        """List universities with optional search.

        P1-11-03: ``region`` is a legacy query param kept for backward
        compatibility (the P1 ``universities`` table has no ``region``
        column — only ``city``). It is accepted and safely ignored so
        callers passing ``?region=`` never get ``AttributeError``/500.
        Do NOT reintroduce ``University.region`` and do NOT map ``region``
        onto ``city`` (different semantics). Legacy status: this repository
        backs an unmounted router (see ``app.api.router``); the mounted
        University Passport pipeline does not use it.
        """
        _ = region  # deprecated no-op, kept in signature for compatibility
        query = self.db.query(University)
        if q:
            query = query.filter(University.name.ilike(f"%{q}%"))
        return query.order_by(University.id.desc()).limit(200).all()

    def get(self, university_id: int) -> University | None:
        return self.db.get(University, university_id)

    def create(self, data: UniversityCreate) -> University:
        obj = University(**data.model_dump())
        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def update(self, obj: University, data: UniversityUpdate) -> University:
        before_responsible = obj.responsible_person_id
        for k, v in data.model_dump(exclude_unset=True).items():
            setattr(obj, k, v)
        self.db.commit()
        self.db.refresh(obj)
        obj._before_responsible = before_responsible  # for audit message
        return obj
