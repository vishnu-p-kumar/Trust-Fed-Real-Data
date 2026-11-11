from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

import src.alert_engine as alert_engine
from src.alert_engine import _send_telegram, build_alert_messages, send_backend_status_message, send_inspector_welcome_message


def test_build_alert_messages_includes_theft_and_pole_tamper_with_labels() -> None:
    frame = pd.DataFrame(
        [
            {
                "meter_id": "M1001",
                "area": "Indiranagar",
                "status": "Electricity Theft",
                "risk_score": 88.5,
                "theft_probability": 0.9132,
            },
            {
                "pole_id": "P0001",
                "area": "Whitefield",
                "tamper_probability": 0.97,
            },
            {
                "meter_id": "M1002",
                "area": "HSR Layout",
                "status": "Normal",
                "risk_score": 40.0,
                "theft_probability": 0.2201,
            },
        ]
    )

    alerts = build_alert_messages(frame, limit=5)

    assert len(alerts) == 2
    theft_alert = next(alert for alert in alerts if alert["category"] == "Electricity Theft")
    pole_alert = next(alert for alert in alerts if alert["category"] == "Pole Tamper")
    assert theft_alert["area"] == "Indiranagar"
    assert theft_alert["risk_score"] == 88.5
    assert theft_alert["theft_probability"] == 0.9132
    assert theft_alert["message"] == "Electricity Theft | Area: Indiranagar | Risk score: 88.50 | Theft probability: 0.9132"
    assert pole_alert["area"] == "Whitefield"
    assert pole_alert["tamper_probability"] == 0.97
    assert pole_alert["message"] == "Pole Tamper | Area: Whitefield | Pole: P0001 | Tamper probability: 0.9700"


def test_build_alert_messages_returns_all_detected_alerts_when_limit_is_none() -> None:
    frame = pd.DataFrame(
        [
            {
                "meter_id": "M1001",
                "area": "Indiranagar",
                "status": "Electricity Theft",
                "risk_score": 88.5,
                "theft_probability": 0.9132,
            },
            {
                "meter_id": "M1002",
                "area": "Whitefield",
                "status": "Electricity Theft",
                "risk_score": 91.2,
                "theft_probability": 0.9541,
            },
            {
                "pole_id": "P0001",
                "area": "HSR Layout",
                "tamper_probability": 0.97,
            },
        ]
    )

    alerts = build_alert_messages(frame, limit=None)

    assert len(alerts) == 3
    assert {alert["area"] for alert in alerts} == {"Indiranagar", "Whitefield", "HSR Layout"}


def test_send_telegram_routes_area_alerts_to_matching_inspector(monkeypatch) -> None:
    sent_payloads: list[dict[str, str]] = []
    alert_engine._telegram_last_sent_at.clear()
    alert_engine._telegram_last_message.clear()

    class DummyResponse:
        def raise_for_status(self) -> None:
            return None

    monkeypatch.setenv("SMARTGRID_TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setattr(
        alert_engine,
        "ensure_users_file",
        lambda: {
            "inspectors": [
                {"username": "alpha", "assigned_area": "Indiranagar", "chat_id": "111111"},
                {"username": "beta", "assigned_area": "Whitefield", "chat_id": "222222"},
                {"username": "gamma", "assigned_area": "HSR Layout", "chat_id": ""},
            ]
        },
    )
    monkeypatch.setattr(
        alert_engine.requests,
        "post",
        lambda _url, json, timeout: sent_payloads.append(json) or DummyResponse(),
    )

    result = _send_telegram(
        [
            {"area": "Indiranagar", "message": "Electricity Theft | Area: Indiranagar | Risk score: 88.50 | Theft probability: 0.9132"},
            {"area": "Whitefield", "message": "Electricity Theft | Area: Whitefield | Risk score: 91.20 | Theft probability: 0.9541"},
            {"area": "Whitefield", "message": "Pole Tamper | Area: Whitefield | Pole: P0001 | Tamper probability: 0.9700"},
            {"area": "Banashankari", "message": "Electricity Theft | Area: Banashankari | Risk score: 82.10 | Theft probability: 0.9012"},
        ]
    )

    assert result == {"provider": "telegram", "status": "sent", "count": 3, "recipients": 2}
    assert sent_payloads == [
        {"chat_id": "111111", "text": "Electricity Theft | Area: Indiranagar | Risk score: 88.50 | Theft probability: 0.9132"},
        {"chat_id": "222222", "text": "Electricity Theft | Area: Whitefield | Risk score: 91.20 | Theft probability: 0.9541\nPole Tamper | Area: Whitefield | Pole: P0001 | Tamper probability: 0.9700"},
    ]


