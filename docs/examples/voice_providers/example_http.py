"""Example Beacon HTTP voice provider.

This provider demonstrates:
- text-to-speech call creation;
- provider call ID tracking;
- status callbacks;
- DTMF callbacks;
- optional status polling.
"""

import requests

from app.notifiers.voice.base import (
    BaseVoiceProvider,
    VoiceCallCallbackEvent,
    VoiceCallRequest,
    VoiceCallResult,
    VoiceProviderCapabilities,
)


class Provider(BaseVoiceProvider):
    """Example provider with TTS, status callbacks and DTMF callbacks."""

    name = "example_http"

    capabilities = VoiceProviderCapabilities(
        tts=True,
        status_callback=True,
        dtmf_callback=True,
        status_polling=True,
    )

    @classmethod
    def validate_config(cls, config):
        """Validate provider config."""

        required = ["api_url", "api_token"]

        missing = [
            item
            for item in required
            if not config.get(item)
        ]

        if missing:
            raise RuntimeError(
                f"example_http config requires: {', '.join(missing)}"
            )

    def place_call(self, request: VoiceCallRequest) -> VoiceCallResult:
        """Create a call through provider API."""

        payload = {
            "to": request.phone,
            "text": request.text,
            "callback_url": request.callback_url,
            "metadata": {
                "alert_id": request.alert_id,
                "event_type": request.event_type,
                "severity": request.severity,
                "team": request.team,
                "assignee": request.assignee,
            },
            "dtmf": {
                "enabled": True,
                "actions": request.action_hints,
            },
        }

        response = requests.post(
            f"{self.config['api_url'].rstrip('/')}/calls",
            json=payload,
            headers={
                "Authorization": f"Bearer {self.config['api_token']}",
            },
            timeout=int(self.config.get("timeout", 10)),
        )
        response.raise_for_status()

        data = response.json() if response.content else {}

        return VoiceCallResult(
            call_id=str(data.get("call_id") or data.get("id") or ""),
            status=str(data.get("status") or "queued"),
            raw=data,
        )

    def parse_callback(
        self,
        payload,
        headers=None,
        raw_body=None,
        query_args=None,
    ):
        """Normalize provider callback.

        Example provider callback:
        {
          "call_id": "abc-123",
          "event": "dtmf",
          "status": "answered",
          "digit": "1"
        }
        """

        call_id = str(payload.get("call_id") or payload.get("id") or "")

        if not call_id:
            raise RuntimeError("callback call_id is missing")

        event_type = str(payload.get("event") or payload.get("event_type") or "status")

        return [
            VoiceCallCallbackEvent(
                call_id=call_id,
                event_type=event_type,
                status=payload.get("status"),
                digit=payload.get("digit"),
                action=payload.get("action"),
                alert_id=payload.get("alert_id"),
                message=payload.get("message"),
                raw=payload,
            )
        ]

    def get_call_status(self, call_id: str) -> VoiceCallResult:
        """Fetch call status from provider API."""

        response = requests.get(
            f"{self.config['api_url'].rstrip('/')}/calls/{call_id}",
            headers={
                "Authorization": f"Bearer {self.config['api_token']}",
            },
            timeout=int(self.config.get("timeout", 10)),
        )
        response.raise_for_status()

        data = response.json() if response.content else {}

        return VoiceCallResult(
            call_id=call_id,
            status=str(data.get("status") or "unknown"),
            raw=data,
        )
