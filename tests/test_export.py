"""
Unit tests for CSV and JSON import/export.
"""
import os
import tempfile
import pytest
from vocab.db import Database
from vocab.exporter import DataExporter


@pytest.fixture
def populated_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    db = Database(db_path)
    gid = db.create_group("Spanish A1", "Beginner Spanish", "green")
    db.add_word(
        group_id=gid,
        word="madrugada",
        definition="Early morning hours before dawn",
        pos="noun",
        example="Nos despertamos de madrugada."
    )
    db.add_word(
        group_id=gid,
        word="sobremesa",
        definition="Conversation around table after eating",
        pos="noun"
    )
    yield db
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
        except Exception:
            pass


def test_csv_export_and_import(populated_db):
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        csv_path = f.name

    try:
        # Export
        count = DataExporter.export_to_csv(populated_db, csv_path)
        assert count == 2
        assert os.path.getsize(csv_path) > 0

        # Import into fresh DB
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f2:
            new_db_path = f2.name
        new_db = Database(new_db_path)

        groups_added, words_added = DataExporter.import_from_csv(new_db, csv_path)
        assert groups_added == 1
        assert words_added == 2

        imported_words = new_db.get_words()
        assert len(imported_words) == 2
        terms = {w.word for w in imported_words}
        assert "madrugada" in terms
        assert "sobremesa" in terms

        if os.path.exists(new_db_path):
            try:
                os.remove(new_db_path)
            except Exception:
                pass
    finally:
        if os.path.exists(csv_path):
            os.remove(csv_path)


def test_json_export_and_import(populated_db):
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        json_path = f.name

    try:
        # Export
        count = DataExporter.export_to_json(populated_db, json_path)
        assert count == 2
        assert os.path.getsize(json_path) > 0

        # Import into fresh DB
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f2:
            new_db_path = f2.name
        new_db = Database(new_db_path)

        groups_added, words_added = DataExporter.import_from_json(new_db, json_path)
        assert groups_added == 1
        assert words_added == 2

        imported_words = new_db.get_words()
        assert len(imported_words) == 2

        if os.path.exists(new_db_path):
            try:
                os.remove(new_db_path)
            except Exception:
                pass
    finally:
        if os.path.exists(json_path):
            os.remove(json_path)
