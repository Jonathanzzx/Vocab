"""
Data models for Vocab memorization app.
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum, Enum
from typing import Optional, List, Dict, Any


class SRSGrade(IntEnum):
    AGAIN = 1  # Complete blackout / wrong answer
    HARD = 2   # Recalled with serious difficulty
    GOOD = 3   # Correct recall with normal effort
    EASY = 4   # Effortless, immediate recall


class CardState(str, Enum):
    NEW = "new"
    LEARNING = "learning"
    REVIEW = "review"
    RELEARNING = "relearning"
    MASTERED = "mastered"


@dataclass
class Group:
    id: Optional[int]
    name: str
    description: str = ""
    color: str = "cyan"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    word_count: int = 0
    due_count: int = 0

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> Group:
        return cls(
            id=row["id"],
            name=row["name"],
            description=row.get("description", "") or "",
            color=row.get("color", "cyan") or "cyan",
            created_at=row.get("created_at", "") or datetime.now(timezone.utc).isoformat(),
            word_count=row.get("word_count", 0),
            due_count=row.get("due_count", 0),
        )


@dataclass
class Word:
    id: Optional[int]
    group_id: int
    word: str
    definition: str
    phonetic: str = ""
    pos: str = ""  # Part of speech: noun, verb, adj, etc.
    example: str = ""
    mnemonic: str = ""  # Memory aid or root
    tags: str = ""  # Comma-separated tags
    state: str = CardState.NEW.value
    step: int = 0  # Intra-day learning step index
    interval_days: float = 0.0  # Spaced repetition interval in days
    ease_factor: float = 2.5    # Difficulty multiplier (min 1.3, default 2.5)
    reps: int = 0               # Consecutive successful reviews
    lapses: int = 0             # Times card was forgotten after graduating
    due_date: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_reviewed: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    avg_thought_time: float = 0.0  # Average latency in seconds
    last_thought_time: float = 0.0  # Most recent latency in seconds
    difficulty: float = 5.0  # DSR Difficulty rating (1.0 to 10.0, default 5.0)
    stability: float = 1.0   # DSR Memory stability in days
    group_name: Optional[str] = None  # Populated from joins
    is_placeholder: bool = False      # Temporary session filler when due words are scarce

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> Word:
        return cls(
            id=row["id"],
            group_id=row["group_id"],
            word=row["word"],
            definition=row["definition"],
            phonetic=row.get("phonetic", "") or "",
            pos=row.get("pos", "") or "",
            example=row.get("example", "") or "",
            mnemonic=row.get("mnemonic", "") or "",
            tags=row.get("tags", "") or "",
            state=row.get("state", CardState.NEW.value),
            step=row.get("step", 0) or 0,
            interval_days=float(row.get("interval_days", 0.0) or 0.0),
            ease_factor=float(row.get("ease_factor", 2.5) or 2.5),
            reps=int(row.get("reps", 0) or 0),
            lapses=int(row.get("lapses", 0) or 0),
            due_date=row.get("due_date", datetime.now(timezone.utc).isoformat()),
            last_reviewed=row.get("last_reviewed"),
            created_at=row.get("created_at", datetime.now(timezone.utc).isoformat()),
            avg_thought_time=float(row.get("avg_thought_time", 0.0) or 0.0),
            last_thought_time=float(row.get("last_thought_time", 0.0) or 0.0),
            difficulty=float(row.get("difficulty", 5.0) or 5.0),
            stability=float(row.get("stability", 1.0) or 1.0),
            group_name=row.get("group_name"),
            is_placeholder=bool(row.get("is_placeholder", False)),
        )

    @staticmethod
    def difficulty_to_capacity(
        difficulty: float,
        slope: float = 1.0,
        intercept: float = 0.0
    ) -> int:
        """
        Calculates the cognitive brain capacity cost for a word from its difficulty
        using a simple linear projection: C(d) = round(slope * d + intercept).
        Using a simple linear projection eliminates excess degrees of freedom
        and establishes a direct, monotonic relationship between difficulty and cognitive load.
        Clamped between 1 and 20.
        """
        raw = slope * float(difficulty) + intercept
        cost = int(math.floor(raw + 0.5))
        return max(1, min(20, cost))

    @property
    def brain_capacity(self) -> int:
        """
        Calculates the cognitive 'brain capacity' cost (points per session) for this word.
        Uses a simple linear projection from word difficulty:
            capacity = round(slope * difficulty + intercept)
        New words take 20 capacity (high cognitive load for initial novel acquisition).
        """
        if self.state == CardState.MASTERED.value:
            return 0
        if self.state == CardState.NEW.value:
            return 20
        return self.difficulty_to_capacity(self.difficulty)

    def retrievability(self, now: Optional[datetime] = None) -> float:
        """
        Calculates memory retrievability R(t, S) = 0.9^(t / S)
        based on elapsed time t and stability S (in days).
        Returns probability of successful recall (0.0 to 1.0).
        """
        if self.state == CardState.NEW.value:
            return 0.0
        if self.stability <= 0:
            return 0.5
        now = now or datetime.now(timezone.utc)
        if not self.last_reviewed:
            return 0.90
        try:
            last_dt = datetime.fromisoformat(self.last_reviewed)
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
            t_days = max(0.0, (now - last_dt).total_seconds() / 86400.0)
            return round(0.9 ** (t_days / max(0.1, self.stability)), 4)
        except Exception:
            return 0.90

    def is_due(self, now: Optional[datetime] = None) -> bool:
        """Returns True if the card is ready for review."""
        if self.state == CardState.MASTERED.value:
            return False
        if self.state == CardState.NEW.value:
            return True
        if not self.due_date:
            return True
        now = now or datetime.now(timezone.utc)
        try:
            due_dt = datetime.fromisoformat(self.due_date)
            if due_dt.tzinfo is None:
                due_dt = due_dt.replace(tzinfo=timezone.utc)
            return now >= due_dt
        except Exception:
            return True

    def urgency_score(self, now: Optional[datetime] = None) -> float:
        """
        Calculates an urgency score for prioritization.
        Higher score = more urgently needed review.
        """
        if self.state == CardState.MASTERED.value:
            return -1000.0
        now = now or datetime.now(timezone.utc)
        # New cards have high priority to be introduced
        if self.state == CardState.NEW.value:
            return 100.0 + (10.0 / (self.id or 1))

        # Cards in learning/relearning need immediate intra-day attention
        if self.state in (CardState.LEARNING.value, CardState.RELEARNING.value):
            return 500.0

        try:
            due_dt = datetime.fromisoformat(self.due_date)
            if due_dt.tzinfo is None:
                due_dt = due_dt.replace(tzinfo=timezone.utc)
            delta_seconds = (now - due_dt).total_seconds()
            interval_seconds = max(self.interval_days * 86400.0, 3600.0)
            overdue_ratio = delta_seconds / interval_seconds
            # Priority combines overdue ratio and lapse penalty (leech words get higher urgency)
            return overdue_ratio * 10.0 + (self.lapses * 2.0)
        except Exception:
            return 0.0

    def format_due_time(self, now: Optional[datetime] = None) -> str:
        """Returns a human-readable representation of when the card is due."""
        if self.state == CardState.MASTERED.value:
            return "Mastered"
        if self.state == CardState.NEW.value:
            return "New (Ready)"
        now = now or datetime.now(timezone.utc)
        try:
            due_dt = datetime.fromisoformat(self.due_date)
            if due_dt.tzinfo is None:
                due_dt = due_dt.replace(tzinfo=timezone.utc)
            delta = due_dt - now
            seconds = delta.total_seconds()

            if seconds <= 0:
                abs_sec = abs(seconds)
                if abs_sec < 60:
                    return "Due now"
                elif abs_sec < 3600:
                    return f"Overdue by {int(abs_sec // 60)}m"
                elif abs_sec < 86400:
                    return f"Overdue by {int(abs_sec // 3600)}h"
                else:
                    return f"Overdue by {int(abs_sec // 86400)}d"
            else:
                if seconds < 60:
                    return f"in {int(seconds)}s"
                elif seconds < 3600:
                    return f"in {int(seconds // 60)}m"
                elif seconds < 86400:
                    return f"in {int(seconds // 3600)}h"
                else:
                    return f"in {round(seconds / 86400, 1)}d"
        except Exception:
            return "Due"

    def masked_word(self) -> str:
        """
        Creates a masked hint of the word for active recall typing mode.
        Example: 'ephemeral' -> 'e _ _ _ _ _ _ l'
        Phrases: 'bite the bullet' -> 'b _ _ e  t _ e  b _ _ _ _ t'
        """
        words = self.word.split()
        masked_parts = []
        for w in words:
            if len(w) <= 2:
                masked_parts.append(w)
            elif len(w) <= 4:
                masked_parts.append(f"{w[0]} {'_ ' * (len(w) - 1)}".strip())
            else:
                middle = " ".join(["_"] * (len(w) - 2))
                masked_parts.append(f"{w[0]} {middle} {w[-1]}")
        return "   ".join(masked_parts)


@dataclass
class ReviewLog:
    id: Optional[int]
    word_id: int
    grade: int
    review_mode: str  # 'flashcard', 'typing', 'quiz'
    scheduled_days: float
    elapsed_seconds: float = 0.0
    thought_time_seconds: float = 0.0  # Recall thinking latency
    hour_of_day: int = 0  # 0 to 23
    day_of_week: int = 0  # 0 (Monday) to 6 (Sunday)
    card_state: str = "review"  # 'new', 'learning', 'relearning', 'review'
    reviewed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> ReviewLog:
        return cls(
            id=row["id"],
            word_id=row["word_id"],
            grade=int(row["grade"]),
            review_mode=row.get("review_mode", "flashcard") or "flashcard",
            scheduled_days=float(row.get("scheduled_days", 0.0) or 0.0),
            elapsed_seconds=float(row.get("elapsed_seconds", 0.0) or 0.0),
            thought_time_seconds=float(row.get("thought_time_seconds", 0.0) or 0.0),
            hour_of_day=int(row.get("hour_of_day", 0) or 0),
            day_of_week=int(row.get("day_of_week", 0) or 0),
            card_state=row.get("card_state", "review") or "review",
            reviewed_at=row.get("reviewed_at", "") or datetime.now(timezone.utc).isoformat(),
        )


@dataclass
class SessionStats:
    total_reviews: int = 0
    unique_words: int = 0
    again_count: int = 0
    hard_count: int = 0
    good_count: int = 0
    easy_count: int = 0
    total_thought_time: float = 0.0
    fluent_count: int = 0    # Latency < 3s (Automatic/fluent recall)
    steady_count: int = 0    # Latency 3s - 7s (Normal recall)
    hesitant_count: int = 0  # Latency > 7s (High retrieval effort)
    timed_reviews: int = 0   # Valid timed reviews (excluding unmeasured and errand outliers)
    outlier_thought_count: int = 0  # Reviews excluded from latency stats due to errand/distraction outliers
    mastered_count: int = 0         # Words achieving permanent mastery during session
    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def retention_rate(self) -> float:
        if self.total_reviews == 0:
            return 0.0
        success = self.good_count + self.easy_count
        return (success / self.total_reviews) * 100.0

    @property
    def avg_thought_time(self) -> float:
        count = self.timed_reviews if self.timed_reviews > 0 else (self.fluent_count + self.steady_count + self.hesitant_count)
        if count == 0:
            return 0.0
        return round(self.total_thought_time / count, 2)


@dataclass
class VocabTestResult:
    id: Optional[int]
    test_type: str  # 'opentdb', 'cefr_benchmark', 'datamuse_synonym'
    total_questions: int
    correct_count: int
    score_pct: float
    cefr_level: str  # 'A1', 'A2', 'B1', 'B2', 'C1', 'C2'
    estimated_vocab_size: int
    avg_response_time: float = 0.0
    details_json: str = ""
    tested_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> VocabTestResult:
        return cls(
            id=row["id"],
            test_type=row.get("test_type", "benchmark"),
            total_questions=int(row.get("total_questions", 0)),
            correct_count=int(row.get("correct_count", 0)),
            score_pct=float(row.get("score_pct", 0.0)),
            cefr_level=row.get("cefr_level", "B1"),
            estimated_vocab_size=int(row.get("estimated_vocab_size", 5000)),
            avg_response_time=float(row.get("avg_response_time", 0.0) or 0.0),
            details_json=row.get("details_json", "") or "",
            tested_at=row.get("tested_at", "") or datetime.now(timezone.utc).isoformat(),
        )

