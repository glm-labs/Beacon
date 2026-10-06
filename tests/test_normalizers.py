import pytest
from app.services.integrations.normalizers.webhook import normalize_webhook
from app.services.integrations.normalizers.zabbix import normalize_zabbix
from app.services.integrations.normalizers.alertmanager import normalize_alertmanager
from app.services.integrations.normalizers.common import make_hash, make_dedup_key


def test_make_hash_is_stable():
    assert make_hash("abc") == make_hash("abc")
    assert make_hash("abc") != make_hash("abcd")


def test_make_dedup_key_is_stable_for_equal_payloads():
    labels = {"alertname": "DiskFull", "instance": "host1"}

    assert make_dedup_key("alertmanager", "fp1", "DiskFull", labels) == make_dedup_key(
        "alertmanager",
        "fp1",
        "DiskFull",
        labels,
    )


def test_normalize_alertmanager_payload():
    payload = {
        "status": "firing",
        "alerts": [
            {
                "status": "firing",
                "labels": {
                    "alertname": "DiskFull",
                    "severity": "critical",
                    "instance": "host1",
                    "team": "infra",
                },
                "annotations": {
                    "summary": "Disk is full",
                    "description": "/var is 95% full",
                },
                "fingerprint": "disk-full-host1-var",
                "startsAt": "2026-05-18T10:00:00Z",
            }
        ],
    }

    alerts = normalize_alertmanager(payload)

    assert len(alerts) == 1
    assert alerts[0]["source"] == "alertmanager"
    assert alerts[0]["team_slug"] == "infra"
    assert alerts[0]["status"] == "firing"
    assert alerts[0]["severity"] == "critical"
    assert alerts[0]["title"] == "Disk is full"
    assert alerts[0]["message"] == "/var is 95% full"
    assert alerts[0]["dedup_key"] == "disk-full-host1-var"
    assert alerts[0]["labels"]["instance"] == "host1"


def test_normalize_zabbix_payload():
    payload = {
        "event_id": "123",
        "title": "CPU load is high",
        "message": "Load average is high",
        "severity": "High",
        "status": "firing",
        "labels": {"team": "infra"},
    }

    alerts = normalize_zabbix(payload)

    assert len(alerts) == 1
    assert alerts[0]["source"] == "zabbix"
    assert alerts[0]["team_slug"] == "infra"
    assert alerts[0]["status"] == "firing"
    assert alerts[0]["severity"] == "high"
    assert alerts[0]["labels"]["zabbix_severity"] == "High"
    assert alerts[0]["title"] == "CPU load is high"
    assert alerts[0]["message"] == "Load average is high"


def test_normalize_webhook_payload():
    payload = {
        "status": "resolved",
        "title": "DiskFull",
        "message": "Disk is ok",
        "severity": "info",
        "fingerprint": "fp-1",
        "labels": {"team": "infra"},
        "external_id": "external-1",
    }

    alerts = normalize_webhook(payload)

    assert len(alerts) == 1
    assert alerts[0]["source"] == "webhook"
    assert alerts[0]["team_slug"] == "infra"
    assert alerts[0]["status"] == "resolved"
    assert alerts[0]["dedup_key"] == "fp-1"
    assert alerts[0]["title"] == "DiskFull"
    assert alerts[0]["labels"]["team"] == "infra"


def test_normalize_zabbix_uses_defaults_for_none_values():
    alerts = normalize_zabbix(
        {
            "event_id": "123",
            "title": "CPUHigh",
            "message": None,
            "severity": None,
            "status": None,
            "labels": {},
        }
    )

    assert alerts == [
        {
            "source": "zabbix",
            "team_slug": None,
            "external_id": "123",
            "dedup_key": alerts[0]["dedup_key"],
            "title": "CPUHigh",
            "message": "",
            "severity": "info",
            "labels": {},
            "payload": {
                "event_id": "123",
                "title": "CPUHigh",
                "message": None,
                "severity": None,
                "status": None,
                "labels": {},
            },
            "status": "firing",
        }
    ]


def test_normalize_zabbix_uses_event_name_as_title():
    payload = {
        "event_id": "12345",
        "trigger_id": "98765",
        "event_name": "Free disk space is less than 10%",
        "host": "db01",
        "event_severity": "High",
        "event_status": "PROBLEM",
        "opdata": "/var: 91% used",
        "tags": [
            {
                "tag": "service",
                "value": "filesystem",
            },
            {
                "tag": "team",
                "value": "infra",
            },
        ],
    }

    alerts = normalize_zabbix(payload)

    assert len(alerts) == 1

    alert = alerts[0]

    assert alert["title"] == "Free disk space is less than 10%"
    assert alert["message"] == "/var: 91% used"
    assert alert["severity"] == "high"
    assert alert["status"] == "firing"
    assert alert["external_id"] == "12345"
    assert alert["team_slug"] == "infra"
    assert alert["labels"]["host"] == "db01"
    assert alert["labels"]["service"] == "filesystem"


def test_normalize_zabbix_uses_trigger_name_when_event_name_is_missing():
    payload = {
        "trigger_id": "98765",
        "trigger_name": "CPU load is too high",
        "host_name": "app01",
        "severity": "Average",
        "status": "PROBLEM",
    }

    alerts = normalize_zabbix(payload)

    assert alerts[0]["title"] == "CPU load is too high"
    assert alerts[0]["severity"] == "medium"
    assert alerts[0]["labels"]["host"] == "app01"


def test_normalize_zabbix_maps_ok_to_resolved():
    payload = {
        "event_id": "12345",
        "event_name": "Free disk space is less than 10%",
        "event_status": "OK",
    }

    alerts = normalize_zabbix(payload)

    assert alerts[0]["status"] == "resolved"


