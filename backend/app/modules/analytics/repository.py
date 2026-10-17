"""Batch-load an already filtered selection."""

from dataclasses import dataclass, field
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, raiseload

from app.models.catalog import ITProgram, License, Responsible, University
from app.models.interactions import InteractionNote, Meeting, UniversityProgram
from app.models.workflow_instances import InstanceStage, WorkflowInstance, WorkflowStageTransition, WorkflowTask
from app.models.workflow_templates import WorkflowStage, WorkflowTemplate
from app.db.seed_workflow import TEMPLATE_NAME
from app.modules.analytics.integration import Selection


@dataclass
class AnalyticsData:
    universities: list[Any] = field(default_factory=list)
    programs: list[Any] = field(default_factory=list)
    links: list[Any] = field(default_factory=list)
    existing_pairs: set[tuple[UUID, UUID]] = field(default_factory=set)
    licenses: list[Any] = field(default_factory=list)
    instances: list[Any] = field(default_factory=list)
    stages: list[Any] = field(default_factory=list)
    tasks: list[Any] = field(default_factory=list)
    transitions: list[Any] = field(default_factory=list)
    meetings: list[Any] = field(default_factory=list)
    interaction_notes: list[Any] = field(default_factory=list)
    responsibles: list[Any] = field(default_factory=list)
    templates: list[Any] = field(default_factory=list)
    template_stages: list[Any] = field(default_factory=list)


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
    data.transitions = selected_rows(db, WorkflowStageTransition, WorkflowStageTransition.instance_id.in_(instance_ids)) if instance_ids else []
    data.meetings = selected_rows(db, Meeting, Meeting.university_id.in_(uni_ids) & Meeting.meeting_at.is_not(None))
    data.interaction_notes = selected_rows(db, InteractionNote, InteractionNote.university_id.in_(uni_ids))
    data.responsibles = list(db.scalars(select(Responsible)))
    standard_template = db.scalar(
        select(WorkflowTemplate)
        .where(WorkflowTemplate.name == TEMPLATE_NAME, WorkflowTemplate.is_active.is_(True))
        .options(raiseload("*"))
    )
    if standard_template is not None:
        data.templates = [standard_template]
        data.template_stages = selected_rows(
            db, WorkflowStage, WorkflowStage.template_id == standard_template.id,
        )
    data.scores = {}
    data.trend = []
    return data
