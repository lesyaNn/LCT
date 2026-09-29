"""Shared validation for contact fields used by catalog and admin writes."""

from __future__ import annotations

import re
from typing import Annotated

from pydantic import AfterValidator


def nonblank(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("Обязательное поле")
    return value


def email(value: str) -> str:
    value = nonblank(value)
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
        raise ValueError("Введите корректный email")
    return value


def phone(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    digits = sum(char.isdigit() for char in value)
    if not re.fullmatch(r"\+?[0-9 ()-]+", value) or not 5 <= digits <= 20:
        raise ValueError("Введите номер телефона: 5–20 цифр, можно использовать +, пробелы, скобки и дефис")
    return value


NonBlankText = Annotated[str, AfterValidator(nonblank)]
ContactEmail = Annotated[str, AfterValidator(email)]
ContactPhone = Annotated[str, AfterValidator(phone)]
