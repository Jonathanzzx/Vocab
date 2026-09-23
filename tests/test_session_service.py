"""Terminal and browser sessions select the same bounded batch."""
import importlib
from io import StringIO

import pytest
from rich.console import Console

from vocab.db import Database
from vocab.web.study import StudySession


@pytest.mark.parametrize("mode,renderer", [
    ("flashcard", "render_flashcard_front"),
    ("typing", "render_typing_prompt"),
    ("quiz", "render_quiz_question"),
])
def test_terminal_completes_same_batch_as_browser(tmp_path, monkeypatch, mode, renderer):
    db = Database(str(tmp_path / "library.db"))
    gid = db.create_group("Study")
    for i in range(14):
        db.add_word(gid, f"word-{i}", "Meaning")
    db.set_setting("capacity_threshold", "60")
    browser = StudySession(db, {"group_id": gid, "mode": mode, "limit": 20, "shuffle": False})
    expected = {browser.current.id, *(word.id for word in browser.queue.queue)}
    assert len(expected) == 3

    terminal = importlib.import_module(f"vocab.sessions.{mode}_session")
    seen = []
    current = {}

    def render(word, **values):
        seen.append(word.id)
        assert len(seen) <= 10, "The terminal session should finish its bounded batch."
        current.update(word=word.word, **values)

    def answer(prompt=""):
        if mode == "quiz":
            return str(current["choices"].index(current["word"]) + 1)
        return "3" if prompt else ""

    monkeypatch.setattr(terminal, renderer, render)
    monkeypatch.setattr(terminal, "render_header", lambda *args: None)
    monkeypatch.setattr(terminal, "pause_prompt", lambda: None)
    monkeypatch.setattr(terminal, "console", Console(file=StringIO()))
    monkeypatch.setattr(terminal.time, "sleep", lambda seconds: None)
    monkeypatch.setattr("builtins.input", answer)
    if mode == "typing":
        monkeypatch.setattr(terminal, "prompt", lambda *args: current["word"])
    if mode == "flashcard":
        monkeypatch.setattr(terminal, "render_flashcard_back", lambda **kwargs: None)

    stats = getattr(terminal, f"run_{mode}_session")(
        db, gid, limit=20, shuffle=False, auto_add_due=True,
    )
    assert set(seen) == expected
    assert stats.unique_words == 3
    assert stats.total_reviews == 3
