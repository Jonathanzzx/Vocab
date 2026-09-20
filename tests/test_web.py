"""Browser API integration: shared scheduling, persistence, and data boundaries."""
import io
import json
from dataclasses import asdict
from datetime import datetime, timedelta, timezone

import pytest

from vocab.db import Database
from vocab.models import SRSGrade
from vocab.scheduler import SRSEngine
from vocab.web import create_app
from vocab.test_service import TestQuestion, VocabTestService


@pytest.fixture
def web(tmp_path):
    app = create_app(str(tmp_path / "library.db"), testing=True, seed=False)
    client = app.test_client()
    csrf = client.get("/api/bootstrap").json["csrf"]
    db = app.extensions["vocab_db"]
    gid = db.create_group("Research", "A test deck")
    for word in ("evidence", "hypothesis", "replication", "inference"):
        db.add_word(gid, word, f"Meaning of {word}")
    return app, client, {"X-CSRF-Token": csrf}, db, gid


def post(web, path, data):
    return web[1].post(f"/api/{path}", json=data, headers=web[2])


def start(web, **options):
    response = post(web, "sessions", {"group_id": web[4], "limit": 1, "shuffle": False,
                                     "auto_add_due": False, **options})
    assert response.status_code == 201, response.json
    return response.json


def act(web, state, action, **values):
    return post(web, f"sessions/{state['id']}", {"token": state["token"], "action": action, **values})


def test_browser_shell_and_read_views(web):
    client = web[1]
    assert b"Learning workspace" in client.get("/").data
    for url in ("/static/app.js", "/static/styles.css", "/api/dashboard", "/api/groups", "/api/words", "/api/checks", "/api/research"):
        assert client.get(url).status_code == 200
    dashboard = client.get("/api/dashboard").json
    assert dashboard["stats"]["total_words"] == 4
    assert list(dashboard["forecast"])[0] == "Today"


def test_deck_word_crud_and_terminal_visibility(web):
    _, client, headers, db, _ = web
    gid = post(web, "groups", {"name": "Literature", "description": "Notes"}).json["group"]["id"]
    word = post(web, "words", {"group_id": gid, "word": "palimpsest", "definition": "A reused manuscript", "tags": "books"}).json["word"]
    response = client.patch(f"/api/words/{word['id']}", headers=headers, json={"definition": "Updated", "retired": True})
    assert response.status_code == 200
    # A fresh terminal Database reads the exact same persisted result.
    saved = Database(db.db_path).get_word_by_id(word["id"])
    assert saved.definition == "Updated" and saved.state == "mastered"
    filtered = client.get("/api/words?search=palimpsest&tag=books&state=mastered").json
    assert filtered["total"] == 1
    assert client.patch(f"/api/groups/{gid}", headers=headers, json={"name": "Reading"}).status_code == 200
    assert client.delete(f"/api/groups/{gid}", headers=headers).status_code == 200
    assert db.get_word_by_id(word["id"]) is None


@pytest.mark.parametrize("entry,word,definition", [
    ("salient: most noticeable", "salient", "most noticeable"),
    ("laconic = using few words", "laconic", "using few words"),
    ("liminal - at a boundary", "liminal", "at a boundary"),
])
def test_continuous_add_parses_terminal_entry_formats(web, monkeypatch, entry, word, definition):
    calls = []
    monkeypatch.setattr("vocab.web.BackgroundEnricher.enrich", lambda **values: calls.append(values))
    response = post(web, "words/quick", {"group_id": web[4], "entry": entry})
    assert response.status_code == 201, response.json
    assert response.json["word"]["word"] == word
    assert response.json["word"]["definition"] == definition
    assert response.json["duplicate"] is False
    assert calls[0]["word_text"] == word and calls[0]["needs_chinese"] is False


def test_continuous_add_saves_immediately_enriches_and_skips_duplicates(web, monkeypatch):
    calls = []
    monkeypatch.setattr("vocab.web.BackgroundEnricher.enrich", lambda **values: calls.append(values))
    response = post(web, "words/quick", {"group_id": web[4], "entry": "ephemeral"})
    assert response.status_code == 201, response.json
    saved = web[3].get_word_by_id(response.json["word"]["id"])
    assert saved.definition == "[Fetching Chinese meaning...]"
    assert calls[0]["word_id"] == saved.id and calls[0]["needs_chinese"] is True

    duplicate = post(web, "words/quick", {"group_id": web[4], "entry": "  EPHEMERAL: replacement  "})
    assert duplicate.status_code == 200
    assert duplicate.json["duplicate"] is True
    assert web[3].count_words(group_id=web[4], search="ephemeral") == 1
    assert len(calls) == 1


