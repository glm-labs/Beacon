from app.api.openapi.common import ERROR_SCHEMA, json_body, path_param, response


NOTIFICATION_RULE_METHOD_VALUES = ["browser_push", "email", "voice_call"]
NOTIFICATION_RULE_EVENT_TYPE_VALUES = [
    "notification",
    "reminder",
    "escalation",
    "acknowledged",
    "resolved",
]
NOTIFICATION_RULE_SEVERITY_VALUES = [
    "critical",
    "high",
    "medium",
    "warning",
    "low",
    "info",
    "unknown",
]


NOTIFICATION_RULE_SEVERITIES_SCHEMA = {
    "type": "array",
    "description": (
        "Optional severity filter. Leave empty or omit to match all severities. "
        "Values are normalized by the API."
    ),
    "items": {
        "type": "string",
        "enum": NOTIFICATION_RULE_SEVERITY_VALUES,
    },
    "example": ["critical", "warning"],
}


NOTIFICATION_RULE_EVENT_TYPES_SCHEMA = {
    "type": "array",
    "description": (
        "Optional event filter. Leave empty or omit to use default events: "
        "notification, reminder and escalation."
    ),
    "items": {
        "type": "string",
        "enum": NOTIFICATION_RULE_EVENT_TYPE_VALUES,
    },
    "example": ["notification", "reminder", "escalation"],
}


NOTIFICATION_RULE_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {
            "type": "integer",
            "readOnly": True,
            "example": 12,
        },
        "position": {
            "type": "integer",
            "description": "Rule order in the current user's notification policy.",
            "example": 1,
        },
        "method": {
            "type": "string",
            "enum": NOTIFICATION_RULE_METHOD_VALUES,
            "description": (
                "User-level notification method. browser_push uses active PWA/browser "
                "subscriptions from the profile, email uses the profile email address, "
                "and voice_call uses the profile phone number and global voice provider."
            ),
            "example": "browser_push",
        },
        "delay_seconds": {
            "type": "integer",
            "minimum": 0,
            "description": "Delay before sending this notification rule. Use 0 for immediate delivery.",
            "example": 300,
        },
        "enabled": {
            "type": "boolean",
            "description": "Whether this notification rule is active.",
            "example": True,
        },
        "severities": NOTIFICATION_RULE_SEVERITIES_SCHEMA,
        "event_types": NOTIFICATION_RULE_EVENT_TYPES_SCHEMA,
        "created_at": {
            "type": "string",
            "format": "date-time",
            "nullable": True,
            "example": "2026-06-02T08:00:00",
        },
        "updated_at": {
            "type": "string",
            "format": "date-time",
            "nullable": True,
            "example": "2026-06-02T08:10:00",
        },
    },
}


NOTIFICATION_RULE_CREATE_SCHEMA = {
    "type": "object",
    "required": ["method"],
    "properties": {
        "method": {
            "type": "string",
            "enum": NOTIFICATION_RULE_METHOD_VALUES,
            "example": "browser_push",
        },
        "delay_seconds": {
            "type": "integer",
            "minimum": 0,
            "default": 0,
            "example": 0,
        },
        "enabled": {
            "type": "boolean",
            "default": True,
            "example": True,
        },
        "severities": NOTIFICATION_RULE_SEVERITIES_SCHEMA,
        "event_types": NOTIFICATION_RULE_EVENT_TYPES_SCHEMA,
    },
}


NOTIFICATION_RULE_UPDATE_SCHEMA = {
    "type": "object",
    "properties": {
        "method": {
            "type": "string",
            "enum": NOTIFICATION_RULE_METHOD_VALUES,
            "example": "email",
        },
        "delay_seconds": {
            "type": "integer",
            "minimum": 0,
            "example": 300,
        },
        "enabled": {
            "type": "boolean",
            "example": True,
        },
        "severities": NOTIFICATION_RULE_SEVERITIES_SCHEMA,
        "event_types": NOTIFICATION_RULE_EVENT_TYPES_SCHEMA,
    },
    "additionalProperties": False,
}


