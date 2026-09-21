from backend.app.repositories import definitions
from backend.db.migrations.runner import run_migrations


def test_definition_updates_create_immutable_versions(tmp_path, monkeypatch):
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
        change_note="Initial rules",
    )

    assert ok is True
    assert definition_id is not None
    assert "v1" in message

    item = definitions.get_definition(definition_id)
    assert item["name"] == "1C ↔ Bank"
    assert item["config"]["amount_tolerance"] == 100
    assert item["current_version_number"] == 1
    assert item["active_version_id"] is not None

    versions = definitions.list_definition_versions(definition_id)
    assert len(versions) == 1
    assert versions[0]["version_number"] == 1
    assert versions[0]["status"] == "ACTIVE"
    assert versions[0]["change_note"] == "Initial rules"

    v1_id = versions[0]["id"]

    ok, message, updated_id = definitions.save_definition(
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
        username="editor",
        change_note="Add account to key",
    )

    assert ok is True
    assert updated_id == definition_id
    assert "v2" in message

    item = definitions.get_definition(definition_id)
    assert item["name"] == "1C ↔ Bank updated"
    assert item["config"]["amount_tolerance"] == 0
    assert item["current_version_number"] == 2
    assert item["version_created_by"] == "editor"

    versions = definitions.list_definition_versions(definition_id)
    assert [version["version_number"] for version in versions] == [2, 1]
    assert versions[0]["status"] == "ACTIVE"
    assert versions[1]["status"] == "ARCHIVED"
    assert versions[0]["based_on_version_id"] == v1_id
    assert versions[0]["change_note"] == "Add account to key"


def test_restoring_old_version_creates_new_version_without_rewriting_history(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / "restore.db"
    run_migrations(str(db_path))
    monkeypatch.setattr(definitions, "DB_PATH", str(db_path))

    ok, _, definition_id = definitions.save_definition(
        name="Bank template",
        description="v1",
        config={"key_pairs": [], "amount_tolerance": 10},
        username="author",
    )
    assert ok

    v1 = definitions.list_definition_versions(definition_id)[0]

    ok, _, _ = definitions.save_definition(
        definition_id=definition_id,
        name="Bank template",
        description="v2",
        config={"key_pairs": [], "amount_tolerance": 500},
        username="editor",
    )
    assert ok

    ok, message, restored = definitions.restore_definition_version(
        definition_id=definition_id,
        version_id=v1["id"],
        username="reviewer",
        change_note="Rollback after validation",
    )

    assert ok is True
    assert "v3" in message
    assert restored["current_version_number"] == 3
    assert restored["config"]["amount_tolerance"] == 10
    assert restored["description"] == "v1"

    versions = definitions.list_definition_versions(definition_id)
    assert [version["version_number"] for version in versions] == [3, 2, 1]
    assert versions[0]["status"] == "ACTIVE"
    assert versions[1]["status"] == "ARCHIVED"
    assert versions[2]["status"] == "ARCHIVED"
    assert versions[0]["restored_from_version_id"] == v1["id"]
    assert versions[0]["change_note"] == "Rollback after validation"

    # Historical snapshots remain unchanged.
    assert versions[2]["config"]["amount_tolerance"] == 10
    assert versions[1]["config"]["amount_tolerance"] == 500


def test_definition_deactivation_keeps_version_history(tmp_path, monkeypatch):
    db_path = tmp_path / "deactivate.db"
    run_migrations(str(db_path))
    monkeypatch.setattr(definitions, "DB_PATH", str(db_path))

    ok, _, definition_id = definitions.save_definition(
        name="Template",
        description="",
        config={"key_pairs": [], "amount_tolerance": 0},
        username="tester",
    )
    assert ok

    assert definitions.deactivate_definition(definition_id) is True
    assert definitions.list_definitions() == []
    assert len(definitions.list_definition_versions(definition_id)) == 1
