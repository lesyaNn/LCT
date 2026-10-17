"""Strict single-mailbox validation for the outbound email channel."""

from email_validator import EmailNotValidError, validate_email


def outbound_email(value: str) -> str:
    """Return one normalized mailbox without DNS checks or display names."""
    try:
        return validate_email(
            value, check_deliverability=False, allow_display_name=False,
            test_environment=True,
        ).normalized
    except EmailNotValidError as exc:
        raise ValueError("invalid email mailbox") from exc
