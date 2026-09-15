"""
Unit tests for word list view, filtering, sorting, and CLI actions.
"""
import os
import tempfile
from io import StringIO
import pytest
from rich.console import Console

from vocab.db import Database
from vocab import show_words_list, browse_words_view
from vocab.ui.forms import render_words_table, get_sort_label, prompt_sort_options, prompt_state_filter
from vocab.app import main


@pytest.fixture
def test_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    db = Database(db_path)
    
    # Setup test groups and words
    g1 = db.create_group("Academic")
    g2 = db.create_group("Technical")

    db.add_word(g1, "ephemeral", "lasting for a very short time", pos="adjective", tags="gre, lit")
    db.add_word(g1, "pragmatic", "dealing with things sensibly", pos="adjective", tags="gre, logic")
    db.add_word(g2, "idempotent", "same result on multiple executions", pos="adjective", tags="tech, api")
    db.add_word(g2, "concurrency", "executing multiple tasks simultaneously", pos="noun", tags="tech, os")

    yield db

    if os.path.exists(db_path):
        try:
            os.remove(db_path)
        except Exception:
            pass


def test_show_words_list_basic(test_db):
    """Test show_words_list non-interactive returns all words and prints table."""
    buf = StringIO()
    test_console = Console(file=buf, force_terminal=False, color_system=None)

    words = show_words_list(test_db, console_out=test_console)
    assert len(words) == 4
    output = buf.getvalue()
    assert "Words Library & Manager" in output
    assert "ephemeral" in output
    assert "pragmatic" in output
    assert "idempotent" in output
    assert "concurrency" in output


def test_show_words_list_filtering_and_sorting(test_db):
    """Test show_words_list with filter and sort arguments."""
    buf = StringIO()
    test_console = Console(file=buf, force_terminal=False, color_system=None)

    # Filter by group (Academic) and sort alphabetical A-Z
    g_acad = test_db.get_group_by_name("Academic")
    words = show_words_list(
        test_db,
        group_id=g_acad.id,
        sort_by="word",
        sort_order="asc",
        console_out=test_console
    )
    assert len(words) == 2
    assert words[0].word == "ephemeral"
    assert words[1].word == "pragmatic"

    # Filter by POS (noun)
    buf.seek(0)
    buf.truncate(0)
    noun_words = show_words_list(
        test_db,
        pos="noun",
        console_out=test_console
    )
    assert len(noun_words) == 1
    assert noun_words[0].word == "concurrency"

    # Filter by search keyword
    buf.seek(0)
    buf.truncate(0)
    searched = show_words_list(
        test_db,
        search="sensibly",
        console_out=test_console
    )
    assert len(searched) == 1
    assert searched[0].word == "pragmatic"


def test_show_words_list_empty_results(test_db):
    """Test show_words_list when no words match filters."""
    buf = StringIO()
    test_console = Console(file=buf, force_terminal=False, color_system=None)

    words = show_words_list(
        test_db,
        search="nonexistent_word_xyz",
        console_out=test_console
    )
    assert words == []
    output = buf.getvalue()
    assert "No words found matching" in output


def test_get_sort_label():
    """Test friendly sort label mapping."""
    assert "A-Z" in get_sort_label("word", "asc")
    assert "Z-A" in get_sort_label("word", "desc")
    assert "Soonest" in get_sort_label("due", "asc")
    assert "Hardest" in get_sort_label("ease", "asc")
    assert "Shortest" in get_sort_label("interval", "asc")
    assert "Newest" in get_sort_label("id", "desc")


def test_cli_list_action(test_db, monkeypatch):
    """Test CLI direct action 'python main.py list' with filtering and sorting."""
    # Test listing with CLI arguments
    argv = [
        "main.py",
        "list",
        "--db", test_db.db_path,
        "--sort", "word",
        "--order", "asc",
        "--limit", "10"
    ]
    monkeypatch.setattr("sys.argv", argv)
    
    # Should run and exit without error
    main()


def test_show_words_list_due_and_state_filtering(test_db):
    """Test filtering by due_only, state, and tag."""
    buf = StringIO()
    test_console = Console(file=buf, force_terminal=False, color_system=None)

    # By default all newly added words are state='new' and due
    due_words = show_words_list(test_db, due_only=True, console_out=test_console)
    assert len(due_words) == 4

    # Filter by tag
    tag_words = show_words_list(test_db, tag="tech", console_out=test_console)
    assert len(tag_words) == 2
    assert {w.word for w in tag_words} == {"idempotent", "concurrency"}

    # Filter by state
    new_words = show_words_list(test_db, state="new", console_out=test_console)
    assert len(new_words) == 4

    learning_words = show_words_list(test_db, state="learning", console_out=test_console)
    assert len(learning_words) == 0


def test_show_words_list_pagination(test_db):
    """Test pagination with limit and offset."""
    buf = StringIO()
    test_console = Console(file=buf, force_terminal=False, color_system=None)

    page1 = show_words_list(test_db, sort_by="word", sort_order="asc", limit=2, offset=0, console_out=test_console)
    assert len(page1) == 2
    assert page1[0].word == "concurrency"
    assert page1[1].word == "ephemeral"

    page2 = show_words_list(test_db, sort_by="word", sort_order="asc", limit=2, offset=2, console_out=test_console)
    assert len(page2) == 2
    assert page2[0].word == "idempotent"
    assert page2[1].word == "pragmatic"


def test_package_exports():
    """Test that show_words_list, browse_words_view, show_words are exported from top-level vocab."""
    import vocab
    assert hasattr(vocab, "show_words_list")
    assert hasattr(vocab, "browse_words_view")
    assert hasattr(vocab, "show_words")
    assert callable(vocab.show_words_list)


def test_show_words_list_mastered_filter_and_rendering(test_db):
    """Test filtering by state='mastered' and that the 🏆 mastered badge is rendered."""
    words = test_db.get_words(limit=1)
    target_id = words[0].id
    test_db.set_word_mastery(target_id, True)

    buf = StringIO()
    test_console = Console(file=buf, force_terminal=False, color_system=None)

    # Filter by mastered
    mastered_words = show_words_list(test_db, state="mastered", console_out=test_console)
    assert len(mastered_words) == 1
    assert mastered_words[0].id == target_id
    assert mastered_words[0].state == "mastered"

    # Verify rendered table output contains mastered indicator
    output = buf.getvalue()
    assert "mastered" in output

    # Due-only filter should NOT include the mastered word
    buf.seek(0)
    buf.truncate(0)
    due_words = show_words_list(test_db, due_only=True, console_out=test_console)
    assert target_id not in [w.id for w in due_words]