def test_continuous_add_quit_command_does_not_create_a_word(web, monkeypatch):
    monkeypatch.setattr("vocab.web.BackgroundEnricher.enrich", lambda **values: None)
    before = web[3].count_words(group_id=web[4])
    response = post(web, "words/quick", {"group_id": web[4], "entry": ":q"})
    assert response.status_code == 200 and response.json == {"quit": True}
    assert web[3].count_words(group_id=web[4]) == before


def test_flashcard_introduction_and_recall_match_shared_engine(web):
    db = web[3]
    state = start(web, mode="flashcard")
    assert state["phase"] == "introduction"
    wid = state["card"]["id"]
    introduced = act(web, state, "introduce").json
    assert introduced["reviews"] == 0
    assert db.get_word_by_id(wid).state == "learning"
    assert db.get_word_review_logs(wid)[0].review_mode == "introduction"
    state = act(web, introduced, "next").json
    assert "definition" not in state["card"]
    old = db.get_word_by_id(wid)
    state = act(web, state, "reveal").json
    assert state["card"]["word"] == old.word
    assert len(state["intervals"]) == 4
    response = act(web, state, "grade", grade=3)
    assert response.status_code == 200, response.json
    saved = db.get_word_by_id(wid)
    log = db.get_word_review_logs(wid)[-1]
    expected, _ = SRSEngine.calculate_next_state(old, SRSGrade.GOOD, log.thought_time_seconds,
                                                 now=datetime.fromisoformat(log.reviewed_at))
    for key in ("state", "step", "reps", "interval_days", "ease_factor", "due_date"):
        assert getattr(saved, key) == getattr(expected, key)
    assert act(web, state, "grade", grade=3).status_code == 409
    assert len(db.get_word_review_logs(wid)) == 2
    done = act(web, response.json, "next").json
    assert done["phase"] == "done"


def test_session_progress_counts_words_removed_from_active_queue(web):
    state = start(web, mode="flashcard")
    assert state["removed"] == 0
    introduced = act(web, state, "introduce").json
    # Introduction re-queues the card for retrieval, so no word has left the session.
    assert introduced["removed"] == 0
    after_next = act(web, introduced, "next").json
    revealed = act(web, after_next, "reveal").json
    graded = act(web, revealed, "grade", grade=3).json
    assert graded["removed"] == 1
    assert graded["remaining"] == graded["initial"] - graded["removed"]


@pytest.mark.parametrize("answer,grade", [("evidence", "Good"), ("evidenc", "Hard"), ("wrong", "Again")])
def test_typing_grades_and_requeues(web, answer, grade):
    state = start(web, mode="typing")
    # Force a known single word, keeping the deck's queue policy.
    wid = state["card"]["id"]
    answer = web[3].get_word_by_id(wid).word if grade == "Good" else (web[3].get_word_by_id(wid).word[:-1] if grade == "Hard" else answer)
    state = act(web, state, "introduce").json
    state = act(web, state, "next").json
    response = act(web, state, "answer", answer=answer)
    assert response.status_code == 200, response.json
    assert response.json["feedback"]["grade"] == grade
    assert response.json["remaining"] == (0 if grade == "Good" else 1)


def test_quiz_preserves_schedule_and_hides_answer(web):
    state = start(web, mode="quiz")
    db = web[3]
    old = db.get_word_by_id(state["card"]["id"])
    assert "word" not in state["card"] and "correct_index" not in state
    state = act(web, state, "answer", choice=state["choices"].index(old.word)).json
    assert state["feedback"]["grade"] == "Good"
    assert asdict(db.get_word_by_id(old.id)) == asdict(old)
    assert db.get_word_review_logs(old.id)[0].review_mode == "quiz"
    assert web[1].get("/api/dashboard").json["stats"]["total_recent_reviews"] == 0


