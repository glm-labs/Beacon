from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


VOICE_ACTION_ACKNOWLEDGE = "acknowledge"
VOICE_ACTION_RESOLVE = "resolve"

VOICE_CALLBACK_STATUS = "status"
VOICE_CALLBACK_DTMF = "dtmf"
VOICE_CALLBACK_ERROR = "error"


@dataclass(frozen=True)
class VoiceProviderCapabilities:
    """Feature flags supported by a voice provider."""

    tts: bool = False
    status_callback: bool = False
    dtmf_callback: bool = False
    status_polling: bool = False


@dataclass(frozen=True)
class VoiceCallRequest:
    """Data passed from Beacon to a voice call provider."""

    phone: str
    text: str
    alert_id: int | None
    event_type: str
    callback_url: str | None = None
    callback_secret: str | None = None
    severity: str | None = None
    title: str | None = None
    message: str | None = None
    assignee: str | None = None
    team: str | None = None
    action_hints: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VoiceCallResult:
    """Provider response normalized for Beacon."""

    call_id: str | None = None
    status: str = "queued"
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VoiceCallCallbackEvent:
    """Normalized callback event from a voice provider."""

    call_id: str
    event_type: str
    status: str | None = None
    digit: str | None = None
    action: str | None = None
    alert_id: int | None = None
    message: str | None = None
    occurred_at: datetime | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class BaseVoiceProvider:
    """Base interface for custom voice call providers."""

    name = "base"

    capabilities = VoiceProviderCapabilities()

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}

    @classmethod
    def validate_config(cls, config: dict[str, Any]) -> None:
        """Validate provider-specific configuration."""

    def place_call(self, request: VoiceCallRequest) -> VoiceCallResult:
        """Place a voice call."""

        raise NotImplementedError

    def parse_callback(
        self,
        payload: dict[str, Any],
        headers: dict[str, str] | None = None,
        raw_body: bytes | None = None,
        query_args: dict[str, Any] | None = None,
    ) -> list[VoiceCallCallbackEvent]:
        """Parse provider webhook callback.

        Providers that support status callbacks or DTMF callbacks should implement this.
        """

        return []

    def get_call_status(self, call_id: str) -> VoiceCallResult:
        """Return current call status.

        Optional fallback for providers that do not support callbacks.
        """

        raise NotImplementedError
