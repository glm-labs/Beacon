"""Mango-like Beacon voice provider template.

This is only a template. Adjust URLs, payload, authentication and signature
logic according to your provider documentation.
"""

import hashlib
import json

import requests

from app.notifiers.voice.base import (
    BaseVoiceProvider,
    VoiceCallCallbackEvent,
    VoiceCallRequest,
    VoiceCallResult,
    VoiceProviderCapabilities,
)


class Provider(BaseVoiceProvider):
    """Mango-like voice provider template."""

    name = "mango"

    capabilities = VoiceProviderCapabilities(
        tts=True,
        status_callback=True,
        dtmf_callback=True,
        status_polling=False,
    )

    @classmethod
    def validate_config(cls, config):
        """Validate Mango-like provider configuration."""

        required_fields = [
            "api_url",
            "api_key",
            "api_salt",
            "from",
        ]

        missing = [
            field
            for field in required_fields
            if not config.get(field)
        ]

        if missing:
            raise RuntimeError(
                f"mango config requires: {', '.join(missing)}"
            )

    def place_call(self, request: VoiceCallRequest) -> VoiceCallResult:
        """Place a voice call through a Mango-like API."""

        payload = {
            "from": self.config["from"],
            "to": request.phone,
            "text": request.text,
            "callback_url": request.callback_url,
            "metadata": {
                "alert_id": request.alert_id,
                "event_type": request.event_type,
                "severity": request.severity,
            },
            "dtmf": {
                "enabled": True,
                "actions": request.action_hints,
            },
        }

        json_payload = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        signature = self._make_signature(json_payload)

        response = requests.post(
            self.config["api_url"],
            data={
                "vpbx_api_key": self.config["api_key"],
                "sign": signature,
                "json": json_payload,
            },
            timeout=int(self.config.get("timeout", 10)),
        )
        response.raise_for_status()

        data = response.json() if response.content else {}

        return VoiceCallResult(
            call_id=str(data.get("call_id") or data.get("result") or ""),
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
        """Normalize Mango-like callback.

        Adjust field names according to actual provider docs.
        """

        call_id = str(payload.get("call_id") or payload.get("entry_id") or "")

        if not call_id:
            raise RuntimeError("callback call_id is missing")

        event_type = str(payload.get("event_type") or payload.get("event") or "status")

        return [
            VoiceCallCallbackEvent(
                call_id=call_id,
                event_type=event_type,
                status=payload.get("status"),
                digit=payload.get("digit") or payload.get("dtmf"),
                action=payload.get("action"),
                alert_id=payload.get("alert_id"),
                message=payload.get("message"),
                raw=payload,
            )
        ]

    def _make_signature(self, json_payload):
        """Create provider request signature."""

        raw = f"{self.config['api_key']}{json_payload}{self.config['api_salt']}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()