def test_stale_card_and_cross_browser_session_rejected(web):
    state = start(web)
    db = web[3]
    word = db.get_word_by_id(state["card"]["id"])
    word.definition = "Edited from terminal"
    db.update_word(word)
    assert act(web, state, "introduce").status_code == 409
    assert db.get_word_review_logs(word.id) == []
    stranger = web[0].test_client()
    assert stranger.get(f"/api/sessions/{state['id']}").status_code == 404
    assert act(web, state, "skip").json["phase"] == "done"


def test_review_update_and_log_rollback_together(web, monkeypatch):
    state = start(web)
    db = web[3]
    old = asdict(db.get_word_by_id(state["card"]["id"]))
    def fail(*args, **kwargs):
        raise RuntimeError("Simulated write failure")
    monkeypatch.setattr(db, "log_review", fail)
    with pytest.raises(RuntimeError):
        act(web, state, "introduce")
    assert asdict(db.get_word_by_id(old["id"])) == old


@pytest.mark.parametrize("source", ["benchmark", "opentdb", "datamuse"])
def test_check_scores_and_persists_once(web, monkeypatch, source):
    questions = [TestQuestion("Select the answer", ["Yes", "No"], 0, "Explanation", cefr_level="A1")]
    for method in ("get_leveled_benchmark_questions", "fetch_opentdb_questions", "fetch_datamuse_questions"):
        monkeypatch.setattr(VocabTestService, method, lambda *a, **k: questions)
    state = start(web, mode="check", source=source)
    assert "correct_index" not in state["question"]
    feedback = act(web, state, "answer", choice=0).json
    assert feedback["feedback"]["correct"]
    assert act(web, state, "answer", choice=0).status_code == 409
    done = act(web, feedback, "next").json
    assert done["result"]["score_pct"] == 100
    assert done["result"]["cefr_level"] == "Uncalibrated"
    act(web, done, "end")
    assert len(web[3].get_test_history()) == 1


def test_csrf_host_and_validation(web):
    c = web[1]
    assert c.post("/api/groups", json={"name": "bad"}).status_code == 400
    assert c.get("/", headers={"Host": "untrusted.example"}).status_code == 400
    for data in ({"limit": -1}, {"limit": True}, {"mode": "unknown"}, {"shuffle": "no"}):
        assert post(web, "sessions", data).status_code == 400
    assert c.get("/api/words?group_id=99999").status_code == 404
    assert post(web, "words", {"word": "new", "definition": "x"}).status_code == 400
    response = c.patch("/api/words/1", headers=web[2], json={"definition": "should roll back", "retired": "yes"})
    assert response.status_code == 400
    assert web[3].get_word_by_id(1).definition != "should roll back"


def test_csv_import_unicode_export_and_duplicate_handling(web):
    c, headers, db = web[1:4]
    content = "definition,word,group\n定义,测试,中文\nA word,lexeme,Linguistics\n".encode()
    response = c.post("/api/import", headers=headers, data={"file": (io.BytesIO(content), "words.csv")})
    assert response.status_code == 200, response.json
    assert response.json == {"groups_added": 2, "words_added": 2}
    duplicate = c.post("/api/import", headers=headers, data={"file": (io.BytesIO(content), "words.csv")})
    assert duplicate.json["words_added"] == 0
    exported = c.get("/api/export?format=json").json
    assert any(g["group_name"] == "中文" for g in exported)
    assert "attachment" in c.get("/api/export?format=csv").headers["Content-Disposition"]


@pytest.mark.parametrize("data", [
    [{"group_name": "Valid", "words": [{"word": "x", "definition": "y"}]}, {"group_name": "Invalid", "words": [{}]}],
    {"wrong": "root"}, [{"group_name": "Deck", "words": ["not an object"]}],
])
def test_bad_import_never_partially_writes(web, data):
    c, headers, db = web[1:4]
    before = len(db.get_groups()), db.count_words()
    response = c.post("/api/import", headers=headers, data={"file": (io.BytesIO(json.dumps(data).encode()), "words.json")})
    assert response.status_code == 400
    assert before == (len(db.get_groups()), db.count_words())


