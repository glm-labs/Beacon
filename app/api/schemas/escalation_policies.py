from pydantic import Field, field_validator, model_validator

from app.api.schemas.base import ApiModel

ESCALATION_TARGET_TYPES = {"rotation", "user", "team"}


class EscalationPolicyCreateSchema(ApiModel):
    """Validate escalation policy creation input."""

    team_id: int = Field(ge=1)
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=2048)
    enabled: bool = True
    repeat_count: int = Field(default=0, ge=0, le=50)


class EscalationPolicyUpdateSchema(ApiModel):
    """Validate escalation policy update input."""

    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=2048)
    enabled: bool | None = None
    repeat_count: int | None = Field(default=None, ge=0, le=50)


class EscalationPolicyRuleSchema(ApiModel):
    """Validate escalation policy rule input."""

    position: int = Field(ge=1, le=100)
    delay_seconds: int = Field(default=300, ge=0, le=86400)
    target_type: str
    target_id: int = Field(ge=1)
    enabled: bool = True

    @field_validator("target_type")
    @classmethod
    def validate_target_type(cls, value):
        if value not in ESCALATION_TARGET_TYPES:
            raise ValueError("target_type must be one of: rotation, user, team")
        return value


class EscalationPolicyRuleUpdateSchema(ApiModel):
    """Validate escalation policy rule update input."""

    position: int | None = Field(default=None, ge=1, le=100)
    delay_seconds: int | None = Field(default=None, ge=0, le=86400)
    target_type: str | None = None
    target_id: int | None = Field(default=None, ge=1)
    enabled: bool | None = None

    @field_validator("target_type")
    @classmethod
    def validate_target_type(cls, value):
        if value is not None and value not in ESCALATION_TARGET_TYPES:
            raise ValueError("target_type must be one of: rotation, user, team")
        return value

    @model_validator(mode="after")
    def validate_target_pair(self):
        if self.target_type is not None and self.target_id is None:
            raise ValueError("target_id is required when target_type is changed")
        return self