NOTIFICATION_RULE_DELETE_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "deleted": {"type": "boolean", "example": True},
        "id": {"type": "integer", "example": 12},
    },
}


def tags():
    """Return OpenAPI tags."""
    return [
        {
            "name": "notification-rules",
            "description": (
                "PagerDuty-like profile notification rules. Rules are user-level "
                "delivery preferences for alerts assigned to the current user. "
                "Supported methods are browser_push, email and voice_call. Voice "
                "calls are no longer route channels."
            ),
        }
    ]


def paths():
    """Return OpenAPI paths for profile notification rules."""
    return {
        "/api/profile/notification-rules": {
            "get": {
                "tags": ["notification-rules"],
                "summary": "List current user's notification rules",
                "description": (
                    "Returns profile notification rules owned by the current user. "
                    "Rules are ordered by position. If the user has no custom rules, "
                    "Beacon may still send default browser push notifications "
                    "when browser push is enabled in the profile."
                ),
                "operationId": "listProfileNotificationRules",
                "security": [{"bearerAuth": []}],
                "responses": {
                    "200": response(
                        "Notification rules returned.",
                        {"type": "array", "items": NOTIFICATION_RULE_SCHEMA},
                    ),
                    "401": response("Valid JWT token is required.", ERROR_SCHEMA),
                },
            },
            "post": {
                "tags": ["notification-rules"],
                "summary": "Create notification rule",
                "description": (
                    "Creates a user-level notification rule for the current user. "
                    "Once at least one custom rule exists, matching notification rules "
                    "control user-level delivery instead of the default immediate browser "
                    "push behavior."
                ),
                "operationId": "createProfileNotificationRule",
                "security": [{"bearerAuth": []}],
                "requestBody": json_body(
                    "Notification rule properties.",
                    NOTIFICATION_RULE_CREATE_SCHEMA,
                ),
                "responses": {
                    "201": response("Notification rule created.", NOTIFICATION_RULE_SCHEMA),
                    "400": response("Validation error.", ERROR_SCHEMA),
                    "401": response("Valid JWT token is required.", ERROR_SCHEMA),
                },
            },
        },
        "/api/profile/notification-rules/{rule_id}": {
            "put": {
                "tags": ["notification-rules"],
                "summary": "Update notification rule",
                "description": (
                    "Updates one notification rule owned by the current user. Omitted "
                    "fields keep their current value."
                ),
                "operationId": "updateProfileNotificationRule",
                "security": [{"bearerAuth": []}],
                "parameters": [path_param("rule_id", "Notification rule id.")],
                "requestBody": json_body(
                    "Updated notification rule properties.",
                    NOTIFICATION_RULE_UPDATE_SCHEMA,
                ),
                "responses": {
                    "200": response("Notification rule updated.", NOTIFICATION_RULE_SCHEMA),
                    "400": response("Validation error.", ERROR_SCHEMA),
                    "401": response("Valid JWT token is required.", ERROR_SCHEMA),
                    "404": response("Notification rule not found.", ERROR_SCHEMA),
                },
            },
            "delete": {
                "tags": ["notification-rules"],
                "summary": "Delete notification rule",
                "description": (
                    "Soft-deletes one notification rule owned by the current user."
                ),
                "operationId": "deleteProfileNotificationRule",
                "security": [{"bearerAuth": []}],
                "parameters": [path_param("rule_id", "Notification rule id.")],
                "responses": {
                    "200": response(
                        "Notification rule deleted.",
                        NOTIFICATION_RULE_DELETE_RESPONSE_SCHEMA,
                    ),
                    "401": response("Valid JWT token is required.", ERROR_SCHEMA),
                    "404": response("Notification rule not found.", ERROR_SCHEMA),
                },
            },
        },
    }
