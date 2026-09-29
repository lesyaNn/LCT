"""Focused request-schema checks for CRM form validation."""

from datetime import date
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.admin_users.schemas import UserInvite
from app.modules.catalog.schemas import ContractCreate, ResponsibleCreate
from app.modules.workflow_instances.schemas import WorkflowTaskCreate
from app.modules.workflow_templates.schemas import StageCreate
from app.schemas.catalog import VendorContactInput


@pytest.mark.parametrize("email", ["abc", "test", "ivanov.mail.ru", " x@y "])
def test_contact_email_rejects_invalid_values(email: str) -> None:
    with pytest.raises(ValidationError):
        VendorContactInput(full_name="Иван Иванов", email=email)
    with pytest.raises(ValidationError):
        ResponsibleCreate(full_name="Иван Иванов", email=email)


@pytest.mark.parametrize("phone", ["+7abc999", "телефон123", "123"])
def test_contact_phone_rejects_invalid_values(phone: str) -> None:
    with pytest.raises(ValidationError):
        VendorContactInput(full_name="Иван Иванов", email="ivan@example.com", phone=phone)


def test_contact_fields_trim_and_accept_valid_values() -> None:
    value = ResponsibleCreate(
        full_name="  Иван Иванов  ",
        email="  ivan@example.com  ",
        phone="  +7 (999) 123-45-67  ",
    )
    assert (value.full_name, value.email, value.phone) == (
        "Иван Иванов", "ivan@example.com", "+7 (999) 123-45-67"
    )


def test_invitation_rejects_invalid_email() -> None:
    with pytest.raises(ValidationError):
        UserInvite(
            name="Иван Иванов", username="ivan", email="abc", role="user",
            scope={"kind": "universities", "university_ids": []},
        )


def test_required_names_reject_whitespace() -> None:
    with pytest.raises(ValidationError):
        WorkflowTaskCreate(stage_id=uuid4(), title="   ")
    with pytest.raises(ValidationError):
        StageCreate(name="   ")
    with pytest.raises(ValidationError):
        ContractCreate(university_id=uuid4(), contract_number="   ", signed_at=date.today())
