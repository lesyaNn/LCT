"""Batch-load an already filtered selection. No P4-01 filter implementation.

Child selections are always intersected with the authorized university IDs.
No lazy relationship IO, no SELECT in matrix-cell loops. P2's score computation
is delegated unchanged and uses P2's existing cache.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload, raiseload

from app.models.catalog import ITProgram, License, University
from app.models.health_score import HealthScoreSnapshot, HealthScoreCurrent
from app.models.interactions import UniversityProgram
from app.models.teachers import Teacher, TeacherCertificate, TeacherProgram, TeacherQualification
from app.models.workflow_instances import InstanceStage, WorkflowInstance, WorkflowTask
from app.modules.analytics.integration import Selection


@dataclass
class AnalyticsData:
    universities: list[Any] = field(default_factory=list)
    programs: list[Any] = field(default_factory=list)
    links: list[Any] = field(default_factory=list)
    existing_pairs: set[tuple[UUID, UUID]] = field(default_factory=set)
    licenses: list[Any] = field(default_factory=list)
    teachers: list[Any] = field(default_factory=list)
    teacher_programs: list[Any] = field(default_factory=list)
    certificates: list[Any] = field(default_factory=list)
    qualifications: list[Any] = field(default_factory=list)
    instances: list[Any] = field(default_factory=list)
    stages: list[Any] = field(default_factory=list)
    tasks: list[Any] = field(default_factory=list)
    scores: dict[UUID, Any] = field(default_factory=dict)
    trend: list[dict] = field(default_factory=list)


def selected_rows(db, model, predicate, ids=None, options=()):
    query = select(model).where(predicate).options(raiseload("*"), *options)
    if ids is not None:
        query = query.where(model.id.in_(ids))
    return list(db.scalars(query))


def load_data(
    db: Session, selection: Selection, *, today: date, filters: dict | None = None
) -> AnalyticsData:
    data = AnalyticsData()
    data.universities = selected_rows(db, University, University.id.in_(selection.university_ids))
    uni_ids = [item.id for item in data.universities]
    data.programs = selected_rows(
        db,
        ITProgram,
        ITProgram.id.in_(selection.program_ids),
        options=(joinedload(ITProgram.direction),),
    )
    if not uni_ids:
        return data
    all_links = selected_rows(
        db,
        UniversityProgram,
        UniversityProgram.university_id.in_(uni_ids)
        & UniversityProgram.program_id.in_(selection.program_ids),
    )
    data.existing_pairs = {(item.university_id, item.program_id) for item in all_links}
    link_ids = (
        None if selection.university_program_ids is None else set(selection.university_program_ids)
    )
    data.links = [item for item in all_links if link_ids is None or item.id in link_ids]
    pairs = {(item.university_id, item.program_id) for item in data.links}
    data.licenses = selected_rows(
        db,
        License,
        License.university_id.in_(uni_ids),
        selection.license_ids,
        (joinedload(License.product),),
    )
    # A NULL program is genuinely unassigned; do not manufacture an association.
    data.licenses = [
        item
        for item in data.licenses
        if item.program_id is None or (item.university_id, item.program_id) in pairs
    ]
    teachers = selected_rows(db, Teacher, Teacher.university_id.in_(uni_ids))
    teacher_unis = {item.id: item.university_id for item in teachers}
    assignments = selected_rows(
        db,
        TeacherProgram,
        TeacherProgram.teacher_id.in_(teacher_unis)
        & TeacherProgram.program_id.in_(selection.program_ids),
    )
    data.teacher_programs = [
        item for item in assignments if (teacher_unis[item.teacher_id], item.program_id) in pairs
    ]
    teacher_ids = {item.teacher_id for item in data.teacher_programs}
    data.teachers = [item for item in teachers if item.id in teacher_ids]
    data.certificates = selected_rows(
        db,
        TeacherCertificate,
        TeacherCertificate.teacher_id.in_(teacher_ids)
        & or_(
            TeacherCertificate.program_id.is_(None),
            TeacherCertificate.program_id.in_(selection.program_ids),
        ),
    )
    data.certificates = [
        item
        for item in data.certificates
        if item.program_id is None or (teacher_unis[item.teacher_id], item.program_id) in pairs
    ]
    data.qualifications = selected_rows(
        db, TeacherQualification, TeacherQualification.teacher_id.in_(teacher_ids)
    )
    data.instances = selected_rows(
        db,
        WorkflowInstance,
        WorkflowInstance.university_id.in_(uni_ids),
        selection.workflow_instance_ids,
    )
    instance_ids = [item.id for item in data.instances]
    data.stages = selected_rows(db, InstanceStage, InstanceStage.instance_id.in_(instance_ids))
    data.tasks = selected_rows(db, WorkflowTask, WorkflowTask.instance_id.in_(instance_ids))
    current_scores = db.execute(select(HealthScoreCurrent).where(
        HealthScoreCurrent.university_id.in_(uni_ids)
    )).scalars()
    data.scores = {row.university_id: row for row in current_scores}
    filters = filters or {}
    start = max(
        today - timedelta(days=29),
        date.fromisoformat(filters["date_from"])
        if filters.get("date_from")
        else today - timedelta(days=29),
    )
    end = min(today, date.fromisoformat(filters["date_to"]) if filters.get("date_to") else today)
    # Multiple trigger events on the same day must not weight that university
    # more heavily. Keep exactly its LAST snapshot for each day before averaging.
    latest = (
        select(
            HealthScoreSnapshot.period_day,
            HealthScoreSnapshot.score,
            func.row_number()
            .over(
                partition_by=(HealthScoreSnapshot.university_id, HealthScoreSnapshot.period_day),
                order_by=(HealthScoreSnapshot.calculated_at.desc(), HealthScoreSnapshot.id.desc()),
            )
            .label("rn"),
        )
        .where(
            HealthScoreSnapshot.university_id.in_(uni_ids),
            HealthScoreSnapshot.period_day.between(start, end),
        )
        .subquery()
    )
    data.trend = [
        {"date": day, "avg_score": round(float(score), 2)}
        for day, score in db.execute(
            select(latest.c.period_day, func.avg(latest.c.score))
            .where(latest.c.rn == 1)
            .group_by(latest.c.period_day)
            .order_by(latest.c.period_day)
        )
    ]
    return data
