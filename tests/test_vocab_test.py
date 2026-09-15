"""
Unit tests for Vocabulary Test & Benchmark features.
Tests OpenTDB parsing, Datamuse integration, offline benchmark bank,
CEFR proficiency estimation, and database tracking.
"""
from __future__ import annotations
import json
import io
import urllib.request
import urllib.error
import pytest
import os
import tempfile
from unittest.mock import patch, MagicMock
from vocab.db import Database
from vocab.models import VocabTestResult, Word
from vocab.test_service import VocabTestService, TestQuestion, BENCHMARK_QUESTION_BANK


@pytest.fixture
def temp_db():
    """Provides a fresh temporary database."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    db = Database(db_path)
    yield db
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
        except Exception:
            pass


def test_opentdb_parsing_and_unescaping():
    """Tests that OpenTDB JSON responses are cleanly parsed and HTML entities unescaped."""
    mock_response_data = {
        "response_code": 0,
        "results": [
            {
                "category": "Entertainment: Books",
                "type": "multiple",
                "difficulty": "medium",
                "question": "Which word means &quot;brief and fleeting&quot;?",
                "correct_answer": "ephemeral",
                "incorrect_answers": ["permanent", "tedious", "ancient"]
            },
            {
                "category": "Entertainment: Books",
                "type": "multiple",
                "difficulty": "hard",
                "question": "Who wrote &#039;War and Peace&#039;?",
                "correct_answer": "Leo Tolstoy",
                "incorrect_answers": ["Fyodor Dostoevsky", "Anton Chekhov", "Vladimir Nabokov"]
            }
        ]
    }

    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(mock_response_data).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        questions = VocabTestService.fetch_opentdb_questions(amount=2)

    assert len(questions) >= 2
    q1 = questions[0]
    assert 'Which word means "brief and fleeting"?' in q1.prompt
    assert "ephemeral" in q1.choices
    assert q1.choices[q1.correct_index] == "ephemeral"
    assert q1.cefr_level == "B2"

    q2 = questions[1]
    assert "Who wrote 'War and Peace'?" in q2.prompt
    assert "Leo Tolstoy" in q2.choices
    assert q2.choices[q2.correct_index] == "Leo Tolstoy"
    assert q2.cefr_level == "C1"


def test_opentdb_network_failure_fallback():
    """Tests that OpenTDB network timeout/error seamlessly falls back to offline benchmark questions."""
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Network unreachable")):
        questions = VocabTestService.fetch_opentdb_questions(amount=5)

    assert len(questions) == 5
    for q in questions:
        assert isinstance(q, TestQuestion)
        assert len(q.choices) == 4
        assert 0 <= q.correct_index < 4
        assert q.correct_answer != ""


def test_datamuse_parsing_and_fallback():
    """Tests Datamuse synonym questions generation with offline fallback."""
    # Test network failure fallback
    with patch("urllib.request.urlopen", side_effect=TimeoutError("Connection timed out")):
        questions = VocabTestService.fetch_datamuse_questions(amount=4)

    assert len(questions) == 4
    for q in questions:
        assert isinstance(q, TestQuestion)
        assert len(q.choices) == 4
        assert 0 <= q.correct_index < 4


def test_datamuse_mocked_success():
    """Tests Datamuse when API returns synonym data successfully."""
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps([{"word": "practical", "score": 1200}]).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        questions = VocabTestService.fetch_datamuse_questions(amount=2)

    assert len(questions) >= 2
    q = questions[0]
    assert "synonym" in q.prompt.lower()
    assert 0 <= q.correct_index < len(q.choices)


def test_leveled_benchmark_bank_integrity():
    """Validates that all questions in the benchmark question bank are well-formed."""
    assert len(BENCHMARK_QUESTION_BANK) >= 30

    levels_present = set()
    for item in BENCHMARK_QUESTION_BANK:
        assert "prompt" in item and len(item["prompt"]) > 5
        assert "choices" in item and len(item["choices"]) == 4
        assert "correct_index" in item and 0 <= item["correct_index"] < 4
        assert "cefr_level" in item
        assert item["cefr_level"] in ("A1", "A2", "B1", "B2", "C1", "C2")
        levels_present.add(item["cefr_level"])

    # Ensure all CEFR levels A1 through C2 are represented
    assert levels_present == {"A1", "A2", "B1", "B2", "C1", "C2"}


def test_get_leveled_benchmark_questions_staircase():
    """Tests progressive staircase question retrieval spanning A1 to C2."""
    questions = VocabTestService.get_leveled_benchmark_questions(amount=12)
    assert len(questions) == 12

    tiers = [q.cefr_level for q in questions]
    assert "A1" in tiers
    assert "B1" in tiers
    assert "C1" in tiers
    assert "C2" in tiers


def test_get_leveled_benchmark_questions_filtered_by_level():
    """Tests level-filtered retrieval."""
    questions = VocabTestService.get_leveled_benchmark_questions(amount=4, level="C2")
    assert len(questions) == 4
    for q in questions:
        assert q.cefr_level == "C2"


def test_estimate_proficiency_perfect_score():
    """Tests proficiency calculation with a 100% correct score on high-tier questions."""
    questions = [
        TestQuestion(prompt="Q1", choices=["A", "B", "C", "D"], correct_index=0, cefr_level="B2"),
        TestQuestion(prompt="Q2", choices=["A", "B", "C", "D"], correct_index=1, cefr_level="C1"),
        TestQuestion(prompt="Q3", choices=["A", "B", "C", "D"], correct_index=2, cefr_level="C1"),
        TestQuestion(prompt="Q4", choices=["A", "B", "C", "D"], correct_index=3, cefr_level="C2"),
        TestQuestion(prompt="Q5", choices=["A", "B", "C", "D"], correct_index=0, cefr_level="C2"),
    ]
    user_correct = [True, True, True, True, True]

    eval_result = VocabTestService.estimate_proficiency(questions, user_correct, avg_response_time=2.8)

    assert eval_result["score_pct"] == 100.0
    assert eval_result["correct_count"] == 5
    assert eval_result["cefr_level"] == "C2"
    assert eval_result["estimated_vocab_size"] >= 20000
    assert eval_result["speed_rating"] == "Automatic / Fluent"
    assert eval_result["is_reliable"] is True


def test_ceiling_rule_single_a1_question():
    """Validates that a 1-question A1 quiz NEVER awards C2 or thousands of extra words."""
    questions = [
        TestQuestion(prompt="What means ancient?", choices=["old", "new", "hot", "cold"], correct_index=0, cefr_level="A1")
    ]
    user_correct = [True]

    eval_result = VocabTestService.estimate_proficiency(questions, user_correct, avg_response_time=2.5)

    assert eval_result["score_pct"] == 100.0
    assert eval_result["correct_count"] == 1
    # MUST be bounded to A1 by the ceiling rule!
    assert eval_result["cefr_level"] == "A1"
    assert eval_result["estimated_vocab_size"] <= 2500
    assert eval_result["is_reliable"] is False
    assert eval_result["sample_warning"] is not None


def test_staircase_multi_tier_benchmark_scoring():
    """Tests realistic scoring on an A1 to C2 12-question staircase battery (8/12 correct)."""
    questions = [
        TestQuestion(prompt="A1_1", choices=["a","b","c","d"], correct_index=0, cefr_level="A1"),
        TestQuestion(prompt="A1_2", choices=["a","b","c","d"], correct_index=0, cefr_level="A1"),
        TestQuestion(prompt="A2_1", choices=["a","b","c","d"], correct_index=0, cefr_level="A2"),
        TestQuestion(prompt="A2_2", choices=["a","b","c","d"], correct_index=0, cefr_level="A2"),
        TestQuestion(prompt="B1_1", choices=["a","b","c","d"], correct_index=0, cefr_level="B1"),
        TestQuestion(prompt="B1_2", choices=["a","b","c","d"], correct_index=0, cefr_level="B1"),
        TestQuestion(prompt="B2_1", choices=["a","b","c","d"], correct_index=0, cefr_level="B2"),
        TestQuestion(prompt="B2_2", choices=["a","b","c","d"], correct_index=0, cefr_level="B2"),
        TestQuestion(prompt="C1_1", choices=["a","b","c","d"], correct_index=0, cefr_level="C1"),
        TestQuestion(prompt="C1_2", choices=["a","b","c","d"], correct_index=0, cefr_level="C1"),
        TestQuestion(prompt="C2_1", choices=["a","b","c","d"], correct_index=0, cefr_level="C2"),
        TestQuestion(prompt="C2_2", choices=["a","b","c","d"], correct_index=0, cefr_level="C2"),
    ]
    # User masters A1, A2, B1, misses B2, gets 1 C1 and 1 C2
    user_correct = [True, True, True, True, True, True, False, False, True, False, True, False]

    eval_result = VocabTestService.estimate_proficiency(questions, user_correct, avg_response_time=6.0)

    assert eval_result["correct_count"] == 8
    assert eval_result["total_questions"] == 12
    assert eval_result["score_pct"] == 66.7
    # Should accurately place user in B2 (Upper Intermediate) with ~12k-15k words
    assert eval_result["cefr_level"] == "B2"
    assert 11000 <= eval_result["estimated_vocab_size"] <= 15000
    assert eval_result["is_reliable"] is True


def test_estimate_proficiency_beginner_score():
    """Tests proficiency calculation when user only gets basic beginner questions correct."""
    questions = [
        TestQuestion(prompt="Q1", choices=["A", "B", "C", "D"], correct_index=0, cefr_level="A1"),
        TestQuestion(prompt="Q2", choices=["A", "B", "C", "D"], correct_index=1, cefr_level="A1"),
        TestQuestion(prompt="Q3", choices=["A", "B", "C", "D"], correct_index=2, cefr_level="A2"),
        TestQuestion(prompt="Q4", choices=["A", "B", "C", "D"], correct_index=3, cefr_level="B1"),
        TestQuestion(prompt="Q5", choices=["A", "B", "C", "D"], correct_index=0, cefr_level="B2"),
    ]
    user_correct = [True, True, False, False, False]

    eval_result = VocabTestService.estimate_proficiency(questions, user_correct, avg_response_time=8.5)

    assert eval_result["correct_count"] == 2
    assert eval_result["cefr_level"] == "A1"
    assert eval_result["estimated_vocab_size"] <= 3500
    assert eval_result["speed_rating"] == "Deliberate"


def test_db_log_and_get_test_history(temp_db):
    """Tests logging test results to the database and querying test history."""
    # Ensure database is empty initially
    history = temp_db.get_test_history()
    assert len(history) == 0

    analytics = temp_db.get_test_analytics()
    assert analytics["total_tests"] == 0
    assert analytics["latest_test"] is None

    # Log a 1-question preliminary attempt (100%)
    t1_id = temp_db.log_test_result(
        test_type="opentdb",
        total_questions=1,
        correct_count=1,
        score_pct=100.0,
        cefr_level="A1",
        estimated_vocab_size=2000,
        avg_response_time=2.9,
        tested_at="2026-09-14T10:00:00Z"
    )

    # Log a full 12-question benchmark (66.7%)
    t2_id = temp_db.log_test_result(
        test_type="cefr_benchmark",
        total_questions=12,
        correct_count=8,
        score_pct=66.7,
        cefr_level="B2",
        estimated_vocab_size=13750,
        avg_response_time=6.1,
        tested_at="2026-09-14T11:00:00Z"
    )

    # Query history
    history = temp_db.get_test_history(limit=10)
    assert len(history) == 2
    # Newest first
    assert history[0].id == t2_id
    assert history[0].test_type == "cefr_benchmark"
    assert history[0].cefr_level == "B2"
    assert history[0].estimated_vocab_size == 13750

    assert history[1].id == t1_id
    assert history[1].test_type == "opentdb"

    # Query analytics: best_score should come from the certified benchmark (66.7%), NOT 100% on 1 question!
    analytics = temp_db.get_test_analytics()
    assert analytics["total_tests"] == 2
    assert analytics["best_score"] == 66.7
    assert analytics["latest_benchmark"].cefr_level == "B2"
    assert len(analytics["progression"]) == 2


def test_db_delete_test_history(temp_db):
    """Tests clearing specific or all test logs."""
    t1 = temp_db.log_test_result("cefr_benchmark", 10, 8, 80.0, "B2", 9000)
    t2 = temp_db.log_test_result("cefr_benchmark", 10, 9, 90.0, "C1", 16000)

    assert len(temp_db.get_test_history()) == 2

    # Delete single test
    deleted = temp_db.delete_test_history(test_id=t1)
    assert deleted == 1
    rem = temp_db.get_test_history()
    assert len(rem) == 1
    assert rem[0].id == t2

    # Clear all
    temp_db.delete_test_history()
    assert len(temp_db.get_test_history()) == 0