def test_send_telegram_notifies_all_matching_inspectors_for_their_detected_areas(monkeypatch) -> None:
    sent_payloads: list[dict[str, str]] = []
    alert_engine._telegram_last_sent_at.clear()
    alert_engine._telegram_last_message.clear()

    class DummyResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"ok": True}

    monkeypatch.setenv("SMARTGRID_TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setattr(
        alert_engine,
        "ensure_users_file",
        lambda: {
            "inspectors": [
                {"username": "alpha", "assigned_area": "Indiranagar", "chat_id": "111111"},
                {"username": "beta", "assigned_area": "Whitefield", "chat_id": "222222"},
                {"username": "gamma", "assigned_area": "HSR Layout", "chat_id": "333333"},
            ]
        },
    )
    monkeypatch.setattr(
        alert_engine.requests,
        "post",
        lambda _url, json, timeout: sent_payloads.append(json) or DummyResponse(),
    )

    result = _send_telegram(
        [
            {"area": "Indiranagar", "message": "Electricity Theft | Area: Indiranagar | Risk score: 88.50 | Theft probability: 0.9132"},
            {"area": "Whitefield", "message": "Electricity Theft | Area: Whitefield | Risk score: 91.20 | Theft probability: 0.9541"},
            {"area": "HSR Layout", "message": "Pole Tamper | Area: HSR Layout | Pole: P0001 | Tamper probability: 0.9700"},
        ]
    )

    assert result == {"provider": "telegram", "status": "sent", "count": 3, "recipients": 3}
    assert sent_payloads == [
        {"chat_id": "111111", "text": "Electricity Theft | Area: Indiranagar | Risk score: 88.50 | Theft probability: 0.9132"},
        {"chat_id": "222222", "text": "Electricity Theft | Area: Whitefield | Risk score: 91.20 | Theft probability: 0.9541"},
        {"chat_id": "333333", "text": "Pole Tamper | Area: HSR Layout | Pole: P0001 | Tamper probability: 0.9700"},
    ]


def test_send_telegram_uses_env_chat_id_as_fallback_recipient(monkeypatch) -> None:
    sent_payloads: list[dict[str, str]] = []
    alert_engine._telegram_last_sent_at.clear()
    alert_engine._telegram_last_message.clear()

    class DummyResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"ok": True}

    monkeypatch.setenv("SMARTGRID_TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("SMARTGRID_TELEGRAM_CHAT_ID", "999999")
    monkeypatch.setattr(
        alert_engine,
        "ensure_users_file",
        lambda: {"inspectors": [{"username": "alpha", "assigned_area": "Whitefield", "chat_id": "111111"}]},
    )
    monkeypatch.setattr(
        alert_engine.requests,
        "post",
        lambda _url, json, timeout: sent_payloads.append(json) or DummyResponse(),
    )

    result = _send_telegram(
        [
            {"area": "Banashankari", "message": "Electricity Theft | Area: Banashankari | Risk score: 82.10 | Theft probability: 0.9012"},
        ]
    )

    assert result == {"provider": "telegram", "status": "sent", "count": 1, "recipients": 1}
    assert sent_payloads == [
        {"chat_id": "999999", "text": "Electricity Theft | Area: Banashankari | Risk score: 82.10 | Theft probability: 0.9012"},
    ]


def test_send_telegram_raises_when_telegram_api_returns_ok_false(monkeypatch) -> None:
    alert_engine._telegram_last_sent_at.clear()
    alert_engine._telegram_last_message.clear()

    class DummyResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"ok": False, "description": "Forbidden: bot was blocked by the user"}

    monkeypatch.setenv("SMARTGRID_TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setattr(
        alert_engine,
        "ensure_users_file",
        lambda: {"inspectors": [{"username": "alpha", "assigned_area": "Indiranagar", "chat_id": "111111"}]},
    )
    monkeypatch.setattr(alert_engine.requests, "post", lambda _url, json, timeout: DummyResponse())

    result = alert_engine.dispatch_alerts(
        pd.DataFrame(
            [
                {
                    "area": "Indiranagar",
                    "status": "Electricity Theft",
                    "risk_score": 88.5,
                    "theft_probability": 0.9132,
                }
            ]
        ),
        limit=5,
    )

    assert result[-1] == {
        "provider": "telegram",
        "status": "error",
        "detail": "Forbidden: bot was blocked by the user",
    }


