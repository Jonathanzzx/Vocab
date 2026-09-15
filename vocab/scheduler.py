"""SM-2 scheduling with explicit application policies. See docs/RESEARCH.md.

The interval/ease equations follow Woźniak (1990). Short learning steps,
early-practice protection and the interval cap are application choices.
No fitted memory probabilities or latency-based adjustments are used.
"""
from __future__ import annotations

import math
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from vocab.models import CardState, SRSGrade, Word

LEARNING_STEPS_MINUTES = [1, 10]
MIN_DIFFICULTY, MAX_DIFFICULTY, DEFAULT_DIFFICULTY = 1.0, 10.0, 5.0
MIN_EASE_FACTOR, MAX_EASE_FACTOR = 1.3, float("inf")
MAX_INTERVAL_DAYS = 36500
MAX_VALID_THOUGHT_TIME = 30.0
TARGET_RETENTION = 0.90  # Legacy illustration only; SM-2 does not target retention.
QUALITY = {SRSGrade.AGAIN: 0, SRSGrade.HARD: 3, SRSGrade.GOOD: 4, SRSGrade.EASY: 5}


def is_valid_thought_time(value, max_threshold=MAX_VALID_THOUGHT_TIME):
    try:
        return math.isfinite(float(value)) and 0 < float(value) <= max_threshold
    except (TypeError, ValueError):
        return False


