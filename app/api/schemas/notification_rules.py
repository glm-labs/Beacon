from pydantic import Field, field_validator

from app.api.schemas.base import ApiModel
from app.services.notifications.rules import NOTIFICATION_RULE_METHODS
from app.services.severity import normalize_severity_list


NOTIFICATION_RULE_EVENT_TYPES = {
    "notification",
    "reminder",
    "escalation",
    "acknowledged",
    "resolved",
}


class NotificationRuleBaseSchema(ApiModel):
    """Validate user notification rule input."""

    method: str = Field(
        description="Notification method: browser_push, email, voice_call or pushover."
    )
    delay_seconds: int = Field(default=0, ge=0)
    severities: list[str] = Field(default_factory=list)
    event_types: list[str] = Field(default_factory=list)
    enabled: bool = True

    @field_validator("method")
    @classmethod
    def validate_method(cls, value):
        if value not in NOTIFICATION_RULE_METHODS:
            raise ValueError("unsupported notification rule method")

        return value

    @field_validator("severities")
    @classmethod
    def validate_severities(cls, value):
        return normalize_severity_list(value or [])

    @field_validator("event_types")
    @classmethod
    def validate_event_types(cls, value):
        values = value or []
        invalid = set(values) - NOTIFICATION_RULE_EVENT_TYPES

        if invalid:
            raise ValueError(
                "unsupported notification rule event type: "
                + ", ".join(sorted(invalid))
            )

        return values


class NotificationRuleCreateSchema(NotificationRuleBaseSchema):
    """Validate notification rule creation input."""


class NotificationRuleUpdateSchema(ApiModel):
    """Validate notification rule update input."""

    method: str | None = None
    delay_seconds: int | None = Field(default=None, ge=0)
    severities: list[str] | None = None
    event_types: list[str] | None = None
    enabled: bool | None = None

    @field_validator("method")
    @classmethod
    def validate_method(cls, value):
        if value is None:
            return value

        if value not in NOTIFICATION_RULE_METHODS:
            raise ValueError("unsupported notification rule method")

        return value

    @field_validator("severities")
    @classmethod
    def validate_severities(cls, value):
        if value is None:
            return value

        return normalize_severity_list(value or [])

    @field_validator("event_types")
    @classmethod
    def validate_event_types(cls, value):
        if value is None:
            return value

        values = value or []
        invalid = set(values) - NOTIFICATION_RULE_EVENT_TYPES

        if invalid:
            raise ValueError(
                "unsupported notification rule event type: "
                + ", ".join(sorted(invalid))
            )

        return values
