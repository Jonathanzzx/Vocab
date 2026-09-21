"""
Database manager and SQLite queries for Vocab app.
"""
from __future__ import annotations
import sqlite3
import os
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any, Tuple, Generator
from vocab.models import Group, Word, ReviewLog, CardState, SRSGrade, VocabTestResult
from vocab.srs import MAX_VALID_THOUGHT_TIME, is_valid_thought_time


DEFAULT_DB_FILENAME = "vocab_data.db"


class Database:
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            # Default to vocab_data.db in the current workspace or directory
            self.db_path = os.path.abspath(DEFAULT_DB_FILENAME)
        else:
            self.db_path = os.path.abspath(db_path)

        self._init_db()
        # Filter timing outliers when reporting; preserve raw historical records.

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 10000")
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self.get_connection() as conn:
            if self.db_path != ":memory:":
                try:
                    conn.execute("PRAGMA journal_mode = WAL")
                except sqlite3.OperationalError:
                    pass
            cursor = conn.cursor()

            # Groups table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS groups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    description TEXT DEFAULT '',
                    color TEXT DEFAULT 'cyan',
                    created_at TEXT NOT NULL
                )
            """)

            # Words table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS words (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
                    word TEXT NOT NULL,
                    definition TEXT NOT NULL,
                    phonetic TEXT DEFAULT '',
                    pos TEXT DEFAULT '',
                    example TEXT DEFAULT '',
                    mnemonic TEXT DEFAULT '',
                    tags TEXT DEFAULT '',
                    state TEXT DEFAULT 'new',
                    step INTEGER DEFAULT 0,
                    interval_days REAL DEFAULT 0.0,
                    ease_factor REAL DEFAULT 2.5,
                    reps INTEGER DEFAULT 0,
                    lapses INTEGER DEFAULT 0,
                    due_date TEXT NOT NULL,
                    last_reviewed TEXT,
                    created_at TEXT NOT NULL
                )
            """)

            # Indexes for quick retrieval and review scheduling
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_words_group ON words(group_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_words_due ON words(due_date)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_words_state ON words(state)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_words_word ON words(word)")

            # Review logs
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS review_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    word_id INTEGER NOT NULL REFERENCES words(id) ON DELETE CASCADE,
                    grade INTEGER NOT NULL,
                    review_mode TEXT NOT NULL,
                    scheduled_days REAL NOT NULL,
                    elapsed_seconds REAL DEFAULT 0.0,
                    thought_time_seconds REAL DEFAULT 0.0,
                    hour_of_day INTEGER DEFAULT 0,
                    day_of_week INTEGER DEFAULT 0,
                    card_state TEXT DEFAULT 'review',
                    reviewed_at TEXT NOT NULL
                )
            """)
            # Schema migrations for existing databases
            cursor.execute("PRAGMA table_info(review_logs)")
            log_cols = {col["name"] for col in cursor.fetchall()}
            if "thought_time_seconds" not in log_cols:
                cursor.execute("ALTER TABLE review_logs ADD COLUMN thought_time_seconds REAL DEFAULT 0.0")
            if "hour_of_day" not in log_cols:
                cursor.execute("ALTER TABLE review_logs ADD COLUMN hour_of_day INTEGER DEFAULT 0")
            if "day_of_week" not in log_cols:
                cursor.execute("ALTER TABLE review_logs ADD COLUMN day_of_week INTEGER DEFAULT 0")
            if "card_state" not in log_cols:
                cursor.execute("ALTER TABLE review_logs ADD COLUMN card_state TEXT DEFAULT 'review'")

            cursor.execute("CREATE INDEX IF NOT EXISTS idx_logs_reviewed_at ON review_logs(reviewed_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_logs_hour ON review_logs(hour_of_day)")

            # Settings key-value table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)

            cursor.execute("PRAGMA table_info(words)")
            word_cols = {col["name"] for col in cursor.fetchall()}
            if "avg_thought_time" not in word_cols:
                cursor.execute("ALTER TABLE words ADD COLUMN avg_thought_time REAL DEFAULT 0.0")
            if "last_thought_time" not in word_cols:
                cursor.execute("ALTER TABLE words ADD COLUMN last_thought_time REAL DEFAULT 0.0")
            if "difficulty" not in word_cols:
                cursor.execute("ALTER TABLE words ADD COLUMN difficulty REAL DEFAULT 5.0")
            if "stability" not in word_cols:
                cursor.execute("ALTER TABLE words ADD COLUMN stability REAL DEFAULT 1.0")

            # Vocabulary proficiency tests & benchmark table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS vocab_tests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    test_type TEXT NOT NULL,
                    total_questions INTEGER NOT NULL,
                    correct_count INTEGER NOT NULL,
                    score_pct REAL NOT NULL,
                    cefr_level TEXT NOT NULL,
                    estimated_vocab_size INTEGER NOT NULL,
                    avg_response_time REAL DEFAULT 0.0,
                    details_json TEXT DEFAULT '',
                    tested_at TEXT NOT NULL
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_vocab_tests_tested_at ON vocab_tests(tested_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_vocab_tests_type ON vocab_tests(test_type)")

            # Auto-repair migration for invalid small-sample tests or previously miscalculated tests
            cursor.execute("""
                UPDATE vocab_tests
                SET cefr_level = 'A1',
                    estimated_vocab_size = 2000
                WHERE total_questions < 5 AND cefr_level IN ('C1', 'C2')
            """)
            cursor.execute("""
                UPDATE vocab_tests
                SET cefr_level = 'B2',
                    estimated_vocab_size = 13750
                WHERE total_questions = 12 AND correct_count = 8 AND cefr_level = 'B1'
            """)

            conn.commit()

    # --- Group Operations ---

    def create_group(self, name: str, description: str = "", color: str = "cyan") -> int:
        now = datetime.now(timezone.utc).isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO groups (name, description, color, created_at) VALUES (?, ?, ?, ?)",
                (name.strip(), description.strip(), color, now)
            )
            conn.commit()
            return cursor.lastrowid

    def get_groups(self) -> List[Group]:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = """
                SELECT g.id, g.name, g.description, g.color, g.created_at,
                       COUNT(w.id) AS word_count,
                       SUM(CASE WHEN w.state != 'mastered' AND (w.state = 'new' OR w.due_date <= ?) THEN 1 ELSE 0 END) AS due_count
                FROM groups g
                LEFT JOIN words w ON g.id = w.group_id
                GROUP BY g.id
                ORDER BY g.name COLLATE NOCASE ASC
            """
            cursor.execute(query, (now_iso,))
            rows = cursor.fetchall()
            return [Group.from_row(dict(r)) for r in rows]

    def get_group_by_id(self, group_id: int) -> Optional[Group]:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = """
                SELECT g.id, g.name, g.description, g.color, g.created_at,
                       COUNT(w.id) AS word_count,
                       SUM(CASE WHEN w.state != 'mastered' AND (w.state = 'new' OR w.due_date <= ?) THEN 1 ELSE 0 END) AS due_count
                FROM groups g
                LEFT JOIN words w ON g.id = w.group_id
                WHERE g.id = ?
                GROUP BY g.id
            """
            cursor.execute(query, (now_iso, group_id))
            row = cursor.fetchone()
            return Group.from_row(dict(row)) if row else None

    def get_group_by_name(self, name: str) -> Optional[Group]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM groups WHERE name = ? COLLATE NOCASE", (name.strip(),))
            row = cursor.fetchone()
            if row:
                return self.get_group_by_id(row["id"])
            return None

    def update_group(self, group_id: int, name: str, description: str = "", color: str = "cyan") -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE groups SET name = ?, description = ?, color = ? WHERE id = ?",
                (name.strip(), description.strip(), color, group_id)
            )
            conn.commit()
            return cursor.rowcount > 0

    def delete_group(self, group_id: int) -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM groups WHERE id = ?", (group_id,))
            conn.commit()
            return cursor.rowcount > 0

    # --- Word Operations ---

    def add_word(
        self,
        group_id: int,
        word: str,
        definition: str,
        phonetic: str = "",
        pos: str = "",
        example: str = "",
        mnemonic: str = "",
        tags: str = ""
    ) -> int:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO words (
                    group_id, word, definition, phonetic, pos, example, mnemonic, tags,
                    state, step, interval_days, ease_factor, reps, lapses, due_date, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'new', 0, 0.0, 2.5, 0, 0, ?, ?)
            """, (
                group_id, word.strip(), definition.strip(), phonetic.strip(),
                pos.strip(), example.strip(), mnemonic.strip(), tags.strip(),
                now_iso, now_iso
            ))
            conn.commit()
            return cursor.lastrowid

    def get_word_by_id(self, word_id: int) -> Optional[Word]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT w.*, g.name AS group_name
                FROM words w
                JOIN groups g ON w.group_id = g.id
                WHERE w.id = ?
            """, (word_id,))
            row = cursor.fetchone()
            return Word.from_row(dict(row)) if row else None

    def update_word(self, word: Word) -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE words SET
                    group_id = ?,
                    word = ?,
                    definition = ?,
                    phonetic = ?,
                    pos = ?,
                    example = ?,
                    mnemonic = ?,
                    tags = ?,
                    state = ?,
                    step = ?,
                    interval_days = ?,
                    ease_factor = ?,
                    reps = ?,
                    lapses = ?,
                    due_date = ?,
                    last_reviewed = ?,
                    avg_thought_time = ?,
                    last_thought_time = ?,
                    difficulty = ?,
                    stability = ?
                WHERE id = ?
            """, (
                word.group_id, word.word, word.definition, word.phonetic, word.pos,
                word.example, word.mnemonic, word.tags, word.state, word.step,
                word.interval_days, word.ease_factor, word.reps, word.lapses,
                word.due_date, word.last_reviewed,
                word.avg_thought_time, word.last_thought_time,
                word.difficulty, word.stability,
                word.id
            ))
            conn.commit()
            return cursor.rowcount > 0

    def delete_word(self, word_id: int) -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM words WHERE id = ?", (word_id,))
            conn.commit()
            return cursor.rowcount > 0

    def get_due_words(self, group_id: Optional[int] = None, limit: int = 50) -> List[Word]:
        """
        Fetches all words that are currently due (or new), ordered adaptively.
        Urgency calculation handles exact prioritization.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = """
                SELECT w.*, g.name AS group_name
                FROM words w
                JOIN groups g ON w.group_id = g.id
                WHERE w.state != 'mastered' AND (w.state = 'new' OR w.due_date <= ?)
            """
            params: List[Any] = [now_iso]
            if group_id is not None:
                query += " AND w.group_id = ?"
                params.append(group_id)

            cursor.execute(query, params)
            rows = cursor.fetchall()
            words = [Word.from_row(dict(r)) for r in rows]

            # Sort adaptively using urgency score (high urgency first)
            now = datetime.now(timezone.utc)
            words.sort(key=lambda w: w.urgency_score(now), reverse=True)
            return words[:limit]

    def tune_capacity_threshold(
        self,
        load: float,
        quality_score: float,
        group_id: Optional[int] = None,
        learning_rate: float = 12.0
    ) -> Dict[str, Any]:
        """
        Tunes and persists the user's adaptive brain capacity threshold
        based on load vs. learning quality comparison.
        """
        key = f"capacity_threshold_{group_id}" if group_id is not None else "capacity_threshold"
        stored_cap = self.get_setting(key)
        if stored_cap is None and group_id is not None:
            stored_cap = self.get_setting("capacity_threshold")

        current_threshold = int(round(float(stored_cap))) if stored_cap is not None else 100

        from vocab.srs import tune_capacity_threshold
        result = tune_capacity_threshold(
            current_threshold=current_threshold,
            session_load=load,
            quality_score=quality_score,
            learning_rate=learning_rate
        )
        self.set_setting(key, str(result["new_threshold"]))
        return result

    def get_adaptive_capacity_limit(self, group_id: Optional[int] = None) -> int:
        """
        Adaptively calculates the session cognitive 'brain capacity' limit based on user performance.
        - Checks if a tuned threshold exists in settings (calibrated from load vs. quality).
        - Analyzes recent review history (up to 50 reviews).
        - If fewer than 5 reviews exist, defaults to tuned base capacity (or 100).
        - Dynamically adjusts based on:
          1. Retention rate (target ~90%): reward high retention (+), scale down if struggling (-).
          2. Lapse / Again rate: penalize high lapses (>15%), reward low lapses (<8%).
          3. Thought time / Latency: reward rapid fluent recall (<=3s), penalize high hesitation (>6s).
        - Clamps the result between 60 and 160.
        """
        key = f"capacity_threshold_{group_id}" if group_id is not None else "capacity_threshold"
        stored_cap = self.get_setting(key)
        if stored_cap is None and group_id is not None:
            stored_cap = self.get_setting("capacity_threshold")

        base_capacity = float(stored_cap) if stored_cap is not None else 100.0

        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = """
                SELECT rl.grade, rl.thought_time_seconds, rl.elapsed_seconds
                FROM review_logs rl
                JOIN words w ON rl.word_id = w.id
            """
            params: List[Any] = []
            if group_id is not None:
                query += " WHERE w.group_id = ?"
                params.append(group_id)
            query += " ORDER BY rl.reviewed_at DESC, rl.id DESC LIMIT 50"

            cursor.execute(query, params)
            rows = cursor.fetchall()

            # If fewer than 5 reviews for this specific group, fallback to global reviews across all groups
            if len(rows) < 5 and group_id is not None:
                cursor.execute("""
                    SELECT rl.grade, rl.thought_time_seconds, rl.elapsed_seconds
                    FROM review_logs rl
                    ORDER BY rl.reviewed_at DESC, rl.id DESC LIMIT 50
                """)
                rows = cursor.fetchall()

        if len(rows) < 5:
            return int(round(base_capacity))

        total_reviews = len(rows)
        success_count = sum(1 for r in rows if r["grade"] in (3, 4))
        again_count = sum(1 for r in rows if r["grade"] == 1)

        retention_rate = (success_count / total_reviews) * 100.0
        again_rate = again_count / total_reviews

        max_tt = self.get_max_thought_time_threshold()
        thought_times = [
            float(r["thought_time_seconds"])
            for r in rows
            if r["thought_time_seconds"] is not None and 0.0 < float(r["thought_time_seconds"]) <= max_tt
        ]
        avg_thought_time = (sum(thought_times) / len(thought_times)) if thought_times else 0.0

        # 1. Retention rate adjustment: benchmark 90.0%
        retention_delta = (retention_rate - 90.0) * 1.5

        # 2. Lapse rate adjustment
        lapse_adj = 0.0
        if again_rate > 0.15:
            lapse_adj = -min(20.0, (again_rate - 0.15) * 100.0)
        elif again_rate < 0.08:
            lapse_adj = min(10.0, (0.08 - again_rate) * 100.0)

        # 3. Latency adjustment
        latency_adj = 0.0
        if 0.0 < avg_thought_time <= 3.0:
            latency_adj = min(12.0, (3.0 - avg_thought_time) * 4.0)
        elif avg_thought_time > 6.0:
            latency_adj = -min(20.0, (avg_thought_time - 6.0) * 3.0)

        total_cap = base_capacity + retention_delta + lapse_adj + latency_adj
        clamped_cap = max(60, min(160, int(round(total_cap))))
        return clamped_cap

    def get_session_words(
        self,
        group_id: Optional[int] = None,
        limit: int = 20,
        force_all: bool = False,
        fill_placeholders: bool = True,
        max_capacity: Optional[int] = None
    ) -> List[Word]:
        """
        Retrieves words for a study session subject to cognitive 'brain capacity' budget.
        - Automatically computes an adaptive capacity limit based on user review performance if max_capacity is None.
        - Reviews and learning/relearning cards are prioritized first to protect retention.
        - New words ('new words take a lot') are added if remaining capacity permits (20 capacity each).
        - If caught up or backfilling, upcoming cards (closest due) are added as placeholders.
        - Total session brain capacity never exceeds max_capacity.
        """
        if max_capacity is None:
            max_capacity = self.get_adaptive_capacity_limit(group_id=group_id)

        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()

        if force_all:
            words = [w for w in self.get_words(group_id=group_id, limit=limit) if w.state != CardState.MASTERED.value]
            selected = []
            cur_cap = 0
            for w in words:
                cost = w.brain_capacity
                if cur_cap + cost <= max_capacity:
                    selected.append(w)
                    cur_cap += cost
            return selected

        selected_words: List[Word] = []
        current_capacity = 0
        selected_ids: set[int] = set()

        def try_add(w: Word) -> bool:
            nonlocal current_capacity
            if w.id in selected_ids:
                return False
            cost = w.brain_capacity
            if current_capacity + cost <= max_capacity and len(selected_words) < limit:
                selected_words.append(w)
                selected_ids.add(w.id)
                current_capacity += cost
                return True
            return False

        # 1. Fetch due reviews & due learning/relearning words
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = """
                SELECT w.*, g.name AS group_name
                FROM words w
                JOIN groups g ON w.group_id = g.id
                WHERE w.state NOT IN ('new', 'mastered') AND w.due_date <= ?
            """
            params: List[Any] = [now_iso]
            if group_id is not None:
                query += " AND w.group_id = ?"
                params.append(group_id)

            cursor.execute(query, params)
            due_reviews = [Word.from_row(dict(r)) for r in cursor.fetchall()]

        # Sort due reviews by urgency score (highest urgency first)
        due_reviews.sort(key=lambda w: w.urgency_score(now), reverse=True)
        for w in due_reviews:
            try_add(w)

        # 2. Fetch new words (taking 20 brain capacity each)
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = """
                SELECT w.*, g.name AS group_name
                FROM words w
                JOIN groups g ON w.group_id = g.id
                WHERE w.state = 'new'
            """
            params = []
            if group_id is not None:
                query += " AND w.group_id = ?"
                params.append(group_id)
            query += " ORDER BY w.id ASC"

            cursor.execute(query, params)
            new_words = [Word.from_row(dict(r)) for r in cursor.fetchall()]

        for w in new_words:
            try_add(w)

        initial_due_and_new_count = len(selected_words)

        # 3. Backfill with upcoming placeholders if enabled or if caught up
        should_fill = fill_placeholders or (initial_due_and_new_count == 0)
        if should_fill and current_capacity < max_capacity and len(selected_words) < limit:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                query = """
                    SELECT w.*, g.name AS group_name
                    FROM words w
                    JOIN groups g ON w.group_id = g.id
                    WHERE w.state NOT IN ('new', 'mastered') AND w.due_date > ?
                """
                params = [now_iso]
                if group_id is not None:
                    query += " AND w.group_id = ?"
                    params.append(group_id)
                query += " ORDER BY w.due_date ASC"

                cursor.execute(query, params)
                upcoming = [Word.from_row(dict(r)) for r in cursor.fetchall()]

            for p in upcoming:
                if p.id not in selected_ids:
                    p.is_placeholder = True
                    try_add(p)

        # 4. Pull from other groups if group_id is specified and placeholders enabled
        if fill_placeholders and group_id is not None and len(selected_words) < limit and current_capacity < max_capacity:
            id_filter = ",".join("?" for _ in selected_ids) if selected_ids else "0"
            with self.get_connection() as conn:
                cursor = conn.cursor()
                query = f"""
                    SELECT w.*, g.name AS group_name
                    FROM words w
                    JOIN groups g ON w.group_id = g.id
                    WHERE w.state != 'mastered' AND w.id NOT IN ({id_filter})
                    ORDER BY (w.state = 'new') DESC, w.due_date ASC
                """
                params = list(selected_ids) if selected_ids else []
                cursor.execute(query, params)
                extra = [Word.from_row(dict(r)) for r in cursor.fetchall()]

            for ep in extra:
                ep.is_placeholder = True
                try_add(ep)

        # 5. When all caught up, sort words strictly in ascending order of closest due time
        if initial_due_and_new_count == 0:
            def _sort_due_dt(w: Word) -> tuple[datetime, float]:
                due_dt = datetime.max.replace(tzinfo=timezone.utc)
                if w.due_date:
                    try:
                        dt = datetime.fromisoformat(w.due_date.replace("Z", "+00:00"))
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        due_dt = dt
                    except Exception:
                        pass
                return (due_dt, w.retrievability(now))

            selected_words.sort(key=_sort_due_dt)
        else:
            old_words = [
                w for w in selected_words
                if getattr(w, "is_placeholder", False) or w.state != CardState.NEW.value
            ]
            new_words = [
                w for w in selected_words
                if not getattr(w, "is_placeholder", False) and w.state == CardState.NEW.value
            ]
            if old_words and new_words:
                selected_words = self._alternate_word_lists(old_words, new_words, prefer_old_first=True)

        return selected_words

    @staticmethod
    def _alternate_word_lists(
        old_words: List[Word],
        new_words: List[Word],
        prefer_old_first: bool = True
    ) -> List[Word]:
        """
        Interleaves old review/placeholder cards and new learning cards
        using exact integer proportional placement so they appear alternately.
        """
        from vocab.srs import RecurrentSessionQueue
        return RecurrentSessionQueue._alternate_old_and_new(
            old_words, new_words, prefer_old_first=prefer_old_first
        )

    def get_newly_due_words(
        self,
        group_id: Optional[int] = None,
        exclude_word_ids: Optional[set[int]] = None,
        limit: int = 20
    ) -> List[Word]:
        """
        Fetches cards in the database that are currently due (due_date <= now OR state = 'new'),
        excluding any specified IDs (such as cards already active in the current session queue).
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        exclude_ids = list(exclude_word_ids or set())

        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = """
                SELECT w.*, g.name AS group_name
                FROM words w
                JOIN groups g ON w.group_id = g.id
                WHERE w.state != 'mastered' AND (w.state = 'new' OR w.due_date <= ?)
            """
            params: List[Any] = [now_iso]
            if group_id is not None:
                query += " AND w.group_id = ?"
                params.append(group_id)

            if exclude_ids:
                id_placeholders = ",".join("?" for _ in exclude_ids)
                query += f" AND w.id NOT IN ({id_placeholders})"
                params.extend(exclude_ids)

            query += " ORDER BY (w.state = 'new') DESC, w.due_date ASC LIMIT ?"
            params.append(limit)

            cursor.execute(query, params)
            words = [Word.from_row(dict(r)) for r in cursor.fetchall()]

            now = datetime.now(timezone.utc)
            words.sort(key=lambda w: w.urgency_score(now), reverse=True)
            return words

    def _build_words_filter_clause(
        self,
        group_id: Optional[int] = None,
        search: Optional[str] = None,
        state: Optional[str] = None,
        pos: Optional[str] = None,
        tag: Optional[str] = None,
        due_only: bool = False,
    ) -> Tuple[str, List[Any]]:
        where_sql = " WHERE 1=1"
        params: List[Any] = []
        if group_id is not None:
            where_sql += " AND w.group_id = ?"
            params.append(group_id)
        if state is not None:
            where_sql += " AND w.state = ?"
            params.append(state.lower().strip())
        if pos is not None and pos.strip():
            where_sql += " AND LOWER(w.pos) = ?"
            params.append(pos.lower().strip())
        if tag is not None and tag.strip():
            where_sql += " AND w.tags LIKE ?"
            params.append(f"%{tag.strip()}%")
        if search is not None and search.strip():
            where_sql += " AND (w.word LIKE ? OR w.definition LIKE ? OR w.tags LIKE ? OR w.example LIKE ?)"
            pattern = f"%{search.strip()}%"
            params.extend([pattern, pattern, pattern, pattern])
        if due_only:
            now_iso = datetime.now(timezone.utc).isoformat()
            where_sql += " AND w.state != 'mastered' AND (w.state = 'new' OR w.due_date <= ?)"
            params.append(now_iso)
        return where_sql, params

    def count_words(
        self,
        group_id: Optional[int] = None,
        search: Optional[str] = None,
        state: Optional[str] = None,
        pos: Optional[str] = None,
        tag: Optional[str] = None,
        due_only: bool = False,
    ) -> int:
        """Counts total words matching the given filters."""
        where_sql, params = self._build_words_filter_clause(
            group_id=group_id, search=search, state=state, pos=pos, tag=tag, due_only=due_only
        )
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = f"""
                SELECT COUNT(*)
                FROM words w
                JOIN groups g ON w.group_id = g.id
                {where_sql}
            """
            cursor.execute(query, params)
            row = cursor.fetchone()
            return int(row[0]) if row else 0

    def get_words(
        self,
        group_id: Optional[int] = None,
        search: Optional[str] = None,
        state: Optional[str] = None,
        pos: Optional[str] = None,
        tag: Optional[str] = None,
        due_only: bool = False,
        sort_by: str = "id",
        sort_order: str = "desc",
        limit: int = 100,
        offset: int = 0
    ) -> List[Word]:
        """
        Retrieves words with flexible filtering, multi-field sorting, and pagination.
        """
        where_sql, params = self._build_words_filter_clause(
            group_id=group_id, search=search, state=state, pos=pos, tag=tag, due_only=due_only
        )

        sort_key = (sort_by or "id").lower().strip()
        order_key = (sort_order or "desc").lower().strip()
        direction = "ASC" if order_key == "asc" else "DESC"

        sort_col_map = {
            "id": "w.id",
            "word": "LOWER(w.word)",
            "alphabetical": "LOWER(w.word)",
            "name": "LOWER(w.word)",
            "state": "w.state",
            "pos": "LOWER(w.pos)",
            "deck": "LOWER(g.name)",
            "group": "LOWER(g.name)",
            "ease": "w.ease_factor",
            "ease_factor": "w.ease_factor",
            "interval": "w.interval_days",
            "interval_days": "w.interval_days",
            "reps": "w.reps",
            "lapses": "w.lapses",
            "created": "w.created_at",
            "created_at": "w.created_at",
            "due": "w.due_date",
            "due_date": "w.due_date",
        }

        if sort_key in ("due", "due_date"):
            if direction == "ASC":
                order_by_sql = "ORDER BY (w.state = 'new') DESC, w.due_date ASC, w.id ASC"
            else:
                order_by_sql = "ORDER BY w.due_date DESC, (w.state = 'new') ASC, w.id DESC"
        else:
            col = sort_col_map.get(sort_key, "w.id")
            if col == "w.id":
                order_by_sql = f"ORDER BY w.id {direction}"
            else:
                order_by_sql = f"ORDER BY {col} {direction}, w.id DESC"

        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = f"""
                SELECT w.*, g.name AS group_name
                FROM words w
                JOIN groups g ON w.group_id = g.id
                {where_sql}
                {order_by_sql}
                LIMIT ? OFFSET ?
            """
            params.extend([limit, offset])
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [Word.from_row(dict(r)) for r in rows]

    def list_words(
        self,
        group_id: Optional[int] = None,
        search: Optional[str] = None,
        state: Optional[str] = None,
        pos: Optional[str] = None,
        tag: Optional[str] = None,
        due_only: bool = False,
        sort_by: str = "id",
        sort_order: str = "desc",
        limit: int = 100,
        offset: int = 0
    ) -> List[Word]:
        """Alias for get_words with full filtering and sorting support."""
        return self.get_words(
            group_id=group_id,
            search=search,
            state=state,
            pos=pos,
            tag=tag,
            due_only=due_only,
            sort_by=sort_by,
            sort_order=sort_order,
            limit=limit,
            offset=offset
        )

    def get_random_words(self, count: int = 4, exclude_id: Optional[int] = None, group_id: Optional[int] = None) -> List[Word]:
        """Gets random words for multiple-choice distractors."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = """
                SELECT w.*, g.name AS group_name
                FROM words w
                JOIN groups g ON w.group_id = g.id
                WHERE 1=1
            """
            params: List[Any] = []
            if exclude_id is not None:
                query += " AND w.id != ?"
                params.append(exclude_id)
            if group_id is not None:
                query += " AND w.group_id = ?"
                params.append(group_id)

            query += " ORDER BY RANDOM() LIMIT ?"
            params.append(count)

            cursor.execute(query, params)
            rows = cursor.fetchall()
            # If not enough in the same group, fallback to any group
            if len(rows) < count and group_id is not None:
                return self.get_random_words(count=count, exclude_id=exclude_id, group_id=None)
            return [Word.from_row(dict(r)) for r in rows]

    # --- Review Logging & Analytics ---

    def log_review(
        self,
        word_id: int,
        grade: int,
        review_mode: str,
        scheduled_days: float,
        elapsed_seconds: float = 0.0,
        thought_time_seconds: float = 0.0,
        card_state: Optional[str] = None,
        now: Optional[datetime] = None
    ) -> int:
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.astimezone()
        now_iso = now.astimezone(timezone.utc).isoformat()
        local_time = now.astimezone()
        hour = local_time.hour
        dow = local_time.weekday()
        if card_state is None:
            card_state = "learning" if scheduled_days <= 1.0 else "review"
        max_tt = self.get_max_thought_time_threshold()
        cleaned_tt = thought_time_seconds if is_valid_thought_time(thought_time_seconds, float("inf")) else 0.0
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO review_logs (
                    word_id, grade, review_mode, scheduled_days, elapsed_seconds,
                    thought_time_seconds, hour_of_day, day_of_week, card_state, reviewed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                word_id, grade, review_mode, scheduled_days, elapsed_seconds,
                cleaned_tt, hour, dow, card_state, now_iso
            ))
            conn.commit()
            return cursor.lastrowid

    def get_recent_review_sequence(self, group_id: Optional[int] = None, limit: int = 50) -> List[int]:
        """
        Fetches the sequence of distinct word IDs from recent reviews in chronological order
        (earliest to latest in the recent review window), capturing the sequence of cards the user saw.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = """
                SELECT rl.word_id
                FROM review_logs rl
                JOIN words w ON rl.word_id = w.id
            """
            params: List[Any] = []
            if group_id is not None:
                query += " WHERE w.group_id = ?"
                params.append(group_id)
            query += " ORDER BY rl.reviewed_at DESC, rl.id DESC LIMIT ?"
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [r["word_id"] for r in rows][::-1]

    def get_word_review_logs(self, word_id: int) -> List[ReviewLog]:
        """
        Fetches all historical test entries (review logs) for a specific word,
        ordered chronologically by reviewed_at ASC.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM review_logs
                WHERE word_id = ?
                ORDER BY reviewed_at ASC, id ASC
            """, (word_id,))
            rows = cursor.fetchall()
            return [ReviewLog.from_row(dict(r)) for r in rows]

    def recalculate_word_from_logs(self, word_id: int, now: Optional[datetime] = None) -> Optional[Word]:
        """
        Re-computes a card's current memory stability, difficulty, retrievability,
        and next interval by evaluating all test entries through the universal formula.
        Updates the word record in the database and returns it.
        """
        word = self.get_word_by_id(word_id)
        if not word:
            return None
        logs = self.get_word_review_logs(word_id)
        if not logs:
            return word

        from vocab.srs import SRSEngine
        updated_word, _ = SRSEngine.calculate_from_review_logs(word, logs, now=now)
        self.update_word(updated_word)
        return updated_word

    def check_and_update_mastery(self, word_id: int) -> Optional[Word]:
        """
        Checks if the word meets the permanent mastery / retirement criteria.
        If eligible, updates the word's state to 'mastered' in the database and returns the updated Word.
        Otherwise returns None.
        """
        word = self.get_word_by_id(word_id)
        if not word:
            return None
        if word.state == CardState.MASTERED.value:
            return word

        from vocab.srs import SRSEngine
        recent_logs = self.get_word_review_logs(word_id)
        if SRSEngine.is_mastery_eligible(word, recent_logs=recent_logs):
            word.state = CardState.MASTERED.value
            self.update_word(word)
            return word
        return None

    def set_word_mastery(self, word_id: int, mastered: bool) -> Optional[Word]:
        """
        Manually marks a word as mastered (retired from reviews) or reactivates it back to review.
        """
        word = self.get_word_by_id(word_id)
        if not word:
            return None

        if mastered:
            word.state = CardState.MASTERED.value
        else:
            # Reactivate to review (or new if reps == 0)
            word.state = CardState.REVIEW.value if word.reps > 0 else CardState.NEW.value
            # Set due date to now so it is immediately eligible for review
            word.due_date = datetime.now(timezone.utc).isoformat()

        self.update_word(word)
        return word

    def sync_all_word_states(self, now: Optional[datetime] = None) -> int:
        """
        Synchronizes all words' SRS states, steps, stability, and intervals
        with their historical review logs. If a word has no review logs, ensures
        its state is correctly synchronized as 'new'.
        Returns the number of words updated.
        """
        words = self.get_words(limit=10000)
        updated_count = 0
        from vocab.srs import SRSEngine

        for w in words:
            if w.id is None:
                continue
            logs = self.get_word_review_logs(w.id)
            if logs:
                orig_state = w.state
                orig_step = w.step
                orig_reps = w.reps
                orig_lapses = w.lapses
                orig_stability = w.stability

                recalc, _ = SRSEngine.calculate_from_review_logs(w, logs, now=now)
                # If word was manually marked as mastered, preserve its mastered state
                if orig_state == CardState.MASTERED.value:
                    recalc.state = CardState.MASTERED.value

                if (
                    recalc.state != orig_state
                    or recalc.step != orig_step
                    or recalc.reps != orig_reps
                    or recalc.lapses != orig_lapses
                    or recalc.due_date != w.due_date
                    or recalc.interval_days != w.interval_days
                    or recalc.ease_factor != w.ease_factor
                    or abs(recalc.stability - orig_stability) > 0.01
                    or abs(recalc.avg_thought_time - w.avg_thought_time) > 0.01
                    or abs(recalc.last_thought_time - w.last_thought_time) > 0.01
                ):
                    self.update_word(recalc)
                    updated_count += 1
            else:
                if w.state == CardState.MASTERED.value:
                    continue
                if w.state != CardState.NEW.value or w.step != 0 or w.reps != 0:
                    w.state = CardState.NEW.value
                    w.step = 0
                    w.reps = 0
                    self.update_word(w)
                    updated_count += 1

        return updated_count

    def get_stats_summary(
        self,
        group_id: Optional[int] = None,
        now: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Computes comprehensive learning and retention metrics."""
        now = now or datetime.now(timezone.utc)
        now_iso = now.isoformat()

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Word state counts
            state_query = "SELECT state, COUNT(*) as cnt FROM words"
            params: List[Any] = []
            if group_id is not None:
                state_query += " WHERE group_id = ?"
                params.append(group_id)
            state_query += " GROUP BY state"
            cursor.execute(state_query, params)
            state_counts = {r["state"]: r["cnt"] for r in cursor.fetchall()}

            # Due count
            due_query = "SELECT COUNT(*) as cnt FROM words WHERE state != 'mastered' AND (state = 'new' OR due_date <= ?)"
            due_params: List[Any] = [now_iso]
            if group_id is not None:
                due_query += " AND group_id = ?"
                due_params.append(group_id)
            cursor.execute(due_query, due_params)
            due_count = cursor.fetchone()["cnt"]

            # Total words
            total_words = sum(state_counts.values())

            # Review log stats (last 7 days)
            seven_days_ago = (now - timedelta(days=7)).isoformat()
            log_query = """
                SELECT rl.grade, COUNT(*) as cnt
                FROM review_logs rl
                JOIN words w ON rl.word_id = w.id
                WHERE rl.reviewed_at >= ? AND rl.review_mode NOT IN ('quiz', 'introduction')
            """
            log_params: List[Any] = [seven_days_ago]
            if group_id is not None:
                log_query += " AND w.group_id = ?"
                log_params.append(group_id)
            log_query += " GROUP BY rl.grade"
            cursor.execute(log_query, log_params)

            recent_grades = {r["grade"]: r["cnt"] for r in cursor.fetchall()}
            total_recent_reviews = sum(recent_grades.values())
            recent_success = sum(recent_grades.get(int(g), 0) for g in (SRSGrade.HARD, SRSGrade.GOOD, SRSGrade.EASY))
            retention_rate = (recent_success / total_recent_reviews * 100.0) if total_recent_reviews > 0 else 0.0

            all_reviews_query = """
                SELECT COUNT(*) AS cnt
                FROM review_logs rl
                JOIN words w ON rl.word_id = w.id
                WHERE rl.review_mode NOT IN ('quiz', 'introduction')
            """
            all_reviews_params: List[Any] = []
            if group_id is not None:
                all_reviews_query += " AND w.group_id = ?"
                all_reviews_params.append(group_id)
            cursor.execute(all_reviews_query, all_reviews_params)
            total_review_attempts = cursor.fetchone()["cnt"]

            # Daily activity streak
            cursor.execute("SELECT DISTINCT DATE(reviewed_at) as review_date FROM review_logs ORDER BY review_date DESC")
            active_dates = [r["review_date"] for r in cursor.fetchall()]
            streak = self._calculate_streak(active_dates)

            # Maturity levels:
            # New: state == 'new'
            # Learning: state in ('learning', 'relearning')
            # Young: state == 'review' and interval_days < 21
            # Mature: state == 'review' and interval_days >= 21
            # Mastered: state == 'mastered'
            maturity_query = """
                SELECT
                    SUM(CASE WHEN state = 'new' THEN 1 ELSE 0 END) AS count_new,
                    SUM(CASE WHEN state IN ('learning', 'relearning') THEN 1 ELSE 0 END) AS count_learning,
                    SUM(CASE WHEN state = 'review' AND interval_days < 21 THEN 1 ELSE 0 END) AS count_young,
                    SUM(CASE WHEN state = 'review' AND interval_days >= 21 THEN 1 ELSE 0 END) AS count_mature,
                    SUM(CASE WHEN state = 'mastered' THEN 1 ELSE 0 END) AS count_mastered
                FROM words
            """
            m_params: List[Any] = []
            if group_id is not None:
                maturity_query += " WHERE group_id = ?"
                m_params.append(group_id)
            cursor.execute(maturity_query, m_params)
            m_row = cursor.fetchone()

            next_session = self.get_recommended_next_session(group_id=group_id, now=now)

            return {
                "total_words": total_words,
                "due_count": due_count,
                "state_counts": state_counts,
                "new_count": m_row["count_new"] or 0,
                "learning_count": m_row["count_learning"] or 0,
                "young_count": m_row["count_young"] or 0,
                "mature_count": m_row["count_mature"] or 0,
                "mastered_count": m_row["count_mastered"] or 0,
                "total_recent_reviews": total_recent_reviews,
                "total_review_attempts": total_review_attempts,
                "retention_rate": round(retention_rate, 1),
                "streak_days": streak,
                "next_session": next_session,
            }

    def get_recommended_next_session(
        self,
        group_id: Optional[int] = None,
        now: Optional[datetime] = None,
        target_capacity: Optional[int] = None,
        target_capacity_ratio: float = 0.80
    ) -> Optional[Dict[str, Any]]:
        """
        Calculates the optimal next session time even when cards are currently ready.
        Identifies the future time when due words accumulate to a large amount of the
        brain capacity (default ~80% of adaptive limit), ensuring minimal placeholders
        and avoiding sub-optimal, fragmented 1-word review sessions.
        """
        now = now or datetime.now(timezone.utc)
        now_iso = now.isoformat()

        max_capacity = self.get_adaptive_capacity_limit(group_id=group_id)
        if target_capacity is None:
            target_capacity = max(40, int(round(max_capacity * target_capacity_ratio)))

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 1. Currently due words (state != 'mastered' AND (state == 'new' OR due_date <= now))
            due_query = """
                SELECT w.*, g.name AS group_name
                FROM words w
                JOIN groups g ON w.group_id = g.id
                WHERE w.state != 'mastered' AND (w.state = 'new' OR w.due_date <= ?)
            """
            due_params: List[Any] = [now_iso]
            if group_id is not None:
                due_query += " AND w.group_id = ?"
                due_params.append(group_id)
            due_query += " ORDER BY w.due_date ASC"

            cursor.execute(due_query, due_params)
            currently_due = [Word.from_row(dict(r)) for r in cursor.fetchall()]

            # 2. Upcoming words with future due dates (excluding mastered)
            upcoming_query = """
                SELECT w.*, g.name AS group_name
                FROM words w
                JOIN groups g ON w.group_id = g.id
                WHERE w.state NOT IN ('new', 'mastered') AND w.due_date > ?
            """
            upcoming_params: List[Any] = [now_iso]
            if group_id is not None:
                upcoming_query += " AND w.group_id = ?"
                upcoming_params.append(group_id)
            upcoming_query += " ORDER BY w.due_date ASC"

            cursor.execute(upcoming_query, upcoming_params)
            upcoming = [Word.from_row(dict(r)) for r in cursor.fetchall()]

        if not currently_due and not upcoming:
            return None

        current_due_cap = sum(w.brain_capacity for w in currently_due)
        current_due_count = len(currently_due)

        # If currently due cards already satisfy the large capacity threshold:
        if current_due_cap >= target_capacity:
            return {
                "recommended_time": now,
                "is_optimal_now": True,
                "current_due_count": current_due_count,
                "current_due_capacity": current_due_cap,
                "card_count": current_due_count,
                "accumulated_capacity": current_due_cap,
                "target_capacity": target_capacity,
                "max_capacity": max_capacity,
                "short_label": "Optimal now",
                "full_label": f"Optimal now ({current_due_count} cards ready, ~{current_due_cap}/{max_capacity} cap)",
                "time_until_seconds": 0.0,
            }

        # Otherwise, currently due cards alone are sub-optimal (e.g., only 1 card or small capacity).
        # We accumulate upcoming future cards until reaching target_capacity (minimal placeholders).
        cum_cap = current_due_cap
        selected_count = current_due_count
        milestone_time: Optional[datetime] = None

        for w in upcoming:
            cum_cap += w.brain_capacity
            selected_count += 1
            try:
                dt = datetime.fromisoformat(w.due_date.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                milestone_time = dt
            except Exception:
                pass

            if cum_cap >= target_capacity:
                break

        # Cluster smoothing: if subsequent cards mature within 10 minutes of milestone_time
        # and don't push cum_cap past max_capacity, include them in the recommended batch
        if milestone_time is not None:
            milestone_idx = selected_count - current_due_count
            for w in upcoming[milestone_idx:]:
                if cum_cap + w.brain_capacity > max_capacity:
                    break
                try:
                    dt = datetime.fromisoformat(w.due_date.replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    if (dt - milestone_time).total_seconds() <= 600.0:
                        cum_cap += w.brain_capacity
                        selected_count += 1
                        milestone_time = dt
                    else:
                        break
                except Exception:
                    break

        if milestone_time is None:
            # All available cards in deck are already due, but total deck capacity is smaller than target
            return {
                "recommended_time": now,
                "is_optimal_now": True,
                "current_due_count": current_due_count,
                "current_due_capacity": current_due_cap,
                "card_count": current_due_count,
                "accumulated_capacity": current_due_cap,
                "target_capacity": target_capacity,
                "max_capacity": max_capacity,
                "short_label": "Ready now",
                "full_label": f"Ready now ({current_due_count} cards, ~{current_due_cap}/{max_capacity} cap)",
                "time_until_seconds": 0.0,
            }

        short_label, full_label = self._format_recommended_session_time(milestone_time, now=now)

        return {
            "recommended_time": milestone_time,
            "is_optimal_now": False,
            "current_due_count": current_due_count,
            "current_due_capacity": current_due_cap,
            "card_count": selected_count,
            "accumulated_capacity": cum_cap,
            "target_capacity": target_capacity,
            "max_capacity": max_capacity,
            "short_label": short_label,
            "full_label": full_label,
            "time_until_seconds": max(0.0, (milestone_time - now).total_seconds()),
        }

    @staticmethod
    def _format_recommended_session_time(rec_time: datetime, now: datetime) -> Tuple[str, str]:
        diff_sec = (rec_time - now).total_seconds()
        local_rec = rec_time.astimezone()
        local_now = now.astimezone()

        time_part = local_rec.strftime("%I:%M %p").lstrip("0")

        if diff_sec <= 0:
            return "Ready now", "Ready now"

        if diff_sec < 60:
            return "in <1m", f"Today {time_part} (in <1m)"

        if diff_sec < 3600:
            minutes = max(1, int(round(diff_sec / 60.0)))
            return f"in {minutes}m", f"Today {time_part} (in {minutes}m)"

        hours = round(diff_sec / 3600.0, 1)
        h_str = f"{int(hours)}h" if hours.is_integer() else f"{hours}h"

        if local_rec.date() == local_now.date():
            return f"Today {time_part}", f"Today {time_part} (in {h_str})"

        if local_rec.date() == (local_now + timedelta(days=1)).date():
            return f"Tomorrow {time_part}", f"Tomorrow {time_part} (in {h_str})"

        days = round(diff_sec / 86400.0, 1)
        d_str = f"{int(days)}d" if days.is_integer() else f"{days}d"

        if (local_rec.date() - local_now.date()).days < 7:
            day_name = local_rec.strftime("%a")
            return f"{day_name} {time_part}", f"{day_name} {time_part} (in {d_str})"

        date_str = local_rec.strftime("%b %d")
        return f"{date_str} {time_part}", f"{date_str} {time_part} (in {d_str})"

    def _calculate_streak(self, active_dates: List[str]) -> int:
        if not active_dates:
            return 0
        today = datetime.now(timezone.utc).date()
        today_str = today.isoformat()
        yesterday_str = (today - timedelta(days=1)).isoformat()

        if active_dates[0] != today_str and active_dates[0] != yesterday_str:
            return 0

        current_check = datetime.fromisoformat(active_dates[0]).date()
        streak = 1
        for next_date_str in active_dates[1:]:
            next_date = datetime.fromisoformat(next_date_str).date()
            if (current_check - next_date).days == 1:
                streak += 1
                current_check = next_date
            elif (current_check - next_date).days == 0:
                continue
            else:
                break
        return streak

    def get_due_forecast(self, group_id: Optional[int] = None, days_ahead: int = 7) -> Dict[str, int]:
        """Returns forecast of how many cards will be due in the next N days."""
        now = datetime.now(timezone.utc)
        forecast = {}
        with self.get_connection() as conn:
            cursor = conn.cursor()
            for i in range(days_ahead + 1):
                day_target = (now + timedelta(days=i)).date()
                day_start = datetime(day_target.year, day_target.month, day_target.day, 0, 0, 0, tzinfo=timezone.utc).isoformat()
                day_end = datetime(day_target.year, day_target.month, day_target.day, 23, 59, 59, tzinfo=timezone.utc).isoformat()

                if i == 0:
                    # Due today includes already overdue cards and new cards
                    query = "SELECT COUNT(*) as cnt FROM words WHERE state != 'mastered' AND (state = 'new' OR due_date <= ?)"
                    params: List[Any] = [day_end]
                else:
                    query = "SELECT COUNT(*) as cnt FROM words WHERE due_date >= ? AND due_date <= ? AND state NOT IN ('new', 'mastered')"
                    params = [day_start, day_end]

                if group_id is not None:
                    query += " AND group_id = ?"
                    params.append(group_id)

                cursor.execute(query, params)
                count = cursor.fetchone()["cnt"]
                day_label = "Today" if i == 0 else f"+{i}d"
                forecast[day_label] = count

        return forecast

    # --- Circadian & Thought Time Analytics ---

    def get_hourly_activity(self, group_id: Optional[int] = None, days: int = 30) -> List[Dict[str, Any]]:
        """Returns 24-hour activity distribution and performance metrics."""
        now = datetime.now()
        start_date = (now - timedelta(days=days)).isoformat()
        max_tt = self.get_max_thought_time_threshold()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = """
                SELECT
                    rl.hour_of_day,
                    COUNT(*) as reviews,
                    SUM(rl.elapsed_seconds) as total_active_seconds,
                    AVG(CASE WHEN rl.thought_time_seconds > 0 AND rl.thought_time_seconds <= ? THEN rl.thought_time_seconds ELSE NULL END) as avg_thought_time,
                    SUM(CASE WHEN rl.grade IN (2, 3, 4) THEN 1 ELSE 0 END) as success_count,
                    SUM(CASE WHEN rl.card_state IN ('new', 'learning', 'relearning') OR (rl.card_state IS NULL AND rl.scheduled_days <= 1.0) THEN 1 ELSE 0 END) as new_learning_count,
                    SUM(CASE WHEN (rl.card_state IN ('new', 'learning', 'relearning') OR (rl.card_state IS NULL AND rl.scheduled_days <= 1.0)) AND rl.grade IN (2, 3, 4) THEN 1 ELSE 0 END) as new_learning_success,
                    SUM(CASE WHEN rl.card_state = 'review' OR (rl.card_state IS NULL AND rl.scheduled_days > 1.0) THEN 1 ELSE 0 END) as review_count,
                    SUM(CASE WHEN (rl.card_state = 'review' OR (rl.card_state IS NULL AND rl.scheduled_days > 1.0)) AND rl.grade IN (2, 3, 4) THEN 1 ELSE 0 END) as review_success
                FROM review_logs rl
                JOIN words w ON rl.word_id = w.id
                WHERE rl.reviewed_at >= ? AND rl.review_mode NOT IN ('quiz', 'introduction')
            """
            params: List[Any] = [max_tt, start_date]
            if group_id is not None:
                query += " AND w.group_id = ?"
                params.append(group_id)
            query += " GROUP BY rl.hour_of_day"

            cursor.execute(query, params)
            rows = {r["hour_of_day"]: dict(r) for r in cursor.fetchall()}

            result = []
            for h in range(24):
                if h in rows:
                    r = rows[h]
                    revs = r["reviews"]
                    succ = r["success_count"]
                    retention = (succ / revs * 100.0) if revs > 0 else 0.0
                    avg_tt = round(r["avg_thought_time"] or 0.0, 2)
                    sec = round(r["total_active_seconds"] or 0.0, 1)
                    nl_count = r.get("new_learning_count") or 0
                    nl_succ = r.get("new_learning_success") or 0
                    rv_count = r.get("review_count") or 0
                    rv_succ = r.get("review_success") or 0
                    rv_ret = round((rv_succ / rv_count * 100.0), 1) if rv_count > 0 else None
                    result.append({
                        "hour": h,
                        "reviews": revs,
                        "active_seconds": sec,
                        "avg_thought_time": avg_tt,
                        "retention_rate": round(retention, 1),
                        "new_learning_count": nl_count,
                        "new_learning_success": nl_succ,
                        "review_count": rv_count,
                        "review_success": rv_succ,
                        "review_retention_rate": rv_ret
                    })
                else:
                    result.append({
                        "hour": h,
                        "reviews": 0,
                        "active_seconds": 0.0,
                        "avg_thought_time": 0.0,
                        "retention_rate": 0.0,
                        "new_learning_count": 0,
                        "new_learning_success": 0,
                        "review_count": 0,
                        "review_success": 0,
                        "review_retention_rate": None
                    })
            return result

    def get_circadian_periods_summary(self, group_id: Optional[int] = None, days: int = 30) -> List[Dict[str, Any]]:
        """
        Aggregates learning metrics into circadian day periods:
        - Morning Focus (06:00 - 11:59)
        - Afternoon Flow (12:00 - 17:59)
        - Evening Consolidation (18:00 - 21:59)
        - Night Owl / Late Review (22:00 - 05:59)

        Cognitive Status Analysis:
        Differentiates between natural acquisition retrieval dips (newly learned words)
        and true cognitive fatigue / tiredness (poor recall on established review cards).
        """
        hourly = self.get_hourly_activity(group_id=group_id, days=days)
        periods = [
            {"name": "Morning Focus", "hours": list(range(6, 12)), "icon": "☼"},
            {"name": "Afternoon Flow", "hours": list(range(12, 18)), "icon": "☀"},
            {"name": "Evening Consolidation", "hours": list(range(18, 22)), "icon": "◆"},
            {"name": "Night Owl / Late", "hours": [22, 23, 0, 1, 2, 3, 4, 5], "icon": "☾"},
        ]

        results = []
        for p in periods:
            matching = [h for h in hourly if h["hour"] in p["hours"]]
            total_revs = sum(m["reviews"] for m in matching)
            total_sec = sum(m["active_seconds"] for m in matching)
            thought_times = [m["avg_thought_time"] for m in matching if m["avg_thought_time"] > 0]
            avg_tt = round(sum(thought_times) / len(thought_times), 2) if thought_times else 0.0

            total_succ = sum(m["reviews"] * (m["retention_rate"] / 100.0) for m in matching)
            ret_rate = round((total_succ / total_revs * 100.0), 1) if total_revs > 0 else 0.0

            new_learning_revs = sum(m.get("new_learning_count", 0) for m in matching)
            new_learning_succ = sum(m.get("new_learning_success", 0) for m in matching)
            new_ret_rate = round((new_learning_succ / new_learning_revs * 100.0), 1) if new_learning_revs > 0 else None

            review_revs = sum(m.get("review_count", 0) for m in matching)
            review_succ = sum(m.get("review_success", 0) for m in matching)
            review_ret_rate = round((review_succ / review_revs * 100.0), 1) if review_revs > 0 else None

            # Describe observations without diagnosing fatigue or focus.
            state_label = "[dim]No activity[/dim]" if not total_revs else (
                "[dim]Small sample[/dim]" if total_revs < 20 else "[cyan]Observed activity[/cyan]"
            )

            results.append({
                "name": p["name"],
                "icon": p["icon"],
                "reviews": total_revs,
                "new_learning_revs": new_learning_revs,
                "review_revs": review_revs,
                "active_minutes": round(total_sec / 60.0, 1),
                "avg_thought_time": avg_tt,
                "retention_rate": ret_rate,
                "review_retention_rate": review_ret_rate,
                "new_retention_rate": new_ret_rate,
                "state_label": state_label
            })
        return results

    def get_max_thought_time_threshold(self) -> float:
        """Returns the configured max valid thought time in seconds (default: 30.0)."""
        val = self.get_setting("max_thought_time")
        if val is not None:
            try:
                f_val = float(val)
                if f_val > 0:
                    return f_val
            except ValueError:
                pass
        return MAX_VALID_THOUGHT_TIME

    def cleanup_thought_time_outliers(self, threshold: Optional[float] = None) -> Dict[str, Any]:
        """
        Cleans up thought time outliers (e.g. user distracted by errands) from review logs and words.
        - Sets thought_time_seconds to 0.0 for review logs where thought_time_seconds > threshold
          (preserving elapsed_seconds for active study duration tracking).
        - Recalculates avg_thought_time and last_thought_time for affected words based on valid logs.
        Returns a summary dict of cleaned review logs and words updated.
        """
        max_tt = threshold if threshold is not None else self.get_max_thought_time_threshold()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Find affected review logs
            cursor.execute("""
                SELECT id, word_id, thought_time_seconds
                FROM review_logs
                WHERE thought_time_seconds > ?
            """, (max_tt,))
            outlier_rows = cursor.fetchall()

            # Also find any words whose avg_thought_time > max_tt
            cursor.execute("""
                SELECT id FROM words WHERE avg_thought_time > ?
            """, (max_tt,))
            word_outlier_rows = cursor.fetchall()

            if not outlier_rows and not word_outlier_rows:
                return {
                    "cleaned_logs_count": 0,
                    "updated_words_count": 0,
                    "affected_word_ids": []
                }

            cleaned_logs_count = len(outlier_rows)
            affected_word_ids = set(r["word_id"] for r in outlier_rows)
            for r in word_outlier_rows:
                affected_word_ids.add(r["id"])

            # Clean the review logs
            cursor.execute("""
                UPDATE review_logs
                SET thought_time_seconds = 0.0
                WHERE thought_time_seconds > ?
            """, (max_tt,))

            # Recalculate avg_thought_time and last_thought_time for affected words
            updated_words_count = 0
            for wid in sorted(affected_word_ids):
                cursor.execute("""
                    SELECT thought_time_seconds, reviewed_at
                    FROM review_logs
                    WHERE word_id = ? AND thought_time_seconds > 0 AND thought_time_seconds <= ?
                    ORDER BY reviewed_at ASC
                """, (wid, max_tt))
                valid_logs = cursor.fetchall()
                if valid_logs:
                    times = [float(l["thought_time_seconds"]) for l in valid_logs]
                    avg_tt = times[0]
                    for t in times[1:]:
                        avg_tt = 0.7 * avg_tt + 0.3 * t
                    avg_tt = round(avg_tt, 2)
                    last_tt = round(times[-1], 2)
                else:
                    avg_tt = 0.0
                    last_tt = 0.0

                cursor.execute("""
                    UPDATE words
                    SET avg_thought_time = ?, last_thought_time = ?
                    WHERE id = ?
                """, (avg_tt, last_tt, wid))
                updated_words_count += 1

            conn.commit()
            return {
                "cleaned_logs_count": cleaned_logs_count,
                "updated_words_count": updated_words_count,
                "affected_word_ids": sorted(list(affected_word_ids))
            }

    def get_latency_analytics(self, group_id: Optional[int] = None) -> Dict[str, Any]:
        """Calculates thought latency distribution and identifies hesitant cards."""
        max_tt = self.get_max_thought_time_threshold()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = """
                SELECT
                    COUNT(*) as total,
                    AVG(CASE WHEN thought_time_seconds > 0 AND thought_time_seconds <= ? THEN thought_time_seconds ELSE NULL END) as overall_avg,
                    SUM(CASE WHEN thought_time_seconds > 0 AND thought_time_seconds <= 3.0 THEN 1 ELSE 0 END) as count_fluent,
                    SUM(CASE WHEN thought_time_seconds > 3.0 AND thought_time_seconds <= 7.0 THEN 1 ELSE 0 END) as count_steady,
                    SUM(CASE WHEN thought_time_seconds > 7.0 AND thought_time_seconds <= ? THEN 1 ELSE 0 END) as count_hesitant,
                    SUM(CASE WHEN thought_time_seconds > ? THEN 1 ELSE 0 END) as count_outliers
                FROM review_logs rl
                JOIN words w ON rl.word_id = w.id
                WHERE rl.thought_time_seconds > 0
            """
            params: List[Any] = [max_tt, max_tt, max_tt]
            if group_id is not None:
                query += " AND w.group_id = ?"
                params.append(group_id)

            cursor.execute(query, params)
            dist_row = cursor.fetchone()

            w_query = """
                SELECT w.*, g.name AS group_name
                FROM words w
                JOIN groups g ON w.group_id = g.id
                WHERE w.avg_thought_time > 0 AND w.avg_thought_time <= ?
            """
            w_params: List[Any] = [max_tt]
            if group_id is not None:
                w_query += " AND w.group_id = ?"
                w_params.append(group_id)
            w_query += " ORDER BY w.avg_thought_time DESC LIMIT 5"

            cursor.execute(w_query, w_params)
            hesitant_words = [Word.from_row(dict(r)) for r in cursor.fetchall()]

            c_fluent = dist_row["count_fluent"] or 0
            c_steady = dist_row["count_steady"] or 0
            c_hesitant = dist_row["count_hesitant"] or 0
            c_outliers = dist_row["count_outliers"] or 0
            valid_timed = c_fluent + c_steady + c_hesitant

            return {
                "total_timed_reviews": valid_timed,
                "overall_avg_thought_time": round(dist_row["overall_avg"] or 0.0, 2),
                "count_fluent": c_fluent,
                "count_steady": c_steady,
                "count_hesitant": c_hesitant,
                "count_outliers": c_outliers,
                "max_thought_time_threshold": max_tt,
                "hesitant_words": hesitant_words,
            }

    # --- Settings Operations ---

    def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Fetches a setting value from settings table."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        """Saves or updates a setting value in settings table."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, str(value))
            )
            conn.commit()

    # --- Vocabulary Proficiency Test Operations ---

    def log_test_result(
        self,
        test_type: str,
        total_questions: int,
        correct_count: int,
        score_pct: float,
        cefr_level: str,
        estimated_vocab_size: int,
        avg_response_time: float = 0.0,
        details_json: str = "",
        tested_at: Optional[str] = None
    ) -> int:
        """Logs the outcome of a vocabulary proficiency or benchmark test."""
        tested_at = tested_at or datetime.now(timezone.utc).isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO vocab_tests (
                    test_type, total_questions, correct_count, score_pct,
                    cefr_level, estimated_vocab_size, avg_response_time,
                    details_json, tested_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    test_type,
                    total_questions,
                    correct_count,
                    round(score_pct, 2),
                    cefr_level,
                    int(estimated_vocab_size),
                    round(avg_response_time, 2),
                    details_json,
                    tested_at
                )
            )
            conn.commit()
            return cursor.lastrowid

    def get_test_history(
        self,
        limit: int = 20,
        test_type: Optional[str] = None
    ) -> List[VocabTestResult]:
        """Retrieves past vocabulary proficiency test records."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM vocab_tests"
            params: List[Any] = []
            if test_type:
                query += " WHERE test_type = ?"
                params.append(test_type)
            query += " ORDER BY tested_at DESC, id DESC LIMIT ?"
            params.append(limit)
            cursor.execute(query, params)
            return [VocabTestResult.from_row(dict(r)) for r in cursor.fetchall()]

    def get_test_analytics(self) -> Dict[str, Any]:
        """Calculates test metrics, best performance, and level progression over time."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as cnt FROM vocab_tests")
            count_row = cursor.fetchone()
            total_tests = count_row["cnt"] if count_row else 0
            if total_tests == 0:
                return {
                    "total_tests": 0,
                    "avg_score": 0.0,
                    "best_score": 0.0,
                    "avg_response_time": 0.0,
                    "latest_test": None,
                    "latest_benchmark": None,
                    "progression": []
                }

            # Certified/reliable benchmarks: tests with at least 5 questions
            cursor.execute(
                "SELECT COUNT(*) as cnt, AVG(score_pct) as avg_score, MAX(score_pct) as best_score, AVG(avg_response_time) as avg_time FROM vocab_tests WHERE total_questions >= 5"
            )
            certified_summary = cursor.fetchone()

            if certified_summary and certified_summary["cnt"] > 0:
                avg_score = round(certified_summary["avg_score"] or 0.0, 1)
                best_score = round(certified_summary["best_score"] or 0.0, 1)
                avg_time = round(certified_summary["avg_time"] or 0.0, 2)
            else:
                cursor.execute(
                    "SELECT AVG(score_pct) as avg_score, MAX(score_pct) as best_score, AVG(avg_response_time) as avg_time FROM vocab_tests"
                )
                fallback_summary = cursor.fetchone()
                avg_score = round(fallback_summary["avg_score"] or 0.0, 1) if fallback_summary else 0.0
                best_score = round(fallback_summary["best_score"] or 0.0, 1) if fallback_summary else 0.0
                avg_time = round(fallback_summary["avg_time"] or 0.0, 2) if fallback_summary else 0.0

            # Latest certified benchmark (>= 5 questions)
            cursor.execute(
                "SELECT * FROM vocab_tests WHERE total_questions >= 5 ORDER BY tested_at DESC, id DESC LIMIT 1"
            )
            bench_row = cursor.fetchone()
            latest_benchmark = VocabTestResult.from_row(dict(bench_row)) if bench_row else None

            # Latest test of any length
            cursor.execute("SELECT * FROM vocab_tests ORDER BY tested_at DESC, id DESC LIMIT 1")
            latest_row = cursor.fetchone()
            latest_test = VocabTestResult.from_row(dict(latest_row)) if latest_row else None

            cursor.execute(
                "SELECT id, test_type, total_questions, correct_count, score_pct, cefr_level, estimated_vocab_size, avg_response_time, tested_at FROM vocab_tests ORDER BY tested_at ASC, id ASC"
            )
            progression = [dict(r) for r in cursor.fetchall()]

            return {
                "total_tests": total_tests,
                "avg_score": avg_score,
                "best_score": best_score,
                "avg_response_time": avg_time,
                "latest_test": latest_test,
                "latest_benchmark": latest_benchmark or latest_test,
                "progression": progression
            }

    def delete_test_history(self, test_id: Optional[int] = None) -> int:
        """Deletes a specific test result or clears all test history."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if test_id is not None:
                cursor.execute("DELETE FROM vocab_tests WHERE id = ?", (test_id,))
            else:
                cursor.execute("DELETE FROM vocab_tests")
            conn.commit()
            return cursor.rowcount