def _utc(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if value.tzinfo is None:
        # Legacy logs were written in local wall time.
        value = value.astimezone()
    return value.astimezone(timezone.utc)


class SRSEngine:
    """Deterministic SM-2 review intervals, shared by previews and history replay."""

    @classmethod
    def calculate_next_state(cls, word, grade, thought_time_seconds=0.0,
                             now=None, apply_fuzz=False):
        now = _utc(now or datetime.now(timezone.utc))
        grade = SRSGrade(grade)  # Reject invalid ratings instead of assuming success.
        updated = replace(word)
        if word.state == CardState.MASTERED.value:
            return updated, word.interval_days

        if is_valid_thought_time(thought_time_seconds):
            updated.last_thought_time = round(float(thought_time_seconds), 2)
            updated.avg_thought_time = round(
                0.7 * word.avg_thought_time + 0.3 * thought_time_seconds
                if word.avg_thought_time > 0 else thought_time_seconds, 2)

        # Practising a future review must not multiply its long-term interval.
        if word.state == CardState.REVIEW.value and grade != SRSGrade.AGAIN:
            if word.last_reviewed and word.due_date and _utc(word.due_date) > now:
                return updated, (_utc(word.due_date) - now).total_seconds() / 86400

        ease = word.ease_factor if math.isfinite(word.ease_factor) else 2.5
        ease = max(MIN_EASE_FACTOR, ease)
        quality = QUALITY[grade]
        updated.ease_factor = round(max(MIN_EASE_FACTOR,
            ease + 0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)), 2)
        updated.last_reviewed = now.isoformat()

        learning = word.state in ("new", "learning", "relearning")
        if grade == SRSGrade.AGAIN:
            updated.state = "relearning" if word.state in ("review", "relearning") else "learning"
            updated.step, updated.reps = 0, 0
            updated.lapses += int(word.state == "review")
            days = 1 / 1440
        elif learning and grade == SRSGrade.HARD:
            updated.state = "relearning" if word.state == "relearning" else "learning"
            days = 10 / 1440
        elif learning and grade == SRSGrade.GOOD and word.step == 0:
            updated.state = "relearning" if word.state == "relearning" else "learning"
            updated.step = 1
            days = 10 / 1440
        else:
            updated.state, updated.step = "review", 0
            if learning or word.reps == 0:
                days, updated.reps = 1.0, 1
            elif word.reps == 1:
                days, updated.reps = 6.0, 2
            else:
                # SM-2 uses the prior ease for this interval, then updates ease.
                days = float(min(MAX_INTERVAL_DAYS, math.ceil(max(1, word.interval_days) * ease)))
                updated.reps = word.reps + 1

        updated.interval_days = days
        updated.due_date = (now + timedelta(days=days)).isoformat()
        # Preserve schema compatibility; these are proxies, not fitted DSR state.
        updated.stability = days
        updated.difficulty = round(max(1.0, min(10.0, (3.5 - updated.ease_factor) / 0.22)), 2)
        return updated, days

    @classmethod
    def calculate_from_review_logs(cls, word, logs, now=None):
        if not logs:
            return replace(word), word.interval_days
        current = replace(word, state="new", step=0, reps=0, lapses=0,
                          interval_days=0.0, ease_factor=2.5, stability=1.0,
                          difficulty=5.0, last_reviewed=None,
                          avg_thought_time=0.0, last_thought_time=0.0)
        parsed = []
        for entry in logs:
            if isinstance(entry, (tuple, list)):
                grade, latency, timestamp = entry
                mode = "flashcard"
            else:
                data = entry if isinstance(entry, dict) else vars(entry)
                grade, timestamp = data["grade"], data["reviewed_at"]
                latency = data.get("thought_time_seconds", data.get("thought_time", 0)) or 0
                mode = data.get("review_mode", "flashcard")
            parsed.append((_utc(timestamp), grade, latency, mode))
        if all(mode == "quiz" for _, _, _, mode in parsed):
            return replace(word), word.interval_days
        for timestamp, grade, latency, mode in sorted(parsed, key=lambda e: e[0]):
            if mode == "quiz":
                continue  # Recognition practice does not certify free recall.
            current, _ = cls.calculate_next_state(current, grade, latency, now=timestamp)
            if mode == "introduction":
                current.state, current.step, current.reps = "learning", 0, 0
        if word.state == "mastered":
            current.state = "mastered"  # Respect manually retired and legacy cards.
        return current, current.interval_days

    @staticmethod
    def is_mastery_eligible(word, recent_logs=None):
        """Retirement is a user decision, never inferred from quick answers."""
        return word.state == "mastered"

    @classmethod
    def preview_intervals(cls, word, now=None):
        now = now or datetime.now(timezone.utc)
        return {g: cls.format_interval(cls.calculate_next_state(word, g, now=now)[1]) for g in SRSGrade}

    @staticmethod
    def format_interval(days):
        minutes = days * 1440
        if minutes < 1.5:
            return "1m" if minutes >= 1 else "<1m"
        if minutes < 60:
            return f"{minutes:.0f}m"
        if days < 1:
            return f"{minutes / 60:.1f}h"
        if days < 30:
            return f"{days:g}d"
        if days < 365:
            return f"{days / 30:.1f}mo"
        return f"{days / 365:.1f}y"

    @staticmethod
    def apply_interval_fuzz(days):
        return days  # Retained API; previews and committed schedules are identical.

    @staticmethod
    def calculate_retrievability(t_days, stability):
        """Legacy illustrative curve, not a calibrated prediction or scheduler input."""
        return round(0.9 ** (max(0, t_days) / max(0.1, stability)), 4)

    calculate_brain_capacity = staticmethod(lambda word: word.brain_capacity)
    difficulty_to_capacity = staticmethod(Word.difficulty_to_capacity)

    @staticmethod
    def rate_session_quality(*args, **kwargs):
        from vocab.srs import rate_session_quality
        return rate_session_quality(*args, **kwargs)

    @staticmethod
    def tune_capacity_threshold(*args, **kwargs):
        from vocab.srs import tune_capacity_threshold
        return tune_capacity_threshold(*args, **kwargs)


class UniversalSRSFormula:
    """Compatibility name for callers of the former custom formula."""

    calculate_retrievability = staticmethod(SRSEngine.calculate_retrievability)
    latency_multiplier = staticmethod(lambda *args, **kwargs: 1.0)

    @staticmethod
    def calculate_from_entries(entries, initial_difficulty=5.0, initial_stability=1.0,
                               current_time=None, apply_fuzz=False):
        word = Word(None, 0, "", "", due_date=(current_time or datetime.now(timezone.utc)).isoformat())
        word, _ = SRSEngine.calculate_from_review_logs(word, entries, now=current_time)
        result = vars(word).copy()
        result["retrievability"] = word.retrievability(current_time)
        return result
