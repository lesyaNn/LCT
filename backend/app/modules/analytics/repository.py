"""Batch-load an already filtered selection."""

from dataclasses import dataclass, field
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, raiseload

from app.models.catalog import ITProgram, License, University
from app.models.interactions import UniversityProgram
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


def load_data(db: Session, selection: Selection, *, today: date, filters: dict | None = None) -> AnalyticsData:
    data = AnalyticsData()
    data.universities = selected_rows(db, University, University.id.in_(selection.university_ids))
    uni_ids = [item.id for item in data.universities]
    data.programs = selected_rows(
        db, ITProgram, ITProgram.id.in_(selection.program_ids),
        options=(joinedload(ITProgram.direction),),
    )
    if not uni_ids:
        return data
    all_links = selected_rows(
        db, UniversityProgram,
        UniversityProgram.university_id.in_(uni_ids) & UniversityProgram.program_id.in_(selection.program_ids),
    )
    data.existing_pairs = {(item.university_id, item.program_id) for item in all_links}
    link_ids = None if selection.university_program_ids is None else set(selection.university_program_ids)
    data.links = [item for item in all_links if link_ids is None or item.id in link_ids]
    pairs = {(item.university_id, item.program_id) for item in data.links}
    data.licenses = selected_rows(db, License, License.university_id.in_(uni_ids), selection.license_ids, (joinedload(License.product),))
    data.licenses = [item for item in data.licenses if item.program_id is None or (item.university_id, item.program_id) in pairs]
    data.instances = selected_rows(db, WorkflowInstance, WorkflowInstance.university_id.in_(uni_ids), selection.workflow_instance_ids)
    instance_ids = [item.id for item in data.instances]
    data.stages = selected_rows(db, InstanceStage, InstanceStage.instance_id.in_(instance_ids)) if instance_ids else []
    data.tasks = selected_rows(db, WorkflowTask, WorkflowTask.instance_id.in_(instance_ids)) if instance_ids else []
    data.scores = {}
    data.trend = []
    return data
