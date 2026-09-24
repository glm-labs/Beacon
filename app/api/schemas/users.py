from pydantic import EmailStr, Field, field_validator

from app.api.schemas.base import ApiModel
from app.api.schemas.limits import (
    CONTACT_ID_MAX_LENGTH,
    DISPLAY_NAME_MAX_LENGTH,
    PHONE_MAX_LENGTH,
    ROLE_MAX_LENGTH,
    USERNAME_MAX_LENGTH,
    USERNAME_MIN_LENGTH,
    normalize_phone,
)
from app.api.schemas.roles import (
    GROUP_ASSIGNABLE_BY_USER_ADMIN_PATTERN,
    GROUP_ROLE_PATTERN,
    GROUP_VIEWER_ROLE,
)


class UserFieldsSchema(ApiModel):
    """Shared user fields for user input."""

    username: str = Field(
        min_length=USERNAME_MIN_LENGTH,
        max_length=USERNAME_MAX_LENGTH,
        pattern=r"^[a-zA-Z0-9._-]+$",
    )
    display_name: str | None = Field(
        default=None,
        max_length=DISPLAY_NAME_MAX_LENGTH,
    )
    email: EmailStr | None = None
    phone: str | None = Field(
        default=None,
        max_length=PHONE_MAX_LENGTH,
    )
    telegram_user_id: str | None = Field(
        default=None,
        max_length=CONTACT_ID_MAX_LENGTH,
    )
    slack_user_id: str | None = Field(
        default=None,
        max_length=CONTACT_ID_MAX_LENGTH,
    )
    mattermost_user_id: str | None = Field(
        default=None,
        max_length=CONTACT_ID_MAX_LENGTH,
    )
    pushover_user_key: str | None = Field(
        default=None,
        max_length=CONTACT_ID_MAX_LENGTH,
    )

    @field_validator("phone")
    @classmethod
    def validate_phone_field(cls, value):
        """Validate user phone number."""
        return normalize_phone(value)


class UserCreateSchema(UserFieldsSchema):
    """Validate global-admin user creation input."""

    active: bool = True
    is_admin: bool = False
    password: str | None = Field(default=None, min_length=8, max_length=256)
    group_id: int | None = Field(default=None, ge=1)
    group_role: str = Field(
        default=GROUP_VIEWER_ROLE,
        max_length=ROLE_MAX_LENGTH,
        pattern=GROUP_ROLE_PATTERN,
    )


class GroupUserCreateSchema(UserFieldsSchema):
    """Validate group user-admin user creation input.

    group_id, active and is_admin are intentionally not accepted here.
    ApiModel forbids extra fields, so clients cannot override the group
    selected from the URL or create global administrators through this schema.
    """

    password: str = Field(min_length=8, max_length=256)
    group_role: str = Field(
        default=GROUP_VIEWER_ROLE,
        max_length=ROLE_MAX_LENGTH,
        pattern=GROUP_ASSIGNABLE_BY_USER_ADMIN_PATTERN,
    )


class UserUpdateSchema(UserFieldsSchema):
    """Validate global-admin user update input.

    group_id/group_role are accepted only by the global admin users endpoint.
    They update the user's active group membership from the Users page.
    """

    active: bool = True
    is_admin: bool = False
    password: str | None = Field(default=None, min_length=8, max_length=256)
    group_id: int | None = Field(default=None, ge=1)
    group_role: str = Field(
        default=GROUP_VIEWER_ROLE,
        max_length=ROLE_MAX_LENGTH,
        pattern=GROUP_ROLE_PATTERN,
    )
