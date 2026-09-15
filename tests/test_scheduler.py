"""Reference values and behavioral regressions for the documented scheduler."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import math

import pytest
from vocab.models import Word, SRSGrade
from vocab.srs import SRSEngine, RecurrentSessionQueue, UniversalSRSFormula
from vocab.measurement import wilson_interval
from vocab.db import Database

NOW = datetime(2026, 9, 15, 8, tzinfo=timezone.utc)


def card(**kwargs):
    return replace(Word(1, 1, "evidence", "information supporting a claim"), **kwargs)


def test_reference_sm2_good_sequence():
    word, days = SRSEngine.calculate_next_state(card(), SRSGrade.EASY, now=NOW)
    assert (days, word.reps, word.ease_factor) == (1, 1, 2.6)
    # Use neutral ease to test published 1, 6, 15, 38 sequence.
    word.ease_factor = 2.5
    for expected in (6, 15, 38):
        word, days = SRSEngine.calculate_next_state(word, SRSGrade.GOOD,
                                                    now=datetime.fromisoformat(word.due_date))
        assert days == expected
        assert word.ease_factor == 2.5


@pytest.mark.parametrize("grade,ease", [(SRSGrade.HARD, 2.36), (SRSGrade.GOOD, 2.5), (SRSGrade.EASY, 2.6)])
def test_previous_ease_sets_interval_then_quality_updates_ease(grade, ease):
    word = card(state="review", reps=3, interval_days=10, due_date=NOW.isoformat())
    updated, days = SRSEngine.calculate_next_state(word, grade, now=NOW)
    assert days == 25
    assert updated.ease_factor == ease
    assert updated.lapses == 0


def test_learning_and_lapse_steps():
    word, days = SRSEngine.calculate_next_state(card(), SRSGrade.GOOD, now=NOW)
    assert (word.state, word.step, days) == ("learning", 1, 10 / 1440)
    word, days = SRSEngine.calculate_next_state(word, SRSGrade.GOOD, now=NOW + timedelta(minutes=10))
    assert (word.state, word.reps, days) == ("review", 1, 1)
    word, days = SRSEngine.calculate_next_state(word, SRSGrade.AGAIN, now=NOW + timedelta(days=1))
    assert (word.state, word.reps, word.lapses, days) == ("relearning", 0, 1, 1 / 1440)
    word, _ = SRSEngine.calculate_next_state(word, SRSGrade.AGAIN, now=NOW + timedelta(days=1, minutes=1))
    assert word.state == "relearning" and word.lapses == 1
    assert word.ease_factor >= 1.3


@pytest.mark.parametrize("grade", list(SRSGrade))
@pytest.mark.parametrize("latency", [0, 1, 8, 20, 90, float("nan"), float("inf")])
def test_latency_does_not_change_schedule(grade, latency):
    word = card(state="review", reps=3, interval_days=10, due_date=NOW.isoformat())
    baseline, _ = SRSEngine.calculate_next_state(word, grade, now=NOW)
    actual, _ = SRSEngine.calculate_next_state(word, grade, latency, now=NOW)
    for key in ("ease_factor", "due_date", "interval_days", "reps", "lapses", "state"):
        assert getattr(actual, key) == getattr(baseline, key)


@pytest.mark.parametrize("grade", [SRSGrade.HARD, SRSGrade.GOOD, SRSGrade.EASY])
def test_repeated_early_practice_preserves_long_term_schedule(grade):
    word = card(state="review", reps=5, interval_days=30, last_reviewed=NOW.isoformat(),
                due_date=(NOW + timedelta(days=30)).isoformat())
    original = replace(word)
    for _ in range(50):
        word, days = SRSEngine.calculate_next_state(word, grade, now=NOW + timedelta(days=1))
    assert days == 29
    assert word == original


def test_preview_is_pure_and_matches_saved_intervals():
    word = card(state="review", reps=2, interval_days=6, due_date=NOW.isoformat())
    original = replace(word)
    previews = SRSEngine.preview_intervals(word, now=NOW)
    assert word == original
    for grade in SRSGrade:
        updated, days = SRSEngine.calculate_next_state(word, grade, now=NOW)
        assert previews[grade] == SRSEngine.format_interval(days)
        assert datetime.fromisoformat(updated.due_date) == NOW + timedelta(days=days)


def test_history_replay_is_idempotent_and_matches_live_reviews():
    original = card()
    word = original
    logs = []
    for grade in (SRSGrade.GOOD, SRSGrade.GOOD, SRSGrade.HARD, SRSGrade.GOOD, SRSGrade.AGAIN, SRSGrade.EASY):
        when = NOW if not logs else datetime.fromisoformat(word.due_date)
        logs.append({"grade": int(grade), "reviewed_at": when.isoformat(), "thought_time_seconds": 4})
        word, _ = SRSEngine.calculate_next_state(word, grade, 4, now=when)
    replayed, _ = SRSEngine.calculate_from_review_logs(word, list(reversed(logs)), now=NOW)
    twice, _ = SRSEngine.calculate_from_review_logs(replayed, logs, now=NOW)
    assert replayed == word == twice


def test_invalid_grade_and_timestamp_are_not_silently_successful():
    with pytest.raises(ValueError):
        SRSEngine.calculate_next_state(card(), 6, now=NOW)
    with pytest.raises(ValueError):
        UniversalSRSFormula.calculate_from_entries([{"grade": 3, "reviewed_at": "bad date"}])


def test_timezone_equivalent_reviews_match():
    shifted = NOW.astimezone(timezone(timedelta(hours=8)))
    a, _ = SRSEngine.calculate_next_state(card(), SRSGrade.GOOD, now=NOW)
    b, _ = SRSEngine.calculate_next_state(card(), SRSGrade.GOOD, now=shifted)
    assert a == b


def test_quick_success_does_not_retire_and_slow_success_does_not_requeue():
    word = card(state="review", interval_days=200, reps=10, stability=200, due_date=NOW.isoformat())
    word, _ = SRSEngine.calculate_next_state(word, SRSGrade.EASY, 1, now=NOW)
    assert word.state == "review"
    assert not SRSEngine.is_mastery_eligible(word, [(4, 1, NOW)] * 3)
    queue = RecurrentSessionQueue([word])
    assert not queue.handle_result(word, SRSGrade.GOOD, 20)


def test_wilson_reference_and_boundaries():
    assert wilson_interval(0, 0) is None
    assert wilson_interval(5, 10) == pytest.approx((0.2365931, 0.7634069))
    assert wilson_interval(0, 10) == pytest.approx((0, 0.2775328))
    assert wilson_interval(10, 10) == pytest.approx((0.7224672, 1))
    with pytest.raises(ValueError):
        wilson_interval(11, 10)


def test_logs_preserve_raw_time_and_recall_counts_hard(tmp_path):
    db = Database(str(tmp_path / "logs.db"))
    group = db.create_group("Test")
    wid = db.add_word(group, "evidence", "support")
    for grade, mode in [(2, "flashcard"), (1, "typing"), (3, "quiz"), (3, "introduction")]:
        db.log_review(wid, grade, mode, 1, thought_time_seconds=90)
    assert all(log.thought_time_seconds == 90 for log in db.get_word_review_logs(wid))
    summary = db.get_stats_summary(group)
    assert summary["total_recent_reviews"] == 2
    assert summary["retention_rate"] == 50
    assert db.get_latency_analytics(group)["total_timed_reviews"] == 0


def test_opening_existing_app_preserves_schedule_and_raw_logs(tmp_path):
    from vocab.app import VocabApp
    path = str(tmp_path / "existing.db")
    db = Database(path)
    group = db.create_group("Existing")
    wid = db.add_word(group, "legacy", "existing")
    word = db.get_word_by_id(wid)
    word.state, word.interval_days, word.reps = "review", 123, 9
    word.due_date = "2027-01-01T00:00:00+00:00"
    db.update_word(word)
    db.log_review(wid, 4, "flashcard", 1, thought_time_seconds=90)
    app = VocabApp(path)
    assert app.db.get_word_by_id(wid) == word
    assert app.db.get_word_review_logs(wid)[0].thought_time_seconds == 90


def test_recognition_session_logs_practice_without_changing_word(tmp_path, monkeypatch):
    from vocab.sessions import quiz_session
    db = Database(str(tmp_path / "quiz.db"))
    group = db.create_group("Recognition")
    for word in ("one", "two", "three", "four"):
        db.add_word(group, word, "sample definition")
    before = db.get_words(group_id=group)
    answer = []
    def show_question(word, choices, **kwargs):
        answer.append(str(choices.index(word.word) + 1))
    monkeypatch.setattr(quiz_session, "render_quiz_question", show_question)
    monkeypatch.setattr(quiz_session, "render_header", lambda *args: None)
    monkeypatch.setattr(quiz_session, "pause_prompt", lambda *args: None)
    monkeypatch.setattr(quiz_session.time, "sleep", lambda *args: None)
    monkeypatch.setattr("builtins.input", lambda *args: answer.pop())
    quiz_session.run_quiz_session(db, group_id=group, limit=1, shuffle=False)
    assert db.get_words(group_id=group) == before
    logs = [log for word in before for log in db.get_word_review_logs(word.id)]
    assert len(logs) == 1 and logs[0].review_mode == "quiz"


def test_quiz_only_history_does_not_reset_existing_schedule():
    word = card(state="review", reps=8, interval_days=120)
    updated, _ = SRSEngine.calculate_from_review_logs(word, [
        {"grade": 4, "reviewed_at": NOW.isoformat(), "review_mode": "quiz"}
    ])
    assert updated == word


def test_assessment_empty_inputs_mismatch_and_speed_neutrality():
    from vocab.test_service import VocabTestService, TestQuestion
    assert VocabTestService.estimate_proficiency([], [])["accuracy_interval"] is None
    questions = [TestQuestion(prompt="Meaning?", choices=["a", "b"], correct_index=0)]
    with pytest.raises(ValueError):
        VocabTestService.estimate_proficiency(questions, [])
    quick = VocabTestService.estimate_proficiency(questions, [True], 1)
    slow = VocabTestService.estimate_proficiency(questions, [True], 20)
    assert quick == slow
    assert quick["estimated_vocab_size"] == 0
    assert quick["is_reliable"] is False
