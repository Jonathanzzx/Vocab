"""Session queue and workload heuristics; scheduling is in vocab.scheduler."""
from __future__ import annotations
import math
import random
from datetime import datetime, timedelta, timezone
from typing import Dict, Tuple, List, Optional, Sequence, Set, Any
from vocab.models import Word, SRSGrade, CardState
from vocab.scheduler import (
    SRSEngine, UniversalSRSFormula, LEARNING_STEPS_MINUTES,
    MIN_DIFFICULTY, MAX_DIFFICULTY, DEFAULT_DIFFICULTY,
    MIN_EASE_FACTOR, MAX_EASE_FACTOR, MAX_VALID_THOUGHT_TIME,
    TARGET_RETENTION, is_valid_thought_time,
)


class RecurrentSessionQueue:
    """Mix due/new cards and separate repeated items using queue heuristics.

    Shuffling reduces repeated neighboring pairs; it does not establish
    category interleaving benefits or eliminate serial-position effects.
    """
    _recent_session_sequences: List[List[Any]] = []
    MAX_RECENT_SEQUENCES: int = 5

    def __init__(
        self,
        words: List[Word],
        reinsert_offset: int = 3,
        enable_shuffling: bool = True,
        enable_interleaving: bool = True,
        previous_sequence: Optional[Sequence[Word | int | str]] = None,
        avoid_pairs: Optional[Set[Tuple[Any, Any]]] = None
    ):
        self.reinsert_offset = reinsert_offset
        self.enable_shuffling = enable_shuffling
        self.recurrent_counts: Dict[int, int] = {}  # word_id -> times re-queued
        self.completed_word_ids: set[int] = set()
        self.completed_words: Dict[Any, Word] = {}
        self._last_popped_card: Optional[Word] = None
        self._session_seen_pairs: Set[Tuple[Any, Any]] = set()

        forward_penalized: Set[Tuple[Any, Any]] = set()
        undirected_penalized: Set[frozenset[Any]] = set()

        if enable_shuffling:
            # 1. Collect pairs from explicitly provided previous sequence
            if previous_sequence:
                f_pairs, u_pairs = self._extract_pairs(previous_sequence)
                forward_penalized.update(f_pairs)
                undirected_penalized.update(u_pairs)
            else:
                # Fallback to recent in-memory session history if no previous_sequence is provided
                for hist_seq in self._recent_session_sequences[-2:]:
                    f_pairs, u_pairs = self._extract_pairs(hist_seq)
                    forward_penalized.update(f_pairs)
                    undirected_penalized.update(u_pairs)

            # 2. Collect pairs from explicit avoid_pairs
            if avoid_pairs:
                for p in avoid_pairs:
                    if len(p) == 2:
                        k1 = self._get_card_key(p[0])
                        k2 = self._get_card_key(p[1])
                        forward_penalized.add((k1, k2))
                        undirected_penalized.add(frozenset({k1, k2}))

        # Build initial queue with priority preservation, interleaving, and anti-pairing
        self.queue: List[Word] = self._prepare_queue(
            words,
            shuffle_within_tiers=enable_shuffling,
            interleave_categories=enable_interleaving,
            forward_penalized=forward_penalized if enable_shuffling else None,
            undirected_penalized=undirected_penalized if enable_shuffling else None
        )
        self.total_initial = len(self.queue)

        # Record this sequence in class history
        if enable_shuffling and self.queue:
            seq_keys = [self._get_card_key(w) for w in self.queue]
            self._record_session_sequence(seq_keys)

    @classmethod
    def _record_session_sequence(cls, seq_keys: List[Any]) -> None:
        if not seq_keys:
            return
        cls._recent_session_sequences.append(seq_keys)
        if len(cls._recent_session_sequences) > cls.MAX_RECENT_SEQUENCES:
            cls._recent_session_sequences.pop(0)

    @classmethod
    def clear_recent_history(cls) -> None:
        """Clears in-memory sequence history (useful for test isolation)."""
        cls._recent_session_sequences.clear()

    @staticmethod
    def _get_card_key(item: Any) -> Any:
        if isinstance(item, Word):
            return item.id if item.id is not None else item.word
        return item

    @staticmethod
    def is_new_learning_word(word: Word) -> bool:
        """
        Returns True if the card represents new learning material
        (state is 'new' or 'learning', and not a placeholder review card).
        """
        if getattr(word, "is_placeholder", False):
            return False
        return word.state in (CardState.NEW.value, CardState.LEARNING.value)

    @classmethod
    def _alternate_old_and_new(
        cls,
        old_words: List[Word],
        new_words: List[Word],
        prefer_old_first: bool = True
    ) -> List[Word]:
        """
        Interleaves old review/placeholder cards and new learning cards
        so they appear alternately throughout the session without piling up.

        Uses exact integer proportional placement:
        - When counts are equal, produces strict 1:1 alternation (Old, New, Old, New...).
        - When counts are unequal, distributes minority cards uniformly across
          majority cards, preventing clusters of either card type.
        - Preserves relative order and urgency within old cards and within new cards.
        """
        if not old_words:
            return list(new_words)
        if not new_words:
            return list(old_words)

        a_len = len(old_words)
        b_len = len(new_words)

        tagged: List[Tuple[int, int, int, Word]] = []

        if prefer_old_first:
            for i, w in enumerate(old_words):
                time_a = 2 * i * b_len
                tagged.append((time_a, 0, i, w))
            for j, w in enumerate(new_words):
                time_b = (2 * j + 1) * a_len
                tagged.append((time_b, 1, j, w))
        else:
            for j, w in enumerate(new_words):
                time_b = 2 * j * a_len
                tagged.append((time_b, 0, j, w))
            for i, w in enumerate(old_words):
                time_a = (2 * i + 1) * b_len
                tagged.append((time_a, 1, i, w))

        tagged.sort(key=lambda x: (x[0], x[1], x[2]))
        return [x[3] for x in tagged]

    @classmethod
    def _de_bias_alternated_sequence(
        cls,
        cards: List[Word],
        forward_penalized: Optional[Set[Tuple[Any, Any]]] = None,
        undirected_penalized: Optional[Set[frozenset[Any]]] = None
    ) -> List[Word]:
        """
        Resolves adjacent pair collisions in an alternated sequence while preserving
        the alternating structure between old review cards and new learning cards.
        """
        if len(cards) <= 2 or (not forward_penalized and not undirected_penalized):
            return list(cards)

        has_both = (
            any(not cls.is_new_learning_word(w) for w in cards)
            and any(cls.is_new_learning_word(w) for w in cards)
        )
        if not has_both:
            return cls._de_bias_sequence(
                cards,
                forward_penalized=forward_penalized,
                undirected_penalized=undirected_penalized
            )

        f_pen = forward_penalized or set()
        u_pen = undirected_penalized or set()
        res = list(cards)
        n = len(res)

        for i in range(n - 1):
            k1 = cls._get_card_key(res[i])
            k2 = cls._get_card_key(res[i + 1])
            if (k1, k2) in f_pen or frozenset({k1, k2}) in u_pen:
                t_target = cls.is_new_learning_word(res[i + 1])
                for j in range(i + 2, min(n, i + 8)):
                    if cls.is_new_learning_word(res[j]) == t_target:
                        k_cand = cls._get_card_key(res[j])
                        if (k1, k_cand) not in f_pen and frozenset({k1, k_cand}) not in u_pen:
                            k_j_left = cls._get_card_key(res[j - 1]) if j - 1 > i + 1 else None
                            k_j_right = cls._get_card_key(res[j + 1]) if j + 1 < n else None
                            if (not k_j_left or (k_j_left, k2) not in f_pen) and (not k_j_right or (k2, k_j_right) not in f_pen):
                                res[i + 1], res[j] = res[j], res[i + 1]
                                break

        return res

    @classmethod
    def _extract_pairs(
        cls,
        sequence: Sequence[Any]
    ) -> Tuple[Set[Tuple[Any, Any]], Set[frozenset[Any]]]:
        """
        Extracts directed adjacent pairs (c_i, c_{i+1}) and
        undirected adjacent pairs {c_i, c_{i+1}} from a sequence.
        """
        forward_pairs: Set[Tuple[Any, Any]] = set()
        undirected_pairs: Set[frozenset[Any]] = set()
        keys = [cls._get_card_key(x) for x in sequence]
        for i in range(len(keys) - 1):
            k1, k2 = keys[i], keys[i + 1]
            if k1 is not None and k2 is not None and k1 != k2:
                forward_pairs.add((k1, k2))
                undirected_pairs.add(frozenset({k1, k2}))
        return forward_pairs, undirected_pairs

    @classmethod
    def _de_bias_sequence(
        cls,
        cards: List[Word],
        forward_penalized: Optional[Set[Tuple[Any, Any]]] = None,
        undirected_penalized: Optional[Set[frozenset[Any]]] = None,
        cluster_bounds: Optional[List[Tuple[int, int]]] = None,
        max_passes: int = 30
    ) -> List[Word]:
        """
        Actively eliminates repeated pairs of 2 cards and identical sequences
        by performing targeted swaps within cluster/tier bounds.
        """
        if len(cards) <= 1:
            return list(cards)

        forward_penalized = forward_penalized or set()
        undirected_penalized = undirected_penalized or set()

        if not forward_penalized and not undirected_penalized:
            return list(cards)

        res = list(cards)
        n = len(res)

        if cluster_bounds is None:
            cluster_bounds = [(0, n)]

        def pair_cost(w1: Word, w2: Word) -> float:
            k1 = cls._get_card_key(w1)
            k2 = cls._get_card_key(w2)
            c = 0.0
            if (k1, k2) in forward_penalized:
                c += 10.0
            if frozenset({k1, k2}) in undirected_penalized:
                c += 3.0
            return c

        def cluster_cost(seq: List[Word], start: int, end: int) -> float:
            return sum(pair_cost(seq[i], seq[i + 1]) for i in range(start, end - 1))

        for start, end in cluster_bounds:
            c_len = end - start
            if c_len <= 1:
                continue

            if c_len == 2:
                # For pair of 2: if forward collision exists, swap to reverse order
                k0 = cls._get_card_key(res[start])
                k1 = cls._get_card_key(res[start + 1])
                if (k0, k1) in forward_penalized:
                    res[start], res[start + 1] = res[start + 1], res[start]
                continue

            # Multi-card cluster optimization:
            best_cluster = list(res[start:end])
            best_c_cost = cluster_cost(best_cluster, 0, c_len)

            if best_c_cost > 0.0:
                # Try random permutations to find an optimal starting point
                num_restarts = min(30, math.factorial(c_len) if c_len <= 6 else 30)
                for _ in range(num_restarts):
                    candidate = list(best_cluster)
                    random.shuffle(candidate)
                    cost = cluster_cost(candidate, 0, c_len)
                    if cost < best_c_cost:
                        best_cluster = candidate
                        best_c_cost = cost
                        if cost == 0.0:
                            break

            # Greedy local search from best_cluster
            for _ in range(max_passes):
                if best_c_cost == 0.0:
                    break
                improved = False
                for i in range(c_len - 1):
                    if pair_cost(best_cluster[i], best_cluster[i + 1]) > 0:
                        for target in (i + 1, i):
                            for j in range(c_len):
                                if j == target:
                                    continue
                                best_cluster[target], best_cluster[j] = best_cluster[j], best_cluster[target]
                                cost = cluster_cost(best_cluster, 0, c_len)
                                if cost < best_c_cost:
                                    best_c_cost = cost
                                    improved = True
                                    break
                                best_cluster[target], best_cluster[j] = best_cluster[j], best_cluster[target]
                            if improved:
                                break
                    if improved:
                        break
                if not improved:
                    break

            res[start:end] = best_cluster

        return res

    @property
    def remaining_count(self) -> int:
        return len(self.queue)

    @property
    def is_empty(self) -> bool:
        return len(self.queue) == 0

    @property
    def recurrent_active_count(self) -> int:
        """Cards currently in queue that have failed at least once this session."""
        return sum(1 for w in self.queue if self.recurrent_counts.get(w.id or 0, 0) > 0)

    def next_card(self) -> Optional[Word]:
        if not self.queue:
            return None
        card = self.queue.pop(0)
        c_key = self._get_card_key(card)
        if self._last_popped_card is not None:
            last_key = self._get_card_key(self._last_popped_card)
            if last_key is not None and c_key is not None and last_key != c_key:
                self._session_seen_pairs.add((last_key, c_key))
                self._session_seen_pairs.add((c_key, last_key))
        self._last_popped_card = card
        return card

    def shuffle_remaining(self) -> int:
        """
        Shuffles the remaining cards in the queue, preserving alternating
        distribution of old review cards and new learning cards, interleaving tags/categories
        to refresh retrieval cues on demand and avoiding repeating pairs.
        Returns the number of cards shuffled.
        """
        if len(self.queue) <= 1:
            return len(self.queue)

        old_cards = [w for w in self.queue if not self.is_new_learning_word(w)]
        new_cards = [w for w in self.queue if self.is_new_learning_word(w)]

        if old_cards and new_cards:
            random.shuffle(old_cards)
            random.shuffle(new_cards)
            if self.enable_shuffling:
                old_cards = self._interleave_cards(old_cards)
                new_cards = self._interleave_cards(new_cards)
            self.queue = self._alternate_old_and_new(old_cards, new_cards, prefer_old_first=True)
            self.queue = self._de_bias_alternated_sequence(
                self.queue,
                forward_penalized=self._session_seen_pairs
            )
        else:
            random.shuffle(self.queue)
            self.queue = self._interleave_cards(self.queue)
            self.queue = self._de_bias_sequence(
                self.queue,
                forward_penalized=self._session_seen_pairs
            )
        return len(self.queue)

    def add_cards(self, new_words: List[Word], position: str = "end") -> int:
        """
        Dynamically adds newly due words to the active session queue.
        Prevents duplicates by checking existing card IDs.
        Returns the number of cards successfully added.
        """
        existing_ids = {w.id for w in self.queue if w.id is not None}
        to_add = []
        for w in new_words:
            if w.id is not None and w.id not in existing_ids:
                to_add.append(w)
                existing_ids.add(w.id)

        if not to_add:
            return 0

        if len(to_add) > 1:
            random.shuffle(to_add)
            to_add = self._interleave_cards(to_add)
            to_add = self._de_bias_sequence(
                to_add,
                forward_penalized=self._session_seen_pairs
            )

        if position == "front":
            self.queue = to_add + self.queue
        else:
            self.queue.extend(to_add)

        return len(to_add)

    def handle_result(self, word: Word, grade: SRSGrade, thought_time_seconds: float = 0.0) -> bool:
        """
        Handles review result. If AGAIN, HARD in early step, or severe hesitation (>12s)
        in learning, re-inserts into queue for immediate retention consolidation.
        Avoids placing the re-queued card adjacent to recently seen cards in this session,
        and favors candidate positions that alternate card types (Old vs New).
        """
        word_id = word.id or 0

        # Correct but slow recall is not a failure. Repeat missed/Hard items
        # for feedback; queue position is an application policy, not a timed step.
        should_requeue = grade in (SRSGrade.AGAIN, SRSGrade.HARD)

        if should_requeue:
            self.recurrent_counts[word_id] = self.recurrent_counts.get(word_id, 0) + 1
            # Re-insert with desirable spacing gap
            if not self.enable_shuffling:
                insert_pos = min(self.reinsert_offset, len(self.queue))
            elif len(self.queue) <= 2:
                insert_pos = len(self.queue)
            else:
                min_pos = max(2, self.reinsert_offset - 1)
                max_pos = min(len(self.queue), max(min_pos, self.reinsert_offset + 2))
                candidates = list(range(min_pos, max_pos + 1))
                random.shuffle(candidates)

                best_pos = candidates[0]
                best_score = -999999.0
                cur_key = self._get_card_key(word)
                cur_is_new = self.is_new_learning_word(word)

                for pos in candidates:
                    left_w = self.queue[pos - 1] if pos > 0 else None
                    right_w = self.queue[pos] if pos < len(self.queue) else None
                    left_key = self._get_card_key(left_w) if left_w else None
                    right_key = self._get_card_key(right_w) if right_w else None

                    score = 0.0
                    if left_key and (left_key, cur_key) in self._session_seen_pairs:
                        score -= 100.0
                    if right_key and (cur_key, right_key) in self._session_seen_pairs:
                        score -= 100.0

                    # Reward alternating card types (Old vs New) to maintain interleaved rhythm
                    if left_w is not None:
                        score += 5.0 if self.is_new_learning_word(left_w) != cur_is_new else -2.0
                    if right_w is not None:
                        score += 5.0 if self.is_new_learning_word(right_w) != cur_is_new else -2.0

                    if score > best_score:
                        best_score = score
                        best_pos = pos

                insert_pos = best_pos
            self.queue.insert(insert_pos, word)
            return True
        else:
            self.completed_word_ids.add(word_id)
            self.completed_words[self._get_card_key(word)] = word
            return False

    def requeue_card(self, word: Word, custom_offset: Optional[int] = None) -> None:
        """
        Re-queues a card into the active session queue for recall testing.
        Used when introducing new words or reinforcing memory traces.
        """
        word_id = word.id or 0
        self.recurrent_counts[word_id] = self.recurrent_counts.get(word_id, 0) + 1
        offset = custom_offset if custom_offset is not None else self.reinsert_offset
        insert_pos = min(offset, len(self.queue))
        if self.enable_shuffling and len(self.queue) > 2:
            cur_key = self._get_card_key(word)
            cur_is_new = self.is_new_learning_word(word)
            candidates = [p for p in (insert_pos, insert_pos + 1, insert_pos - 1) if 1 <= p <= len(self.queue)]
            best_pos = insert_pos
            best_score = -999999.0
            for pos in candidates:
                left_w = self.queue[pos - 1] if pos > 0 else None
                right_w = self.queue[pos] if pos < len(self.queue) else None
                left_key = self._get_card_key(left_w) if left_w else None
                right_key = self._get_card_key(right_w) if right_w else None

                score = 0.0
                if left_key and (left_key, cur_key) in self._session_seen_pairs:
                    score -= 100.0
                if right_key and (cur_key, right_key) in self._session_seen_pairs:
                    score -= 100.0

                if left_w is not None:
                    score += 5.0 if self.is_new_learning_word(left_w) != cur_is_new else -2.0
                if right_w is not None:
                    score += 5.0 if self.is_new_learning_word(right_w) != cur_is_new else -2.0

                if score > best_score:
                    best_score = score
                    best_pos = pos

            insert_pos = best_pos
        self.queue.insert(insert_pos, word)

    def _prepare_queue(
        self,
        words: List[Word],
        shuffle_within_tiers: bool = True,
        interleave_categories: bool = True,
        forward_penalized: Optional[Set[Tuple[Any, Any]]] = None,
        undirected_penalized: Optional[Set[frozenset[Any]]] = None
    ) -> List[Word]:
        """
        Partitions cards into urgency tiers, shuffles within each tier to prevent
        serial position bias, interleaves categories (Kornell & Bjork 2008),
        alternates old review/placeholder cards and new learning cards to eliminate
        card clustering, and de-biases against previous sequence pairs.
        """
        if not words:
            return []

        if not shuffle_within_tiers:
            # Deterministic mode: preserve exact input order (or sort placeholders if standalone)
            placeholders = [w for w in words if getattr(w, "is_placeholder", False)]
            non_placeholders = [w for w in words if not getattr(w, "is_placeholder", False)]
            if placeholders and not non_placeholders:
                return sorted(placeholders, key=self._card_due_sort_key)

            old_words = [w for w in words if not self.is_new_learning_word(w)]
            new_words = [w for w in words if self.is_new_learning_word(w)]
            if old_words and new_words:
                return self._alternate_old_and_new(old_words, new_words, prefer_old_first=True)
            return list(words)

        now = datetime.now(timezone.utc)
        tier_critically_overdue: List[Word] = []
        tier_due_today: List[Word] = []
        tier_new_cards: List[Word] = []
        tier_placeholders: List[Word] = []

        for w in words:
            if getattr(w, "is_placeholder", False):
                tier_placeholders.append(w)
            elif w.state in (CardState.NEW.value, CardState.LEARNING.value):
                tier_new_cards.append(w)
            elif w.urgency_score(now) > 10.0:
                tier_critically_overdue.append(w)
            else:
                tier_due_today.append(w)

        # Shuffle within tiers
        random.shuffle(tier_critically_overdue)
        random.shuffle(tier_due_today)
        random.shuffle(tier_new_cards)
        tier_placeholders = self._proximity_shuffle(
            tier_placeholders,
            now=now,
            interleave_categories=interleave_categories,
            forward_penalized=forward_penalized,
            undirected_penalized=undirected_penalized
        )

        # Interleave categories within each tier if enabled
        if interleave_categories:
            tier_critically_overdue = self._interleave_cards(tier_critically_overdue)
            tier_due_today = self._interleave_cards(tier_due_today)
            tier_new_cards = self._interleave_cards(tier_new_cards)

        # De-bias each tier against penalized pairs
        if forward_penalized or undirected_penalized:
            tier_critically_overdue = self._de_bias_sequence(
                tier_critically_overdue,
                forward_penalized=forward_penalized,
                undirected_penalized=undirected_penalized
            )
            tier_due_today = self._de_bias_sequence(
                tier_due_today,
                forward_penalized=forward_penalized,
                undirected_penalized=undirected_penalized
            )
            tier_new_cards = self._de_bias_sequence(
                tier_new_cards,
                forward_penalized=forward_penalized,
                undirected_penalized=undirected_penalized
            )

        # Combine old review cards preserving macro urgency
        # (critically overdue -> due today -> upcoming placeholders)
        old_cards = tier_critically_overdue + tier_due_today + tier_placeholders
        new_learning_cards = tier_new_cards

        # Interleave old and new cards alternately if both are present
        if old_cards and new_learning_cards:
            combined = self._alternate_old_and_new(
                old_words=old_cards,
                new_words=new_learning_cards,
                prefer_old_first=True
            )
            # Resolve adjacent pair collisions in alternated sequence if any
            if (forward_penalized or undirected_penalized) and len(combined) > 2:
                combined = self._de_bias_alternated_sequence(
                    combined,
                    forward_penalized=forward_penalized,
                    undirected_penalized=undirected_penalized
                )
        else:
            tiers = [tier_critically_overdue, tier_due_today, tier_new_cards, tier_placeholders]
            combined = []
            bounds = []
            for t in tiers:
                if t:
                    s = len(combined)
                    combined.extend(t)
                    bounds.append((s, len(combined)))

            if forward_penalized and len(bounds) > 1:
                for b_idx in range(len(bounds) - 1):
                    start_a, end_a = bounds[b_idx]
                    start_b, end_b = bounds[b_idx + 1]
                    idx_a = end_a - 1
                    idx_b = start_b
                    k_a = self._get_card_key(combined[idx_a])
                    k_b = self._get_card_key(combined[idx_b])
                    if (k_a, k_b) in forward_penalized:
                        if (end_a - start_a) > 1:
                            combined[idx_a], combined[idx_a - 1] = combined[idx_a - 1], combined[idx_a]
                        elif (end_b - start_b) > 1:
                            combined[idx_b], combined[idx_b + 1] = combined[idx_b + 1], combined[idx_b]

        return combined

    @classmethod
    def _proximity_shuffle(
        cls,
        cards: List[Word],
        now: Optional[datetime] = None,
        max_cluster_size: int = 8,
        interleave_categories: bool = True,
        forward_penalized: Optional[Set[Tuple[Any, Any]]] = None,
        undirected_penalized: Optional[Set[frozenset[Any]]] = None
    ) -> List[Word]:
        """
        Groups cards into temporal proximity clusters (cards due at similar horizons)
        and shuffles within each cluster. This eliminates associative sequence bias
        and serial position effects while strictly preserving macro urgency
        (e.g., cards due in 30 minutes always precede cards due in 2 hours or days).
        """
        if len(cards) <= 1:
            return list(cards)

        now = now or datetime.now(timezone.utc)

        # Sort cards by due date / retrievability first
        sorted_cards = sorted(cards, key=cls._card_due_sort_key)

        def _get_due_seconds(word: Word) -> float:
            if not word.due_date:
                return float("inf")
            try:
                dt = datetime.fromisoformat(word.due_date.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return (dt - now).total_seconds()
            except Exception:
                return float("inf")

        clusters: List[List[Word]] = []
        current_cluster: List[Word] = []

        for card in sorted_cards:
            if not current_cluster:
                current_cluster.append(card)
                continue

            first_card = current_cluster[0]
            t_curr = _get_due_seconds(card)
            t_first = _get_due_seconds(first_card)

            # Check if card is temporally close to the first card in the cluster
            if math.isinf(t_curr) or math.isinf(t_first):
                is_close = math.isinf(t_curr) and math.isinf(t_first)
            elif t_curr <= 0 and t_first <= 0:
                # Both overdue: within 1 hour or 25% of overdue horizon
                is_close = abs(t_curr - t_first) <= max(3600.0, abs(t_first) * 0.25)
            elif t_curr <= 0 or t_first <= 0:
                is_close = False
            else:
                # Both in future:
                # Proximity window: within 15 minutes, or within 20% of first card's horizon
                window = max(900.0, t_first * 0.20)
                is_close = (t_curr - t_first) <= window

            if is_close and len(current_cluster) < max_cluster_size:
                current_cluster.append(card)
            else:
                clusters.append(current_cluster)
                current_cluster = [card]

        if current_cluster:
            clusters.append(current_cluster)

        # Shuffle, interleave, and de-bias within each cluster
        result: List[Word] = []
        for cluster in clusters:
            if len(cluster) > 1:
                shuffled_cluster = list(cluster)
                random.shuffle(shuffled_cluster)
                if interleave_categories and len(shuffled_cluster) > 1:
                    shuffled_cluster = cls._interleave_cards(shuffled_cluster)
                if forward_penalized or undirected_penalized:
                    shuffled_cluster = cls._de_bias_sequence(
                        shuffled_cluster,
                        forward_penalized=forward_penalized,
                        undirected_penalized=undirected_penalized
                    )
                result.extend(shuffled_cluster)
            else:
                result.extend(cluster)

        return result

    @staticmethod
    def _card_due_sort_key(word: Word) -> tuple[datetime, float]:
        """Sorts primarily by closest due date, then lowest retrievability."""
        now = datetime.now(timezone.utc)
        due_dt = datetime.max.replace(tzinfo=timezone.utc)
        if word.due_date:
            try:
                dt = datetime.fromisoformat(word.due_date.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                due_dt = dt
            except Exception:
                pass
        return (due_dt, -word.lapses)

    @classmethod
    def _interleave_cards(cls, cards: List[Word]) -> List[Word]:
        """
        Interleaves cards by group / primary tag so adjacent cards don't share
        the same subcategory, maximizing cognitive discrimination.
        """
        if len(cards) <= 1:
            return list(cards)

        if len(cards) == 2:
            cat0 = (cards[0].tags.split(",")[0].strip() if cards[0].tags else cards[0].group_name) or "general"
            cat1 = (cards[1].tags.split(",")[0].strip() if cards[1].tags else cards[1].group_name) or "general"
            if cat0 != cat1:
                res = list(cards)
                random.shuffle(res)
                return res
            return list(cards)

        # Group cards by category/tag
        buckets: Dict[str, List[Word]] = {}
        for c in cards:
            cat = (c.tags.split(",")[0].strip() if c.tags else c.group_name) or "general"
            buckets.setdefault(cat, []).append(c)

        for b in buckets.values():
            random.shuffle(b)

        # Round-robin interleaving with dynamic re-shuffling of non-empty buckets
        interleaved: List[Word] = []
        keys = list(buckets.keys())

        while any(buckets.values()):
            non_empty_keys = [k for k in keys if buckets[k]]
            if len(non_empty_keys) > 1:
                random.shuffle(non_empty_keys)
            for k in non_empty_keys:
                if buckets[k]:
                    interleaved.append(buckets[k].pop(0))

        return interleaved


# ─── Session Quality & Threshold Calibration ──────────────────────────────────

def rate_session_quality(
    words: Optional[Sequence[Word]] = None,
    repetitions_map: Optional[Dict[Any, int]] = None,
    queue: Optional[RecurrentSessionQueue] = None,
    stats: Optional[SessionStats] = None,
    expected_slope: float = 0.10,
    expected_intercept: float = 1.0,
) -> Dict[str, Any]:
    """
    Rates a learning session on its quality of learning, mainly by the average
    number of repetitions needed for words to be mastered, normalized by word difficulty.

    Mathematical Model:
    - For each word i with difficulty D_i in [1.0, 10.0]:
        R_expected(D_i) = expected_intercept + expected_slope * (D_i - 1.0)
      (e.g., D=1 -> 1.0 reps, D=5 -> 1.4 reps, D=10 -> 1.9 reps)
    - Actual repetitions R_i >= 1 (1 if mastered on first attempt, 2+ if re-queued).
    - Session average repetitions: R_avg = sum(R_i) / N
    - Session expected repetitions: R_exp_avg = sum(R_expected(D_i)) / N
    - Normalized repetitions index: norm_reps = R_avg / R_exp_avg
    - Learning Quality Score: quality_score = 1.0 / norm_reps = R_exp_avg / R_avg
    - Quality Tiers:
        >= 1.20: Exceptional (mastered significantly faster than expected)
        >= 1.05: High Efficiency (exceeded expected retention)
        >= 0.90: Target Mastery (nominal expected performance)
        >= 0.75: Moderate (mild friction / extra re-testing needed)
        < 0.75: Struggling (cognitive overload / frequent lapses)
    """
    word_list: List[Word] = []
    reps_dict: Dict[Any, int] = {}

    if queue is not None:
        word_list = list(queue.completed_words.values())
        for k in queue.completed_words.keys():
            reps_dict[k] = 1 + queue.recurrent_counts.get(k, 0)
    elif words is not None:
        word_list = list(words)

    if repetitions_map is not None:
        reps_dict.update(repetitions_map)

    if not word_list:
        return {
            "quality_score": 1.0,
            "quality_percentage": 100.0,
            "avg_repetitions": 1.0,
            "avg_expected_repetitions": 1.0,
            "avg_difficulty": 5.0,
            "normalized_repetitions": 1.0,
            "total_load": 0,
            "unique_words": 0,
            "total_repetitions": 0,
            "quality_tier": "Nominal",
            "assessment": "No cards reviewed to assess learning quality."
        }

    total_reps = 0
    total_expected = 0.0
    total_diff = 0.0
    total_load = 0
    n = len(word_list)

    for w in word_list:
        k = getattr(w, "id", None) if getattr(w, "id", None) is not None else getattr(w, "word", "")
        r_actual = max(1, reps_dict.get(k, 1))
        diff = max(1.0, min(10.0, float(getattr(w, "difficulty", 5.0) or 5.0)))
        cap = w.brain_capacity

        r_exp = expected_intercept + expected_slope * (diff - 1.0)

        total_reps += r_actual
        total_expected += r_exp
        total_diff += diff
        total_load += cap

    avg_reps = total_reps / n
    avg_exp = total_expected / n
    avg_diff = total_diff / n
    norm_reps = avg_reps / max(0.01, avg_exp)
    quality_score = max(0.1, min(2.5, 1.0 / max(0.01, norm_reps)))
    quality_pct = round(quality_score * 100.0, 1)

    if quality_score >= 1.20:
        quality_tier = "Exceptional"
        assessment = f"Outstanding recall! Mastered words in {avg_reps:.2f} reps/word vs. {avg_exp:.2f} expected."
    elif quality_score >= 1.05:
        quality_tier = "High Efficiency"
        assessment = f"High learning efficiency! {avg_reps:.2f} reps/word vs. {avg_exp:.2f} expected for difficulty {avg_diff:.1f}."
    elif quality_score >= 0.90:
        quality_tier = "Target Mastery"
        assessment = f"Solid mastery on target. Required {avg_reps:.2f} reps/word (expected {avg_exp:.2f})."
    elif quality_score >= 0.75:
        quality_tier = "Moderate"
        assessment = f"Mild friction detected. Required {avg_reps:.2f} reps/word (expected {avg_exp:.2f})."
    else:
        quality_tier = "Struggling"
        assessment = f"High friction / lapses. Required {avg_reps:.2f} reps/word (expected {avg_exp:.2f})."

    return {
        "quality_score": round(quality_score, 3),
        "quality_percentage": quality_pct,
        "avg_repetitions": round(avg_reps, 2),
        "avg_expected_repetitions": round(avg_exp, 2),
        "avg_difficulty": round(avg_diff, 2),
        "normalized_repetitions": round(norm_reps, 3),
        "total_load": total_load,
        "unique_words": n,
        "total_repetitions": total_reps,
        "quality_tier": quality_tier,
        "assessment": assessment
    }


def tune_capacity_threshold(
    current_threshold: int,
    session_load: float,
    quality_score: float,
    min_threshold: int = 60,
    max_threshold: int = 160,
    learning_rate: float = 12.0
) -> Dict[str, Any]:
    """
    Tunes the session brain capacity threshold based on a load vs. quality comparison.

    Principles:
    1. High load + High quality -> User comfortably handled high cognitive load with few repetitions;
       expand capacity threshold to accelerate progress.
    2. High load + Low quality -> User suffered cognitive fatigue / high repetitions under heavy load;
       contract capacity threshold to prevent overload.
    3. Low load -> Small sample size (e.g. 1-card review); dampen adjustments proportionally.
    """
    current_threshold = int(current_threshold)
    if session_load <= 0:
        return {
            "previous_threshold": current_threshold,
            "new_threshold": current_threshold,
            "delta": 0,
            "session_load": 0,
            "load_ratio": 0.0,
            "quality_score": round(quality_score, 3),
            "reason": "No session load to evaluate"
        }

    load_ratio = session_load / max(1.0, float(current_threshold))
    # Full confidence when session load >= 50% of threshold
    load_confidence = min(1.0, session_load / (max(1.0, float(current_threshold)) * 0.5))
    quality_delta = quality_score - 1.0

    if quality_delta >= 0:
        # High quality: expand threshold
        raw_delta = learning_rate * quality_delta * load_confidence
    else:
        # Lower quality: contract threshold (with 25% safety buffer against overload)
        raw_delta = learning_rate * 1.25 * quality_delta * load_confidence

    delta = int(round(raw_delta))
    new_threshold = max(min_threshold, min(max_threshold, current_threshold + delta))
    actual_delta = new_threshold - current_threshold

    if actual_delta > 0:
        reason = f"Expanded (+{actual_delta}) due to high learning quality ({quality_score:.0%}) under {int(round(load_ratio * 100))}% load."
    elif actual_delta < 0:
        reason = f"Contracted ({actual_delta}) due to cognitive friction ({quality_score:.0%}) under {int(round(load_ratio * 100))}% load."
    else:
        reason = "Maintained threshold (balanced load vs. mastery)."

    return {
        "previous_threshold": current_threshold,
        "new_threshold": new_threshold,
        "delta": actual_delta,
        "session_load": int(session_load),
        "load_ratio": round(load_ratio, 2),
        "quality_score": round(quality_score, 3),
        "reason": reason
    }
