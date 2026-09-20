"""Browser session state; scheduling and queue policy remain in shared services."""
from dataclasses import asdict
from datetime import datetime, timezone
from time import monotonic
from uuid import uuid4
import random

from werkzeug.exceptions import BadRequest, Conflict
from vocab.models import SRSGrade, SessionStats
from vocab.srs import SRSEngine, RecurrentSessionQueue, rate_session_quality
from vocab.sessions.typing_session import _levenshtein_distance
from vocab.test_service import VocabTestService


class StudySession:
    def __init__(self, db, options):
        self.db = db
        self.mode = options.get("mode", "flashcard")
        if self.mode not in ("flashcard", "typing", "quiz"):
            raise BadRequest("Choose flashcards, typing, or quiz.")
        self.group_id = options.get("group_id")
        self.auto_add = options.get("auto_add_due", True)
        words = db.get_session_words(self.group_id, limit=options["limit"],
            force_all=options.get("force_all", False),
            fill_placeholders=options.get("fill_placeholders", True))
        self.queue = RecurrentSessionQueue(words, enable_shuffling=options.get("shuffle", True),
            previous_sequence=db.get_recent_review_sequence(self.group_id))
        self.total_added = len(words)
        self.seen = {w.id for w in words}
        self.stats = SessionStats()
        self.current = None
        self.phase = "ready"
        self.token = ""
        self.feedback = None
        self.quality = None
        self.next()

    def add_due(self):
        words = self.db.get_newly_due_words(self.group_id, exclude_word_ids=self.seen, limit=20)
        self.seen.update(w.id for w in words)
        added = self.queue.add_cards(words)
        self.total_added += added
        return added

    def next(self):
        if self.phase == "done":
            return
        self.feedback = None
        self.current = None
        while not self.queue.is_empty:
            queued = self.queue.next_card()
            word = self.db.get_word_by_id(queued.id)
            if word and word.state != "mastered":
                self.current = word
                break
        if self.current is None:
            self.finish()
            return
        self.token = uuid4().hex
        self.started = monotonic()
        self.elapsed = None
        self.phase = "introduction" if self.current.state == "new" and self.mode != "quiz" else "question"
        self.choices = []
        if self.mode == "quiz":
            others = self.db.get_random_words(12, exclude_id=self.current.id, group_id=self.group_id)
            if len(others) < 3:
                others += self.db.get_random_words(12, exclude_id=self.current.id)
            self.choices = list(dict.fromkeys(w.word for w in others if w.word != self.current.word))[:3]
            if not self.choices:
                # A one-word deck still permits meaningful recognition practice.
                self.choices = ["None of these"]
            self.choices.append(self.current.word)
            random.shuffle(self.choices)

    def view(self):
        remaining = self.queue.remaining_count + int(self.current is not None and self.phase != "feedback")
        result = {"mode": self.mode, "phase": self.phase, "token": self.token,
            "remaining": remaining, "removed": len(self.queue.completed_word_ids),
            "initial": self.queue.total_initial, "completed": len(self.queue.completed_word_ids),
            "total_added": self.total_added,
            "auto_add": self.auto_add,
            "reviews": self.stats.total_reviews, "retention": self.stats.retention_rate,
            "average_seconds": self.stats.avg_thought_time, "feedback": self.feedback,
            "grades": {"Again": self.stats.again_count, "Hard": self.stats.hard_count,
                       "Good": self.stats.good_count, "Easy": self.stats.easy_count}}
        if self.current and self.phase != "done":
            word = self.current
            result["card"] = {"id": word.id, "group_name": word.group_name, "state": word.state,
                "pos": word.pos, "tags": word.tags}
            if self.mode == "flashcard":
                result["card"].update(word=word.word, phonetic=word.phonetic)
            if self.mode != "flashcard" or self.phase != "question":
                result["card"]["definition"] = word.definition
            if self.phase in ("introduction", "revealed", "feedback"):
                result["card"].update({k: getattr(word, k) for k in ("word", "phonetic", "example", "mnemonic")})
            if self.phase == "revealed":
                result["intervals"] = {str(int(k)): v for k, v in SRSEngine.preview_intervals(word).items()}
            result["choices"] = self.choices
        return result

    def act(self, data):
        action = data.get("action")
        if action == "end":
            self.finish()
            return self.view()
        if self.phase == "done":
            raise Conflict("This session has ended. Start a new session.")
        if action == "shuffle":
            self.queue.shuffle_remaining()
            return self.view()
        if action == "add_due":
            self.add_due()
            return self.view()
        if action == "set_auto_add":
            enabled = data.get("enabled")
            if type(enabled) is not bool:
                raise BadRequest("Auto-add must be true or false.")
            self.auto_add = enabled
            return self.view()
        if data.get("token") != self.token:
            raise Conflict("This card has already changed. Refresh the session.")
        if action == "next" and self.phase == "feedback":
            if self.auto_add:
                self.add_due()
            self.next()
            return self.view()
        if action == "skip":
            self.next()
            return self.view()
        if action == "reveal" and self.mode == "flashcard" and self.phase == "question":
            self.elapsed = monotonic() - self.started
            self.phase = "revealed"
            return self.view()
        intro = action == "introduce" and self.phase == "introduction"
        if not intro and not ((action == "grade" and self.mode == "flashcard" and self.phase == "revealed") or
                              (action == "answer" and self.mode in ("typing", "quiz") and self.phase == "question")):
            raise Conflict("That action is not available for this card.")
        if intro:
            grade = SRSGrade.GOOD
        elif self.mode == "flashcard":
            try:
                grade = SRSGrade(int(data.get("grade", 0)))
            except (ValueError, TypeError):
                raise BadRequest("Choose a grade from 1 to 4.")
        elif self.mode == "typing":
            answer = str(data.get("answer", "")).strip().casefold()
            if not answer or len(answer) > 500:
                raise BadRequest("Enter an answer of 1–500 characters.")
            correct = self.current.word.strip().casefold()
            grade = SRSGrade.GOOD if answer == correct else (SRSGrade.HARD if _levenshtein_distance(answer, correct) <= 2 else SRSGrade.AGAIN)
        else:
            choice = data.get("choice")
            if type(choice) is not int or not 0 <= choice < len(self.choices):
                raise BadRequest("Select an answer.")
            grade = SRSGrade.GOOD if self.choices[choice] == self.current.word else SRSGrade.AGAIN
        seconds = 0 if intro else (self.elapsed if self.elapsed is not None else monotonic() - self.started)
        effective_seconds = seconds if seconds <= self.db.get_max_thought_time_threshold() else 0
        now = datetime.now(timezone.utc)
        # Compare and write under one SQLite transaction, including the history log.
        with self.db.transaction():
            saved = self.db.get_word_by_id(self.current.id)
            if saved is None or asdict(saved) != asdict(self.current):
                raise Conflict("This word was edited or reviewed elsewhere. Skip it to load the next card.")
            mode = "introduction" if intro else self.mode
            if self.mode == "quiz":
                updated, days = saved, saved.interval_days
            else:
                updated, days = SRSEngine.calculate_next_state(saved, grade, effective_seconds, now=now)
                if intro:
                    updated.state, updated.step, updated.reps = "learning", 0, 0
                self.db.update_word(updated)
            self.db.log_review(saved.id, int(grade), mode, days, elapsed_seconds=seconds,
                thought_time_seconds=seconds, card_state=saved.state, now=now)
        self.current = updated
        if intro:
            self.queue.requeue_card(updated, custom_offset=3)
        else:
            self.queue.handle_result(updated, grade, effective_seconds)
            self.stats.total_reviews += 1
            name = {1: "again_count", 2: "hard_count", 3: "good_count", 4: "easy_count"}[int(grade)]
            setattr(self.stats, name, getattr(self.stats, name) + 1)
            if 0 < seconds <= self.db.get_max_thought_time_threshold():
                self.stats.timed_reviews += 1
                self.stats.total_thought_time += seconds
        self.feedback = {"grade": grade.name.title(), "introduced": intro,
            "message": "Added to this session for recall." if intro else
                       ("Practice recorded; review schedule preserved." if self.mode == "quiz" else "Review saved."),
            "seconds": round(seconds, 1), "due": updated.due_date}
        self.phase = "feedback"
        return self.view()

    def finish(self):
        if self.phase == "done":
            return
        if self.stats.total_reviews and self.queue.completed_words:
            self.quality = rate_session_quality(queue=self.queue, stats=self.stats)
            self.db.tune_capacity_threshold(self.quality["total_load"], self.quality["quality_score"], self.group_id)
        self.phase = "done"
        self.current = None