def test_send_telegram_throttles_same_inspector_for_five_minutes(monkeypatch) -> None:
    sent_payloads: list[dict[str, str]] = []
    alert_engine._telegram_last_sent_at.clear()
    alert_engine._telegram_last_message.clear()

    class DummyResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"ok": True}

    monkeypatch.setenv("SMARTGRID_TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setattr(
        alert_engine,
        "ensure_users_file",
        lambda: {"inspectors": [{"username": "alpha", "assigned_area": "Whitefield", "chat_id": "111111"}]},
    )
    monkeypatch.setattr(
        alert_engine.requests,
        "post",
        lambda _url, json, timeout: sent_payloads.append(json) or DummyResponse(),
    )

    first = _send_telegram(
        [{"area": "Whitefield", "message": "Electricity Theft | Area: Whitefield | Risk score: 68.91 | Theft probability: 0.9100"}]
    )
    second = _send_telegram(
        [{"area": "Whitefield", "message": "Electricity Theft | Area: Whitefield | Risk score: 68.91 | Theft probability: 0.9100"}]
    )

    assert first == {"provider": "telegram", "status": "sent", "count": 1, "recipients": 1}
    assert second == {"provider": "telegram", "status": "throttled", "recipients": 0, "throttled": 1}
    assert sent_payloads == [
        {"chat_id": "111111", "text": "Electricity Theft | Area: Whitefield | Risk score: 68.91 | Theft probability: 0.9100"}
    ]

    alert_engine._telegram_last_sent_at["alpha"] = datetime.now(timezone.utc) - timedelta(minutes=6)
    third = _send_telegram(
        [{"area": "Whitefield", "message": "Electricity Theft | Area: Whitefield | Risk score: 68.91 | Theft probability: 0.9100"}]
    )

    assert third == {"provider": "telegram", "status": "sent", "count": 1, "recipients": 1}
    assert len(sent_payloads) == 2


def test_send_telegram_sends_new_content_within_cooldown_for_same_inspector(monkeypatch) -> None:
    sent_payloads: list[dict[str, str]] = []
    alert_engine._telegram_last_sent_at.clear()
    alert_engine._telegram_last_message.clear()

    class DummyResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"ok": True}

    monkeypatch.setenv("SMARTGRID_TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setattr(
        alert_engine,
        "ensure_users_file",
        lambda: {"inspectors": [{"username": "alpha", "assigned_area": "HSR Layout", "chat_id": "111111"}]},
    )
    monkeypatch.setattr(
        alert_engine.requests,
        "post",
        lambda _url, json, timeout: sent_payloads.append(json) or DummyResponse(),
    )

    first = _send_telegram(
        [{"area": "HSR Layout", "message": "Electricity Theft | Area: HSR Layout | Risk score: 67.15 | Theft probability: 0.9100"}]
    )
    second = _send_telegram(
        [{"area": "HSR Layout", "message": "Pole Tamper | Area: HSR Layout | Pole: P0086 | Tamper probability: 0.8158"}]
    )

    assert first == {"provider": "telegram", "status": "sent", "count": 1, "recipients": 1}
    assert second == {"provider": "telegram", "status": "sent", "count": 1, "recipients": 1}
    assert sent_payloads == [
        {"chat_id": "111111", "text": "Electricity Theft | Area: HSR Layout | Risk score: 67.15 | Theft probability: 0.9100"},
        {"chat_id": "111111", "text": "Pole Tamper | Area: HSR Layout | Pole: P0086 | Tamper probability: 0.8158"},
    ]


