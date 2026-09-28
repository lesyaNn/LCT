"""Compatibility entry points for the retired automatic workflow templates.

Workflow templates are now created only by CRM users through the UI.
"""

from sqlalchemy.orm import Session


def ensure_spec_workflow_template(db: Session) -> dict:
    return {"status": "disabled", "templates": 0, "stages": 0, "instances_created": 0}


def ensure_default_workflow_template(db: Session) -> dict:
    return {"status": "disabled", "templates": 0, "stages": 0, "instances_created": 0}