class CheckSession:
    def __init__(self, db, options):
        self.db = db
        self.source = options.get("source", "benchmark")
        amount = options["limit"]
        if self.source == "benchmark":
            self.questions = VocabTestService.get_leveled_benchmark_questions(amount, options.get("level") or None)
        elif self.source == "opentdb":
            self.questions = VocabTestService.fetch_opentdb_questions(amount=amount)
        elif self.source == "datamuse":
            self.questions = VocabTestService.fetch_datamuse_questions(amount=amount)
        else:
            raise BadRequest("Unknown question source.")
        self.answers, self.times = [], []
        self.phase, self.feedback, self.result = "question", None, None
        self.token = uuid4().hex
        self.started = monotonic()

    def view(self):
        result = {"mode": "check", "phase": self.phase, "token": self.token,
            "total": len(self.questions), "answered": len(self.answers), "feedback": self.feedback,
            "result": self.result}
        if self.phase != "done":
            index = len(self.answers) - int(self.phase == "feedback")
            q = self.questions[index]
            result["question"] = {"prompt": q.prompt, "choices": q.choices, "category": q.category, "level": q.cefr_level}
        return result

    def act(self, data):
        if self.phase == "done":
            return self.view()
        if data.get("action") == "end":
            self.finish()
            return self.view()
        if data.get("token") != self.token:
            raise Conflict("This question has changed. Refresh the session.")
        if data.get("action") == "next" and self.phase == "feedback":
            if len(self.answers) == len(self.questions):
                self.finish()
            else:
                self.phase, self.feedback = "question", None
                self.token, self.started = uuid4().hex, monotonic()
        elif data.get("action") == "answer" and self.phase == "question":
            q = self.questions[len(self.answers)]
            choice = data.get("choice")
            if type(choice) is not int or not 0 <= choice < len(q.choices):
                raise BadRequest("Select an answer.")
            correct = choice == q.correct_index
            self.answers.append(correct)
            self.times.append(monotonic() - self.started)
            self.feedback = {"correct": correct, "answer": q.correct_answer, "explanation": q.explanation}
            self.phase = "feedback"
        else:
            raise Conflict("This question has already been answered.")
        return self.view()

    def finish(self):
        if self.phase == "done":
            return
        self.result = VocabTestService.estimate_proficiency(self.questions[:len(self.answers)], self.answers)
        if self.answers:
            import json
            self.db.log_test_result(self.source, len(self.answers), sum(self.answers),
                self.result["score_pct"], "Uncalibrated", 0, sum(self.times) / len(self.times),
                details_json=json.dumps(self.result))
        self.phase = "done"