def test_normalize_zabbix_adds_event_tag_to_labels():
    payload = {
        "event_id": "12345",
        "event_name": "RabbitMQ node is down",
        "event_status": "PROBLEM",
        "event_severity": "High",
        "event_tag": "team: infra, service: rabbitmq",
    }

    alerts = normalize_zabbix(payload)

    assert len(alerts) == 1

    alert = alerts[0]

    assert alert["title"] == "RabbitMQ node is down"
    assert alert["labels"]["event_tag"] == "team: infra, service: rabbitmq"
    assert alert["labels"]["team"] == "infra"
    assert alert["labels"]["service"] == "rabbitmq"


def test_normalize_zabbix_adds_event_tags_json_to_labels():
    payload = {
        "event_id": "12345",
        "event_name": "Disk space is low",
        "event_status": "PROBLEM",
        "event_severity": "Average",
        "event_tag": [
            {
                "tag": "team",
                "value": "infra",
            },
            {
                "tag": "service",
                "value": "filesystem",
            },
        ],
    }

    alerts = normalize_zabbix(payload)

    assert alerts[0]["labels"]["event_tag"] == (
        '[{"tag": "team", "value": "infra"}, '
        '{"tag": "service", "value": "filesystem"}]'
    )
    assert alerts[0]["labels"]["team"] == "infra"
    assert alerts[0]["labels"]["service"] == "filesystem"


def test_normalize_zabbix_maps_severity_and_keeps_original_value():
    payload = {
        "event_id": "12345",
        "event_name": "CPU load is high",
        "event_status": "PROBLEM",
        "event_severity": "High",
    }

    alerts = normalize_zabbix(payload)

    assert len(alerts) == 1

    alert = alerts[0]

    assert alert["severity"] == "high"
    assert alert["labels"]["zabbix_severity"] == "High"


def test_normalize_zabbix_maps_average_to_medium():
    payload = {
        "event_id": "12345",
        "event_name": "CPU load is high",
        "event_status": "PROBLEM",
        "event_severity": "Average",
    }

    alerts = normalize_zabbix(payload)

    assert alerts[0]["severity"] == "medium"
    assert alerts[0]["labels"]["zabbix_severity"] == "Average"


@pytest.mark.parametrize(
    ("zabbix_severity", "expected"),
    [
        ("Disaster", "critical"),
        ("High", "high"),
        ("Average", "medium"),
        ("Warning", "warning"),
        ("Information", "info"),
        ("Not classified", "info"),
        ("", "info"),
    ],
)
def test_normalize_zabbix_keeps_each_severity_level_distinct(zabbix_severity, expected):
    """Six Zabbix levels map onto six Beacon levels; High is not a Disaster."""
    payload = {
        "event_id": "12345",
        "event_name": "Disk is filling up",
        "event_status": "PROBLEM",
        "event_severity": zabbix_severity,
    }

    alerts = normalize_zabbix(payload)

    assert alerts[0]["severity"] == expected


def test_normalize_zabbix_adds_event_link_to_labels():
    payload = {
        "event_id": "123",
        "trigger_id": "456",
        "event_name": "CPU load is high",
        "event_status": "PROBLEM",
        "event_severity": "High",
        "event_link": "https://zabbix.example.com/tr_events.php?triggerid=456&eventid=123",
        "labels": {
            "team": "infra",
        },
    }

    alerts = normalize_zabbix(payload)

    assert len(alerts) == 1
    assert alerts[0]["labels"]["event_link"] == (
        "https://zabbix.example.com/tr_events.php?triggerid=456&eventid=123"
    )


def test_normalize_zabbix_builds_event_link_from_zabbix_url():
    payload = {
        "event_id": "123",
        "trigger_id": "456",
        "event_name": "CPU load is high",
        "event_status": "PROBLEM",
        "event_severity": "High",
        "zabbix_url": "https://zabbix.example.com",
    }

    alerts = normalize_zabbix(payload)

    assert alerts[0]["labels"]["event_link"] == (
        "https://zabbix.example.com/tr_events.php?triggerid=456&eventid=123"
    )


def test_normalize_alertmanager_adds_generator_url_as_event_link():
    payload = {
        "status": "firing",
        "externalURL": "https://alertmanager.example.com",
        "alerts": [
            {
                "status": "firing",
                "labels": {
                    "alertname": "DiskFull",
                    "severity": "critical",
                    "team": "infra",
                },
                "annotations": {
                    "summary": "Disk is full",
                    "description": "/var is 95% full",
                },
                "generatorURL": "https://prometheus.example.com/graph?g0.expr=DiskFull",
                "fingerprint": "disk-full-host1-var",
            }
        ],
    }

    alerts = normalize_alertmanager(payload)

    assert alerts[0]["labels"]["event_link"] == (
        "https://prometheus.example.com/graph?g0.expr=DiskFull"
    )
    assert alerts[0]["labels"]["generator_url"] == (
        "https://prometheus.example.com/graph?g0.expr=DiskFull"
    )
    assert alerts[0]["labels"]["alertmanager_url"] == (
        "https://alertmanager.example.com"
    )


def test_normalize_webhook_adds_event_link_to_labels():
    payload = {
        "title": "Custom alert",
        "message": "Something is broken",
        "severity": "critical",
        "event_link": "https://monitoring.example.com/events/123",
        "labels": {
            "team": "infra",
        },
    }

    alerts = normalize_webhook(payload)

    assert alerts[0]["labels"]["event_link"] == (
        "https://monitoring.example.com/events/123"
    )
