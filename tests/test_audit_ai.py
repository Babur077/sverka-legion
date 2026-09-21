import json

from backend.app.services import audit_ai


def _event(**overrides):
    event = {
        "id": 42,
        "timestamp": "2026-09-21T12:00:00",
        "user_id": "alice",
        "action": "RECONCILIATION_RUN",
        "module_id": "bank_rrn",
        "object_type": "RunResult",
        "object_id": "run-secret-123",
        "status": "SUCCESS",
        "ip_address": "10.20.30.40",
        "duration_ms": 120.0,
        "details": "regular run",
    }
    event.update(overrides)
    return event


def test_failed_audit_event_is_marked_for_review(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    result = audit_ai.analyze_audit_event(
        _event(
            action="RECONCILIATION_RUN_FAILED",
            status="FAILED",
            details="broken input file",
        )
    )

    assert result["provider"] == "local"
    assert result["attention_level"] == "review"
    assert result["attention_label"] == "Стоит проверить"
    assert result["checks"]


def test_successful_delete_requires_attention(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    result = audit_ai.analyze_audit_event(
        _event(action="ARCHIVE_DELETE", status="SUCCESS")
    )

    assert result["attention_level"] == "attention"
    assert "удал" in (result["summary"] + result["explanation"]).lower()


def test_external_ai_context_excludes_direct_identifiers_and_redacts_details():
    event = _event(
        user_id="sensitive-user",
        object_id="private-run-id",
        ip_address="192.168.1.25",
        details=(
            "user sensitive-user object private-run-id "
            "contact finance@example.com ip 172.16.0.3 "
            "api_key=super-secret-value "
            "uuid 123e4567-e89b-12d3-a456-426614174000 "
            "cardlike 1234567890123456"
        ),
    )

    context = audit_ai.build_audit_ai_context(event)
    serialized = json.dumps(context, ensure_ascii=False)

    assert "sensitive-user" not in serialized
    assert "private-run-id" not in serialized
    assert "192.168.1.25" not in serialized
    assert "finance@example.com" not in serialized
    assert "172.16.0.3" not in serialized
    assert "super-secret-value" not in serialized
    assert "123e4567-e89b-12d3-a456-426614174000" not in serialized
    assert "1234567890123456" not in serialized
    assert context["has_object_id"] is True
