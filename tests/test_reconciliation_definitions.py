from backend.app.repositories import definitions
from backend.db.migrations.runner import run_migrations


def test_definition_crud_uses_versioned_schema(tmp_path, monkeypatch):
    db_path = tmp_path / "definitions.db"
    run_migrations(str(db_path))
    monkeypatch.setattr(definitions, "DB_PATH", str(db_path))

    ok, message, definition_id = definitions.save_definition(
        name="1C ↔ Bank",
        description="Test template",
        config={
            "key_pairs": [
                {"left": "Document", "right": "DocNo", "mode": "text"},
            ],
            "amount_tolerance": 100,
        },
        username="tester",
    )

    assert ok is True
    assert definition_id is not None
    assert "сохранён" in message

    items = definitions.list_definitions()
    assert len(items) == 1
    assert items[0]["name"] == "1C ↔ Bank"
    assert items[0]["config"]["amount_tolerance"] == 100

    ok, _, updated_id = definitions.save_definition(
        definition_id=definition_id,
        name="1C ↔ Bank updated",
        description="Updated",
        config={
            "key_pairs": [
                {"left": "Document", "right": "DocNo", "mode": "text"},
                {"left": "Account", "right": "Account", "mode": "exact"},
            ],
            "amount_tolerance": 0,
        },
        username="tester",
    )
    assert ok is True
    assert updated_id == definition_id
    assert definitions.get_definition(definition_id)["name"] == "1C ↔ Bank updated"

    assert definitions.deactivate_definition(definition_id) is True
    assert definitions.list_definitions() == []