def test_settings_and_explicit_maintenance(web):
    assert post(web, "maintenance", {"action": "threshold", "value": 45}).json["threshold"] == 45
    assert web[3].get_max_thought_time_threshold() == 45
    assert web[1].get("/api/bootstrap").json["keyboard_controls"] is True
    assert post(web, "maintenance", {"action": "keyboard", "enabled": False}).json["keyboard_controls"] is False
    assert web[1].get("/api/bootstrap").json["keyboard_controls"] is False
    assert post(web, "maintenance", {"action": "keyboard", "enabled": "false"}).status_code == 400
    for action in ("sync", "cleanup", "seed"):
        result = post(web, "maintenance", {"action": action})
        assert result.status_code == 200, result.json


def test_session_auto_add_can_be_changed_without_advancing_card(web):
    state = start(web, mode="flashcard", auto_add_due=True)
    card_id, token = state["card"]["id"], state["token"]
    response = act(web, state, "set_auto_add", enabled=False)
    assert response.status_code == 200
    updated = response.json
    assert updated["auto_add"] is False
    assert updated["card"]["id"] == card_id and updated["token"] == token
    assert act(web, updated, "set_auto_add", enabled="false").status_code == 400


def test_retired_words_excluded_from_forecast(web):
    db = web[3]
    assert sum(db.get_due_forecast().values()) == 4
    db.set_word_mastery(1, True)
    assert sum(db.get_due_forecast().values()) == 3


def test_terminal_csv_supports_definition_in_first_column(web, tmp_path):
    from vocab.exporter import DataExporter
    path = tmp_path / "column-order.csv"
    path.write_text("definition,word,group\nMeaning,lexeme,Reading\n", encoding="utf-8")
    assert DataExporter.import_from_csv(web[3], str(path)) == (1, 1)
    assert web[3].get_words(search="lexeme")[0].definition == "Meaning"


def test_export_does_not_truncate_large_libraries(web, tmp_path):
    from vocab.exporter import DataExporter
    db = web[3]
    now = datetime.now(timezone.utc).isoformat()
    with db.get_connection() as conn:
        conn.executemany("INSERT INTO words (group_id,word,definition,created_at,due_date) VALUES (?,?,?,?,?)",
                         [(web[4], f"word-{i}", "Meaning", now, now) for i in range(10001)])
        conn.commit()
    total = db.count_words()
    for fmt in ("csv", "json"):
        assert getattr(DataExporter, f"export_to_{fmt}")(db, str(tmp_path / f"export.{fmt}")) == total


def test_dictionary_uses_shared_lookup(web, monkeypatch):
    from vocab.dictionary import DictionaryService, DictionaryEntry
    monkeypatch.setattr(DictionaryService, "lookup", lambda word: DictionaryEntry(word, definition="Meaning"))
    monkeypatch.setattr(DictionaryService, "lookup_chinese", lambda word: "中文")
    monkeypatch.setattr(DictionaryService, "check_word_exists", lambda word: (True, None))
    result = post(web, "dictionary", {"word": "example"}).json
    assert result["entry"]["definition"] == "Meaning" and result["chinese"] == "中文"


def test_early_success_preserves_schedule(web):
    db = web[3]
    for word in db.get_words():
        word.state = "review"
        word.reps, word.interval_days = 5, 30
        word.last_reviewed = datetime.now(timezone.utc).isoformat()
        word.due_date = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        db.update_word(word)
    state = start(web, mode="flashcard", force_all=True)
    old = db.get_word_by_id(state["card"]["id"])
    state = act(web, state, "reveal").json
    response = act(web, state, "grade", grade=4)
    assert response.status_code == 200, response.json
    saved = db.get_word_by_id(old.id)
    assert (saved.due_date, saved.reps, saved.interval_days) == (old.due_date, old.reps, old.interval_days)


def test_sync_endpoint_and_revision_tracking(web):
    client = web[1]
    initial = client.get("/api/sync").json
    assert initial["revision"] >= 1
    assert initial["changed"] is True
    assert client.get(f"/api/sync?since={initial['revision']}").json["changed"] is False

    post(web, "groups", {"name": "SyncTest", "description": "Testing sync"})
    updated = client.get(f"/api/sync?since={initial['revision']}").json
    assert updated["changed"] is True
    assert updated["revision"] > initial["revision"]