def test_send_telegram_reports_skipped_reason_when_no_matching_recipient(monkeypatch) -> None:
    alert_engine._telegram_last_sent_at.clear()
    alert_engine._telegram_last_message.clear()

    monkeypatch.setenv("SMARTGRID_TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.delenv("SMARTGRID_TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.setattr(
        alert_engine,
        "ensure_users_file",
        lambda: {"inspectors": [{"username": "alpha", "assigned_area": "Whitefield", "chat_id": "111111"}]},
    )

    result = _send_telegram(
        [{"area": "Banashankari", "message": "Electricity Theft | Area: Banashankari | Risk score: 82.10 | Theft probability: 0.9012"}]
    )

    assert result == {
        "provider": "telegram",
        "status": "skipped",
        "detail": "No inspector chat_id matched the alert areas, and SMARTGRID_TELEGRAM_CHAT_ID fallback is empty.",
    }


def test_send_inspector_welcome_message_sends_direct_message(monkeypatch) -> None:
    sent_payloads: list[dict[str, str]] = []

    class DummyResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"ok": True}

    monkeypatch.setenv("SMARTGRID_TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setattr(
        alert_engine.requests,
        "post",
        lambda _url, json, timeout: sent_payloads.append(json) or DummyResponse(),
    )

    result = send_inspector_welcome_message(
        {
            "name": "Field One",
            "username": "inspector1",
            "assigned_area": "Area A",
            "chat_id": "1242950500",
        }
    )

    assert result == {"provider": "telegram", "status": "sent", "recipients": 1, "count": 1}
    assert sent_payloads == [
        {
            "chat_id": "1242950500",
            "text": "Welcome Field One.\nYour Smart Grid inspector account has been created successfully.\nUsername: inspector1\nAssigned area: Area A\nYou will receive field alerts here when activity is detected in your assigned area.",
        }
    ]


def test_send_backend_status_message_uses_configured_status_chat(monkeypatch) -> None:
    sent_payloads: list[dict[str, str]] = []

    class DummyResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"ok": True}

    monkeypatch.setenv("SMARTGRID_TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("SMARTGRID_TELEGRAM_CHAT_ID", "999999")
    monkeypatch.setattr(
        alert_engine.requests,
        "post",
        lambda _url, json, timeout: sent_payloads.append(json) or DummyResponse(),
    )

    result = send_backend_status_message("Smart Grid backend started", ["Current tick: ready"])

    assert result == {"provider": "telegram", "status": "sent", "count": 1, "recipients": 1}
    assert sent_payloads == [{"chat_id": "999999", "text": "Smart Grid backend started\nCurrent tick: ready"}]


def test_send_inspector_welcome_message_skips_without_bot_token(monkeypatch) -> None:
    monkeypatch.delenv("SMARTGRID_TELEGRAM_BOT_TOKEN", raising=False)

    result = send_inspector_welcome_message(
        {
            "name": "Field One",
            "username": "inspector1",
            "assigned_area": "Area A",
            "chat_id": "1242950500",
        }
    )

    assert result == {
        "provider": "telegram",
        "status": "skipped",
        "detail": "SMARTGRID_TELEGRAM_BOT_TOKEN is not configured in the running API process.",
    }
