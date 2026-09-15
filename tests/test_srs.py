"""
Unit tests for the Cognitive Science-Backed Adaptive Recurrent SRS Engine.

Validates:
1. Ebbinghaus & DSR dynamic progression and lapse handling.
2. Bjork & Bjork (1992, 2011) Desirable Difficulties (storage strength gain inversely related to retrievability).
3. Cepeda et al. (2006, 2008) Power-law interval flattening and anti-clustering fuzzing.
4. Cognitive thought latency adaptations (fluency bonus, hesitation damping, learning re-queue).
5. Kornell & Bjork (2008) Category interleaving and queue shuffling.
"""
import pytest
from datetime import datetime, timezone, timedelta
from vocab.models import Word, SRSGrade, CardState, ReviewLog
from vocab.srs import (
    SRSEngine,
    UniversalSRSFormula,
    RecurrentSessionQueue,
    MIN_DIFFICULTY,
    MAX_DIFFICULTY,
    MIN_EASE_FACTOR,
    MAX_EASE_FACTOR,
)


def test_new_card_good_progression():
    """Test that a new card progresses through learning steps on Good and graduates to Review."""
    word = Word(
        id=1,
        group_id=1,
        word="laconic",
        definition="concise",
        state=CardState.NEW.value,
        step=0,
        interval_days=0.0,
        reps=0,
        lapses=0,
        difficulty=5.0,
        stability=0.0
    )
    now = datetime(2026, 9, 7, 12, 0, 0, tzinfo=timezone.utc)

    # First GOOD review: should advance to step 1 (10 minutes)
    updated, days = SRSEngine.calculate_next_state(word, SRSGrade.GOOD, now=now, apply_fuzz=False)
    assert updated.state == CardState.LEARNING.value
    assert updated.step == 1
    assert days == pytest.approx(10.0 / 1440.0)

    # Second GOOD review: should graduate to REVIEW
    updated_grad, days_grad = SRSEngine.calculate_next_state(updated, SRSGrade.GOOD, now=now, apply_fuzz=False)
    assert updated_grad.state == CardState.REVIEW.value
    assert updated_grad.step == 0
    assert updated_grad.reps == 1
    assert days_grad >= 1.0
    assert updated_grad.stability == pytest.approx(days_grad)


def test_new_card_easy_immediate_graduation():
    """Test that rating Easy immediately graduates a new card with high initial stability."""
    word = Word(
        id=2,
        group_id=1,
        word="ephemeral",
        definition="fleeting",
        state=CardState.NEW.value,
        step=0,
        interval_days=0.0,
        reps=0,
        lapses=0,
        difficulty=5.0,
        stability=0.0
    )
    now = datetime(2026, 9, 7, 12, 0, 0, tzinfo=timezone.utc)

    updated, days = SRSEngine.calculate_next_state(word, SRSGrade.EASY, now=now, apply_fuzz=False)
    assert updated.state == CardState.REVIEW.value
    assert updated.step == 0
    assert updated.reps == 1
    assert days >= 4.0
    assert updated.difficulty < 5.0  # Difficulty reduced on Easy
    assert updated.ease_factor >= 2.5


def test_review_card_lapse_on_again():
    """Test that a graduated review card lapses on AGAIN and enters relearning."""
    word = Word(
        id=3,
        group_id=1,
        word="obdurate",
        definition="stubborn",
        state=CardState.REVIEW.value,
        step=0,
        interval_days=10.0,
        stability=10.0,
        difficulty=5.0,
        reps=4,
        lapses=0
    )
    now = datetime(2026, 9, 7, 12, 0, 0, tzinfo=timezone.utc)

    updated, days = SRSEngine.calculate_next_state(word, SRSGrade.AGAIN, now=now, apply_fuzz=False)
    assert updated.state == CardState.RELEARNING.value
    assert updated.lapses == 1
    assert updated.reps == 0
    assert updated.stability < 10.0  # Stability collapsed post-lapse
    assert days == pytest.approx(10.0 / 1440.0)


def test_difficulty_and_ease_factor_bounds():
    """Test that difficulty and ease factor stay within configured boundaries."""
    word_low = Word(
        id=4,
        group_id=1,
        word="axon",
        definition="nerve fiber",
        state=CardState.REVIEW.value,
        interval_days=5.0,
        stability=5.0,
        difficulty=1.2
    )
    # Consecutive Easy reviews should not push difficulty below MIN_DIFFICULTY
    for _ in range(5):
        word_low, _ = SRSEngine.calculate_next_state(word_low, SRSGrade.EASY, apply_fuzz=False)
    assert word_low.difficulty >= MIN_DIFFICULTY
    assert word_low.ease_factor <= MAX_EASE_FACTOR

    word_high = Word(
        id=5,
        group_id=1,
        word="synapse",
        definition="junction",
        state=CardState.REVIEW.value,
        interval_days=5.0,
        stability=5.0,
        difficulty=9.5
    )
    # Consecutive Again reviews should not push difficulty above MAX_DIFFICULTY
    for _ in range(5):
        word_high, _ = SRSEngine.calculate_next_state(word_high, SRSGrade.AGAIN, apply_fuzz=False)
    assert word_high.difficulty <= MAX_DIFFICULTY
    assert word_high.ease_factor >= MIN_EASE_FACTOR


def test_bjork_desirable_difficulties_retrieval_gain():
    """
    Test Bjork & Bjork (1992, 2011) Desirable Difficulties principle:
    Retrieving a memory when retrievability R is lower yields greater storage
    strength expansion than retrieving when memory is still fresh.
    """
    now = datetime(2026, 9, 7, 12, 0, 0, tzinfo=timezone.utc)

    # Word reviewed yesterday (high retrievability R ~ 0.99)
    word_fresh = Word(
        id=6,
        group_id=1,
        word="hippocampus",
        definition="memory center",
        state=CardState.REVIEW.value,
        interval_days=10.0,
        stability=10.0,
        difficulty=5.0,
        last_reviewed=(now - timedelta(days=1)).isoformat()
    )

    # Word reviewed 10 days ago (retrievability R ~ 0.90)
    word_due = Word(
        id=7,
        group_id=1,
        word="amygdala",
        definition="emotion center",
        state=CardState.REVIEW.value,
        interval_days=10.0,
        stability=10.0,
        difficulty=5.0,
        last_reviewed=(now - timedelta(days=10)).isoformat()
    )

    up_fresh, days_fresh = SRSEngine.calculate_next_state(word_fresh, SRSGrade.GOOD, now=now, apply_fuzz=False)
    up_due, days_due = SRSEngine.calculate_next_state(word_due, SRSGrade.GOOD, now=now, apply_fuzz=False)

    # Reviewing when due (lower R) must yield a larger stability increase
    assert days_due > days_fresh


def test_cepeda_power_law_flattening():
    """
    Test Cepeda et al. (2008) power-law growth damping:
    Growth multiplier decreases as stability increases, preventing interval explosion.
    """
    now = datetime(2026, 9, 7, 12, 0, 0, tzinfo=timezone.utc)

    word_early = Word(
        id=8,
        group_id=1,
        word="dendrite",
        definition="receptor branch",
        state=CardState.REVIEW.value,
        interval_days=5.0,
        stability=5.0,
        difficulty=5.0,
        last_reviewed=(now - timedelta(days=5)).isoformat()
    )

    word_mature = Word(
        id=9,
        group_id=1,
        word="myelin",
        definition="fatty insulation",
        state=CardState.REVIEW.value,
        interval_days=60.0,
        stability=60.0,
        difficulty=5.0,
        last_reviewed=(now - timedelta(days=60)).isoformat()
    )

    _, days_early = SRSEngine.calculate_next_state(word_early, SRSGrade.GOOD, now=now, apply_fuzz=False)
    _, days_mature = SRSEngine.calculate_next_state(word_mature, SRSGrade.GOOD, now=now, apply_fuzz=False)

    ratio_early = days_early / word_early.stability
    ratio_mature = days_mature / word_mature.stability

    # Early card should have higher proportional growth multiplier than mature card
    assert ratio_early > ratio_mature


def test_cognitive_latency_fast_recall():
    """Test that fast recall (thought time <= 3s) grants a fluency bonus."""
    word = Word(
        id=10,
        group_id=1,
        word="dopamine",
        definition="neurotransmitter",
        state=CardState.REVIEW.value,
        interval_days=5.0,
        stability=5.0,
        difficulty=5.0,
        reps=2
    )

    standard, std_days = SRSEngine.calculate_next_state(word, SRSGrade.GOOD, thought_time_seconds=0.0, apply_fuzz=False)
    fast, fast_days = SRSEngine.calculate_next_state(word, SRSGrade.GOOD, thought_time_seconds=1.5, apply_fuzz=False)

    assert fast_days > std_days
    assert fast_days == pytest.approx(std_days * 1.12, rel=1e-2)
    assert fast.last_thought_time == 1.5
    assert fast.avg_thought_time == 1.5


def test_cognitive_latency_hesitant_recall():
    """Test that hesitant recall (thought time > 7s and > 12s) compresses interval and increases difficulty."""
    word = Word(
        id=11,
        group_id=1,
        word="acetylcholine",
        definition="neurotransmitter",
        state=CardState.REVIEW.value,
        interval_days=10.0,
        stability=10.0,
        difficulty=5.0,
        reps=3
    )

    standard, std_days = SRSEngine.calculate_next_state(word, SRSGrade.GOOD, thought_time_seconds=0.0, apply_fuzz=False)
    hesitant, hes_days = SRSEngine.calculate_next_state(word, SRSGrade.GOOD, thought_time_seconds=9.0, apply_fuzz=False)
    assert hes_days < std_days
    assert hes_days == pytest.approx(std_days * 0.85, rel=1e-2)
    assert hesitant.difficulty > standard.difficulty

    severe, sev_days = SRSEngine.calculate_next_state(word, SRSGrade.GOOD, thought_time_seconds=15.0, apply_fuzz=False)
    assert sev_days < hes_days
    assert sev_days == pytest.approx(std_days * 0.70, rel=1e-2)
    assert severe.difficulty > hesitant.difficulty


def test_cognitive_latency_requeue():
    """Test that severe hesitation (>12s) on learning cards causes intra-session re-queueing."""
    w1 = Word(id=20, group_id=1, word="pons", definition="bridge", state=CardState.LEARNING.value)
    queue = RecurrentSessionQueue([w1], enable_shuffling=False)

    c = queue.next_card()
    # User answered GOOD, but took 14.2s to recall!
    requeued = queue.handle_result(c, SRSGrade.GOOD, thought_time_seconds=14.2)
    assert requeued is True
    assert queue.remaining_count == 1


def test_anti_clustering_fuzz():
    """Test anti-clustering fuzzing to prevent repeating review spikes."""
    # Under 3 days: no fuzz
    assert SRSEngine.apply_interval_fuzz(1.0) == 1.0
    assert SRSEngine.apply_interval_fuzz(2.5) == 2.5

    # 3 to 6 days: small jitter
    fuzzed_5 = SRSEngine.apply_interval_fuzz(5.0)
    assert 3.0 <= fuzzed_5 <= 6.0

    # >= 7 days: +/- 5% jitter
    fuzzed_30 = SRSEngine.apply_interval_fuzz(30.0)
    assert 28.0 <= fuzzed_30 <= 32.0


def test_recurrent_session_queue():
    """Test intra-session recurrent queueing behavior."""
    w1 = Word(id=1, group_id=1, word="w1", definition="d1")
    w2 = Word(id=2, group_id=1, word="w2", definition="d2")
    w3 = Word(id=3, group_id=1, word="w3", definition="d3")
    w4 = Word(id=4, group_id=1, word="w4", definition="d4")

    queue = RecurrentSessionQueue([w1, w2, w3, w4], reinsert_offset=2, enable_shuffling=False, enable_interleaving=False)
    assert queue.remaining_count == 4

    # Pop card 1
    c1 = queue.next_card()
    assert c1.word == "w1"

    # User fails card 1 (AGAIN)
    requeued = queue.handle_result(c1, SRSGrade.AGAIN)
    assert requeued is True
    assert queue.remaining_count == 4

    # Pop w2 -> user answers GOOD
    c2 = queue.next_card()
    assert c2.word == "w2"
    assert queue.handle_result(c2, SRSGrade.GOOD) is False

    # Pop w3 -> user answers GOOD
    c3 = queue.next_card()
    assert c3.word == "w3"
    assert queue.handle_result(c3, SRSGrade.GOOD) is False

    # Pop next -> it MUST be the recurrent w1!
    c1_recur = queue.next_card()
    assert c1_recur.word == "w1"
    assert queue.handle_result(c1_recur, SRSGrade.GOOD) is False

    # Pop w4 -> GOOD
    c4 = queue.next_card()
    assert c4.word == "w4"
    assert queue.handle_result(c4, SRSGrade.GOOD) is False

    # Queue should now be empty and finished!
    assert queue.is_empty is True
    assert len(queue.completed_word_ids) == 4


def test_queue_shuffling_and_interleaving():
    """Test that queue shuffling and interleaving mix categories across cards (Kornell & Bjork 2008)."""
    words = [
        Word(id=1, group_id=1, group_name="Bio", tags="neuro", word="axon", definition="fiber"),
        Word(id=2, group_id=1, group_name="Bio", tags="neuro", word="dendrite", definition="branch"),
        Word(id=3, group_id=1, group_name="Bio", tags="neuro", word="myelin", definition="sheath"),
        Word(id=4, group_id=1, group_name="Bio", tags="brain", word="occipital", definition="vision"),
        Word(id=5, group_id=1, group_name="Bio", tags="brain", word="temporal", definition="hearing"),
        Word(id=6, group_id=1, group_name="Bio", tags="brain", word="frontal", definition="executive"),
    ]
    queue = RecurrentSessionQueue(words, enable_shuffling=True, enable_interleaving=True)
    assert queue.remaining_count == 6

    # Test shuffle_remaining method
    shuffled_len = queue.shuffle_remaining()
    assert shuffled_len == 6


def test_dynamic_add_cards_to_queue():
    """Test dynamically adding newly due cards to an active session queue."""
    w1 = Word(id=1, group_id=1, word="card1", definition="d1")
    w2 = Word(id=2, group_id=1, word="card2", definition="d2")

    queue = RecurrentSessionQueue([w1, w2], enable_shuffling=False, enable_interleaving=False)
    assert queue.remaining_count == 2

    # A newly due card matures during the session
    w3_new = Word(id=3, group_id=1, word="card3_matured", definition="d3")
    added = queue.add_cards([w3_new])
    assert added == 1
    assert queue.remaining_count == 3

    # Attempting to add duplicate card ID should be ignored
    w1_dup = Word(id=1, group_id=1, word="card1_dup", definition="d1")
    added_dup = queue.add_cards([w1_dup])
    assert added_dup == 0
    assert queue.remaining_count == 3


def test_queue_placeholders_preserved():
    """Test that is_placeholder attribute is preserved through SRS engine and queue."""
    w_ph = Word(id=10, group_id=1, word="placeholder_term", definition="test", is_placeholder=True)
    queue = RecurrentSessionQueue([w_ph], enable_shuffling=False)

    card = queue.next_card()
    assert card is not None
    assert card.is_placeholder is True

    # When reviewed through SRS Engine
    updated, _ = SRSEngine.calculate_next_state(card, SRSGrade.GOOD, apply_fuzz=False)
    assert updated.is_placeholder is True


def test_queue_closest_due_preserved_when_all_caught_up():
    """
    Test that when a session starts with cards that are all caught up (upcoming cards),
    RecurrentSessionQueue preserves strict closest-due-time order even with enable_shuffling=True.
    """
    now = datetime.now(timezone.utc)
    w_2h = Word(id=1, group_id=1, word="w_2h", definition="d", state="review", due_date=(now + timedelta(hours=2)).isoformat(), is_placeholder=True)
    w_30m = Word(id=2, group_id=1, word="w_30m", definition="d", state="review", due_date=(now + timedelta(minutes=30)).isoformat(), is_placeholder=True)
    w_3d = Word(id=3, group_id=1, word="w_3d", definition="d", state="review", due_date=(now + timedelta(days=3)).isoformat(), is_placeholder=True)
    w_1d = Word(id=4, group_id=1, word="w_1d", definition="d", state="review", due_date=(now + timedelta(days=1)).isoformat(), is_placeholder=True)

    # Scrambled input list
    input_words = [w_2h, w_3d, w_30m, w_1d]

    # Queue initialized with enable_shuffling=True
    queue = RecurrentSessionQueue(input_words, enable_shuffling=True)

    # First card popped must be the closest due: w_30m (30 minutes)
    c1 = queue.next_card()
    assert c1 is not None and c1.word == "w_30m"

    # Second card popped: w_2h (2 hours)
    c2 = queue.next_card()
    assert c2 is not None and c2.word == "w_2h"

    # Third card popped: w_1d (1 day)
    c3 = queue.next_card()
    assert c3 is not None and c3.word == "w_1d"

    # Fourth card popped: w_3d (3 days)
    c4 = queue.next_card()
    assert c4 is not None and c4.word == "w_3d"


def test_proximity_shuffle_reduces_same_order_repetition():
    """
    Test that when cards share identical or close due dates (e.g. batch-reviewed or caught up),
    RecurrentSessionQueue randomizes and varies their order across sessions,
    actively reducing serial position and associative sequence bias.
    """
    now = datetime.now(timezone.utc)
    base_due = now + timedelta(days=1)
    # 5 words with very close due dates (reviewed in the same previous session)
    words = [
        Word(id=1, group_id=1, word="somatic nervous system", definition="voluntary muscle control", due_date=base_due.isoformat(), is_placeholder=True),
        Word(id=2, group_id=1, word="peripheral nervous system", definition="nerves outside CNS", due_date=(base_due + timedelta(seconds=15)).isoformat(), is_placeholder=True),
        Word(id=3, group_id=1, word="serotonin", definition="mood neurotransmitter", due_date=(base_due + timedelta(seconds=30)).isoformat(), is_placeholder=True),
        Word(id=4, group_id=1, word="medulla", definition="heart rate and breathing", due_date=(base_due + timedelta(seconds=45)).isoformat(), is_placeholder=True),
        Word(id=5, group_id=1, word="adrenal gland", definition="releases adrenaline", due_date=(base_due + timedelta(seconds=60)).isoformat(), is_placeholder=True),
    ]

    sequences = []
    for _ in range(12):
        q = RecurrentSessionQueue(words, enable_shuffling=True)
        seq = tuple(w.word for w in q.queue)
        sequences.append(seq)
        # All 5 words must always be in the queue
        assert len(seq) == 5
        assert set(seq) == {w.word for w in words}

    # Across 12 runs, there must be multiple different permutations
    unique_orders = set(sequences)
    assert len(unique_orders) > 1, "Queue produced identical order across all sessions despite shuffling enabled"


def test_recurrent_reinsert_dynamic_jitter():
    """
    Test that re-inserting failed cards uses jittered spacing (between 2 and 5)
    rather than a rigid constant offset of 3 every single time.
    """
    words = [Word(id=i, group_id=1, word=f"word_{i}", definition=f"d{i}") for i in range(1, 10)]

    insert_positions = set()
    for _ in range(40):
        q = RecurrentSessionQueue(words, enable_shuffling=True)
        card = q.next_card()
        assert card is not None
        # Card failed on AGAIN
        requeued = q.handle_result(card, SRSGrade.AGAIN)
        assert requeued is True

        # Find where the failed card was re-inserted
        pos = [i for i, w in enumerate(q.queue) if w.id == card.id][0]
        insert_positions.add(pos)
        assert 2 <= pos <= 5

    # Across 40 requeues, multiple different jittered positions must be observed
    assert len(insert_positions) > 1, f"Expected dynamic jittered positions, but got only {insert_positions}"


def test_placeholder_memory_compounding():
    """
    Test that reviewing a placeholder card before its due date (delta_t < S)
    actively compounds its memory trace, increasing stability (S' > S)
    and pushing its next interval further into the future.
    """
    now = datetime(2026, 9, 7, 12, 0, 0, tzinfo=timezone.utc)
    # Card graduated with stability = 10.0 days, last reviewed 2 days ago (due in 8 days)
    word = Word(
        id=50,
        group_id=1,
        word="synaptic plasticity",
        definition="ability of synapses to strengthen or weaken",
        state=CardState.REVIEW.value,
        interval_days=10.0,
        stability=10.0,
        difficulty=5.0,
        last_reviewed=(now - timedelta(days=2)).isoformat(),
        due_date=(now + timedelta(days=8)).isoformat(),
        is_placeholder=True
    )

    # User reviews this placeholder card ahead of time with normal GOOD recall
    updated, next_days = SRSEngine.calculate_next_state(word, SRSGrade.GOOD, thought_time_seconds=4.0, now=now, apply_fuzz=False)

    # Stability MUST have grown and exceeded previous 10.0 days (adding to memory)
    assert updated.stability > 10.0
    assert next_days > 10.0
    assert updated.is_placeholder is True

    # Next due date must be scheduled from current time + new interval
    expected_due = now + timedelta(days=next_days)
    assert datetime.fromisoformat(updated.due_date) == expected_due


def test_placeholder_hesitation_impact():
    """
    Test that hesitation latency on a placeholder card directly influences the
    universal formula: fluent recall yields stronger compounding than hesitant recall.
    """
    now = datetime(2026, 9, 7, 12, 0, 0, tzinfo=timezone.utc)
    base_word = Word(
        id=51,
        group_id=1,
        word="myelin sheath",
        definition="insulating layer around nerves",
        state=CardState.REVIEW.value,
        interval_days=10.0,
        stability=10.0,
        difficulty=5.0,
        last_reviewed=(now - timedelta(days=3)).isoformat(),
        is_placeholder=True
    )

    # Fluent recall (1.5s thought latency)
    fast_updated, fast_days = SRSEngine.calculate_next_state(base_word, SRSGrade.GOOD, thought_time_seconds=1.5, now=now, apply_fuzz=False)

    # Hesitant recall (10.0s thought latency)
    hes_updated, hes_days = SRSEngine.calculate_next_state(base_word, SRSGrade.GOOD, thought_time_seconds=10.0, now=now, apply_fuzz=False)

    # Fluent recall must compound memory significantly more than hesitant recall
    assert fast_days > hes_days
    assert fast_updated.stability > hes_updated.stability
    assert hes_updated.difficulty > fast_updated.difficulty


def test_universal_formula_from_entries_replay():
    """
    Test that replaying an entire historical sequence of test entries
    (entry time, response choice, hesitation latency) through UniversalSRSFormula
    calculates exact memory state and compounds placeholder reviews.
    """
    t0 = datetime(2026, 9, 1, 10, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(minutes=15)
    t2 = t0 + timedelta(days=1)  # Placeholder review (1 day into ~2.5 day stability)
    t3 = t0 + timedelta(days=4)  # Review test entry

    entries = [
        {"grade": int(SRSGrade.GOOD), "thought_time_seconds": 2.5, "reviewed_at": t0.isoformat()},
        {"grade": int(SRSGrade.GOOD), "thought_time_seconds": 2.0, "reviewed_at": t1.isoformat()},
        {"grade": int(SRSGrade.GOOD), "thought_time_seconds": 1.8, "reviewed_at": t2.isoformat()},  # Placeholder!
        {"grade": int(SRSGrade.EASY), "thought_time_seconds": 1.2, "reviewed_at": t3.isoformat()},
    ]

    now = t0 + timedelta(days=5)
    res = UniversalSRSFormula.calculate_from_entries(entries, current_time=now)

    assert res["state"] == CardState.REVIEW.value
    assert res["reps"] >= 3
    assert res["lapses"] == 0
    assert res["stability"] > 5.0
    assert res["interval_days"] == res["stability"]
    assert 0.0 < res["retrievability"] <= 1.0
    assert res["avg_thought_time"] == pytest.approx((2.5 + 2.0 + 1.8 + 1.2) / 4.0, rel=1e-2)


def test_srsl_calculate_from_review_logs():
    """
    Test SRSEngine.calculate_from_review_logs updating a Word model from ReviewLog objects.
    """
    t0 = datetime(2026, 9, 1, 10, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(minutes=15)
    t2 = t0 + timedelta(days=2)

    word = Word(
        id=99,
        group_id=1,
        word="serotonin",
        definition="mood neurotransmitter",
        state=CardState.NEW.value
    )

    logs = [
        ReviewLog(id=1, word_id=99, grade=int(SRSGrade.GOOD), review_mode="flashcard", scheduled_days=0.007, thought_time_seconds=2.0, reviewed_at=t0.isoformat()),
        ReviewLog(id=2, word_id=99, grade=int(SRSGrade.GOOD), review_mode="flashcard", scheduled_days=2.5, thought_time_seconds=1.5, reviewed_at=t1.isoformat()),
        ReviewLog(id=3, word_id=99, grade=int(SRSGrade.GOOD), review_mode="flashcard", scheduled_days=5.5, thought_time_seconds=2.2, reviewed_at=t2.isoformat()),
    ]

    now = t0 + timedelta(days=3)
    updated, scheduled = SRSEngine.calculate_from_review_logs(word, logs, now=now)

    assert updated.state == CardState.REVIEW.value
    assert updated.reps == 2
    assert updated.stability > 2.5
    assert scheduled == updated.interval_days
    assert updated.last_reviewed == t2.isoformat()


def test_placeholder_unfamiliar_again_resets_to_relearning():
    """
    Test that when an upcoming/placeholder card is rated AGAIN (unfamiliar),
    it immediately transitions to RELEARNING, resets reps to 0, increments lapses,
    collapses stability, clears is_placeholder to False, sets interval to 10m,
    and is re-queued in the active session.
    """
    now = datetime(2026, 9, 7, 12, 0, 0, tzinfo=timezone.utc)
    word = Word(
        id=70,
        group_id=1,
        word="acetylcholine",
        definition="neurotransmitter for motor control",
        state=CardState.REVIEW.value,
        interval_days=10.0,
        stability=10.0,
        difficulty=5.0,
        last_reviewed=(now - timedelta(days=2)).isoformat(),
        due_date=(now + timedelta(days=8)).isoformat(),
        is_placeholder=True
    )

    updated, scheduled_days = SRSEngine.calculate_next_state(
        word, SRSGrade.AGAIN, thought_time_seconds=3.0, now=now, apply_fuzz=False
    )

    assert updated.state == CardState.RELEARNING.value
    assert updated.is_placeholder is False
    assert updated.reps == 0
    assert updated.lapses == 1
    assert scheduled_days == pytest.approx(10.0 / 1440.0)
    assert updated.stability < 3.0

    # Must be re-queued in active session
    queue = RecurrentSessionQueue([word], enable_shuffling=False)
    requeued = queue.handle_result(updated, SRSGrade.AGAIN)
    assert requeued is True


def test_placeholder_unfamiliar_hard_resets_to_relearning():
    """
    Test that when an upcoming/placeholder card is rated HARD (struggled/unfamiliar
    before due date), it is NOT scheduled for days into the future. It immediately
    transitions to RELEARNING, clears is_placeholder, sets 10m remediation interval,
    regresses stability, and is re-queued in the session.
    """
    now = datetime(2026, 9, 7, 12, 0, 0, tzinfo=timezone.utc)
    word = Word(
        id=71,
        group_id=1,
        word="endorphins",
        definition="natural pain relievers",
        state=CardState.REVIEW.value,
        interval_days=10.0,
        stability=10.0,
        difficulty=5.0,
        last_reviewed=(now - timedelta(days=2)).isoformat(),
        due_date=(now + timedelta(days=8)).isoformat(),
        is_placeholder=True
    )

    updated, scheduled_days = SRSEngine.calculate_next_state(
        word, SRSGrade.HARD, thought_time_seconds=6.0, now=now, apply_fuzz=False
    )

    assert updated.state == CardState.RELEARNING.value
    assert updated.is_placeholder is False
    assert updated.reps == 0
    assert updated.lapses == 1
    assert scheduled_days == pytest.approx(10.0 / 1440.0)
    assert updated.stability < 5.0
    assert updated.difficulty > 5.0

    # Must be re-queued in active session
    queue = RecurrentSessionQueue([word], enable_shuffling=False)
    requeued = queue.handle_result(updated, SRSGrade.HARD)
    assert requeued is True


def test_early_review_hard_on_review_card_lapse():
    """
    Test that an early review on a graduated review card (elapsed < 0.5 * stability)
    with HARD rating is treated as an acute lapse / fragile memory, resetting to
    relearning with 10m interval rather than expanding stability.
    """
    now = datetime(2026, 9, 7, 12, 0, 0, tzinfo=timezone.utc)
    word = Word(
        id=72,
        group_id=1,
        word="dopamine",
        definition="pleasure neurotransmitter",
        state=CardState.REVIEW.value,
        interval_days=14.0,
        stability=14.0,
        difficulty=4.5,
        last_reviewed=(now - timedelta(days=2)).isoformat(),  # 2 days << 7 days (0.5 * 14)
        is_placeholder=False
    )

    updated, scheduled_days = SRSEngine.calculate_next_state(
        word, SRSGrade.HARD, thought_time_seconds=5.0, now=now, apply_fuzz=False
    )

    assert updated.state == CardState.RELEARNING.value
    assert scheduled_days == pytest.approx(10.0 / 1440.0)
    assert updated.reps == 0
    assert updated.lapses == 1
    assert updated.stability < 14.0


def test_universal_formula_compound_placeholder_unfamiliar_grades():
    """
    Test UniversalSRSFormula.compound_placeholder_memory specifically handling
    AGAIN and HARD as post-lapse collapsed stability and 10m intervals,
    while GOOD compounds memory.
    """
    # AGAIN
    stab_again, int_again = UniversalSRSFormula.compound_placeholder_memory(
        stability=10.0, difficulty=5.0, elapsed_days=2.0, grade=SRSGrade.AGAIN
    )
    assert int_again == pytest.approx(10.0 / 1440.0, rel=1e-4)
    assert stab_again < 2.0

    # HARD
    stab_hard, int_hard = UniversalSRSFormula.compound_placeholder_memory(
        stability=10.0, difficulty=5.0, elapsed_days=2.0, grade=SRSGrade.HARD
    )
    assert int_hard == pytest.approx(10.0 / 1440.0, rel=1e-4)
    assert stab_hard < 5.0

    # GOOD
    stab_good, int_good = UniversalSRSFormula.compound_placeholder_memory(
        stability=10.0, difficulty=5.0, elapsed_days=2.0, grade=SRSGrade.GOOD
    )
    assert stab_good > 10.0
    assert int_good > 10.0


def test_universal_formula_from_entries_with_early_hard():
    """
    Test historical entries replay where an early review entry has HARD rating:
    must enter RELEARNING with 10m interval.
    """
    t0 = datetime(2026, 9, 1, 10, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(minutes=15)
    t2 = t0 + timedelta(days=1)  # Graduated to review with ~2.5d stability
    t3 = t0 + timedelta(days=1, hours=3)  # Early review 3 hours later, rated HARD!

    entries = [
        {"grade": int(SRSGrade.GOOD), "thought_time_seconds": 2.0, "reviewed_at": t0.isoformat()},
        {"grade": int(SRSGrade.GOOD), "thought_time_seconds": 2.0, "reviewed_at": t1.isoformat()},
        {"grade": int(SRSGrade.GOOD), "thought_time_seconds": 2.0, "reviewed_at": t2.isoformat()},
        {"grade": int(SRSGrade.HARD), "thought_time_seconds": 8.0, "reviewed_at": t3.isoformat()},
    ]

    now = t3 + timedelta(minutes=1)
    res = UniversalSRSFormula.calculate_from_entries(entries, current_time=now)

    assert res["state"] == CardState.RELEARNING.value
    assert res["lapses"] == 1
    assert res["interval_days"] == pytest.approx(10.0 / 1440.0, abs=1e-3)


def test_brain_capacity_calculation():
    """Test brain capacity scoring based on linear projection from word difficulty."""
    # 1. Brand new word takes high capacity (20)
    new_word = Word(id=1, group_id=1, word="ephemeral", definition="short-lived", state=CardState.NEW.value)
    assert new_word.brain_capacity == 20
    assert SRSEngine.calculate_brain_capacity(new_word) == 20

    # 2. Mastered, fluent review card (difficulty 2.0) -> capacity 2
    easy_word = Word(
        id=2, group_id=1, word="apple", definition="fruit",
        state=CardState.REVIEW.value, difficulty=2.0, reps=6, lapses=0, stability=45.0, avg_thought_time=1.5
    )
    assert easy_word.brain_capacity == 2
    assert Word.difficulty_to_capacity(2.0) == 2

    # 3. Standard review card (difficulty 5.0) -> capacity 5
    norm_word = Word(
        id=3, group_id=1, word="concept", definition="idea",
        state=CardState.REVIEW.value, difficulty=5.0, reps=3, lapses=0, stability=10.0, avg_thought_time=3.5
    )
    assert 3 <= norm_word.brain_capacity <= 5
    assert norm_word.brain_capacity == 5
    assert Word.difficulty_to_capacity(5.0) == 5

    # 4. Difficult card (difficulty 8.5) -> capacity 9
    hard_word = Word(
        id=4, group_id=1, word="perspicacious", definition="shrewd",
        state=CardState.REVIEW.value, difficulty=8.5, reps=1, lapses=3, stability=1.0, avg_thought_time=11.5
    )
    assert hard_word.brain_capacity == 9
    assert Word.difficulty_to_capacity(8.5) == 9

    # 5. Relearning word with difficulty 7.0 -> capacity 7
    relearn_word = Word(
        id=5, group_id=1, word="esoteric", definition="obscure",
        state=CardState.RELEARNING.value, difficulty=7.0, lapses=2
    )
    assert relearn_word.brain_capacity == 7

    # 6. Clamping bounds [1, 20] and custom linear slope/intercept
    assert Word.difficulty_to_capacity(0.5) == 1
    assert Word.difficulty_to_capacity(25.0) == 20
    assert Word.difficulty_to_capacity(5.0, slope=1.5, intercept=1.0) == 9  # 1.5*5 + 1 = 8.5 -> 9


def test_rate_session_quality_normalized_by_difficulty():
    """
    Test rate_session_quality evaluates mastery repetitions normalized by word difficulty:
    - 1 repetition on hard words yields higher quality than 1 repetition on easy words.
    - High repetitions on easy words indicates severe struggle.
    """
    from vocab.srs import rate_session_quality

    # Case A: 4 words with average difficulty 5.0 (expected reps ~ 1.4 each)
    # User masters all 4 in 1 repetition! Total reps = 4 vs expected 5.6.
    words_a = [
        Word(id=1, group_id=1, word=f"w{i}", definition=f"d{i}", difficulty=5.0)
        for i in range(4)
    ]
    reps_a = {1: 1, 2: 1, 3: 1, 4: 1}
    q_a = rate_session_quality(words=words_a, repetitions_map=reps_a)
    assert q_a["avg_repetitions"] == 1.0
    assert q_a["avg_difficulty"] == 5.0
    assert q_a["normalized_repetitions"] < 1.0  # Finished faster than expected
    assert q_a["quality_score"] > 1.20  # Exceptional rating
    assert q_a["quality_tier"] == "Exceptional"

    # Case B: 4 easy words (difficulty 1.0, expected 1.0 rep each), but user needed 3 reps each!
    words_b = [
        Word(id=10 + i, group_id=1, word=f"easy{i}", definition=f"d{i}", difficulty=1.0)
        for i in range(4)
    ]
    reps_b = {10: 3, 11: 3, 12: 3, 13: 3}
    q_b = rate_session_quality(words=words_b, repetitions_map=reps_b)
    assert q_b["avg_repetitions"] == 3.0
    assert q_b["avg_difficulty"] == 1.0
    assert q_b["normalized_repetitions"] == pytest.approx(3.0 / 1.0, abs=0.01)
    assert q_b["quality_score"] < 0.50  # Very low quality
    assert q_b["quality_tier"] == "Struggling"

    # Case C: 4 very hard words (difficulty 9.0, expected ~ 1.8 reps each), user needed 2 reps each
    words_c = [
        Word(id=20 + i, group_id=1, word=f"hard{i}", definition=f"d{i}", difficulty=9.0)
        for i in range(4)
    ]
    reps_c = {20: 2, 21: 2, 22: 2, 23: 2}
    q_c = rate_session_quality(words=words_c, repetitions_map=reps_c)
    assert q_c["avg_repetitions"] == 2.0
    # Needing 2 reps on hard words is close to expected (1.8), so normalized is ~1.11, not a severe penalty!
    assert 0.85 <= q_c["quality_score"] <= 1.0


def test_rate_session_quality_integration_with_queue():
    """
    Test rate_session_quality directly consuming a RecurrentSessionQueue
    tracking completed words and recurrent re-queue attempts.
    """
    w1 = Word(id=1, group_id=1, word="swift", definition="fast", difficulty=3.0)
    w2 = Word(id=2, group_id=1, word="arduous", definition="difficult", difficulty=8.0)

    queue = RecurrentSessionQueue([w1, w2], enable_shuffling=False)

    # Word 1: passes on first try -> 1 presentation (0 requeues)
    card1 = queue.next_card()
    queue.handle_result(card1, grade=SRSGrade.GOOD)

    # Word 2: fails first try (re-queued), then passes on second try -> 2 presentations (1 requeue)
    card2 = queue.next_card()
    queue.handle_result(card2, grade=SRSGrade.AGAIN)
    assert len(queue.queue) == 1
    card2_retry = queue.next_card()
    queue.handle_result(card2_retry, grade=SRSGrade.GOOD)

    assert queue.is_empty
    assert len(queue.completed_words) == 2

    quality = SRSEngine.rate_session_quality(queue=queue)
    assert quality["unique_words"] == 2
    assert quality["total_repetitions"] == 3  # w1=1 rep, w2=2 reps
    assert quality["avg_repetitions"] == 1.5
    assert quality["total_load"] == w1.brain_capacity + w2.brain_capacity
    assert quality["quality_score"] > 0.0


def test_tune_capacity_threshold_load_vs_quality():
    """
    Test tuning adaptive brain capacity limit based on load vs. quality comparison:
    - High load + high quality -> expand threshold
    - High load + low quality -> contract threshold
    - Low load -> dampened adjustments
    """
    from vocab.srs import tune_capacity_threshold

    # 1. High load (90 / 100) and high quality (1.30) -> threshold expands (+4 to +6)
    res_high = tune_capacity_threshold(current_threshold=100, session_load=90, quality_score=1.30)
    assert res_high["delta"] > 0
    assert res_high["new_threshold"] > 100
    assert "Expanded" in res_high["reason"]

    # 2. High load (90 / 100) and low quality (0.65) -> threshold contracts (-4 to -7)
    res_low = tune_capacity_threshold(current_threshold=100, session_load=90, quality_score=0.65)
    assert res_low["delta"] < 0
    assert res_low["new_threshold"] < 100
    assert "Contracted" in res_low["reason"]

    # 3. Tiny session load (5 / 100, e.g. 1 card) -> dampened delta (0)
    res_tiny = tune_capacity_threshold(current_threshold=100, session_load=5, quality_score=1.50)
    assert abs(res_tiny["delta"]) <= 1

    # 4. Zero load -> no adjustment
    res_zero = tune_capacity_threshold(current_threshold=100, session_load=0, quality_score=1.0)
    assert res_zero["delta"] == 0
    assert res_zero["new_threshold"] == 100

    # 5. Clamping bounds [60, 160]
    res_clamp_high = tune_capacity_threshold(current_threshold=158, session_load=150, quality_score=1.5, max_threshold=160)
    assert res_clamp_high["new_threshold"] == 160

    res_clamp_low = tune_capacity_threshold(current_threshold=62, session_load=60, quality_score=0.4, min_threshold=60)
    assert res_clamp_low["new_threshold"] == 60


def test_db_tune_capacity_threshold_integration():
    """
    Test Database.tune_capacity_threshold persists tuned limit in settings
    and get_adaptive_capacity_limit reads the calibrated threshold.
    """
    import tempfile
    import os
    from vocab.db import Database

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        temp_db = Database(db_path)
        gid = temp_db.create_group("Tune Deck")

        # Baseline before tuning
        base_cap = temp_db.get_adaptive_capacity_limit(group_id=gid)
        assert base_cap == 100

        # High load + High quality session -> expands capacity
        res = temp_db.tune_capacity_threshold(load=90, quality_score=1.30, group_id=gid)
        assert res["delta"] > 0
        new_cap = res["new_threshold"]

        # get_adaptive_capacity_limit should now return new_cap!
        assert temp_db.get_adaptive_capacity_limit(group_id=gid) == new_cap
        assert temp_db.get_setting(f"capacity_threshold_{gid}") == str(new_cap)

        # Log some reviews that produce a dynamic modifier
        wid = temp_db.add_word(group_id=gid, word="testword", definition="def")
        for _ in range(10):
            temp_db.log_review(word_id=wid, grade=2, review_mode="flashcard", scheduled_days=1.0, thought_time_seconds=5.0)

        # Subsequent tuning should tune from base setting (new_cap), not double-count dynamic review adjustments
        res2 = temp_db.tune_capacity_threshold(load=90, quality_score=1.30, group_id=gid)
        assert res2["previous_threshold"] == new_cap
        assert res2["new_threshold"] > new_cap
        assert temp_db.get_setting(f"capacity_threshold_{gid}") == str(res2["new_threshold"])
    finally:
        if os.path.exists(db_path):
            try:
                os.remove(db_path)
            except Exception:
                pass


def test_session_capacity_cap_and_new_words_limit():
    """Test that session words strictly honor max 100 brain capacity and do not flood with new words."""
    import tempfile
    import os
    from vocab.db import Database

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        db = Database(db_path)
        gid = db.create_group("Capacity Deck")

        # Add 10 new words (each takes 20 capacity)
        for i in range(10):
            db.add_word(group_id=gid, word=f"newword{i}", definition=f"def{i}")

        # Request session: 10 new words would be 200 capacity, so only 5 can fit (5 * 20 = 100)
        session_words = db.get_session_words(group_id=gid, limit=20, max_capacity=100)
        total_capacity = sum(w.brain_capacity for w in session_words)

        assert len(session_words) == 5
        assert total_capacity == 100
        assert all(w.state == CardState.NEW.value for w in session_words)

        # Now add 5 review words that take ~4 capacity each (~20 capacity total)
        now = datetime.now(timezone.utc)
        for i in range(5):
            wid = db.add_word(group_id=gid, word=f"reviewword{i}", definition=f"rdef{i}")
            w_obj = db.get_word_by_id(wid)
            w_obj.state = CardState.REVIEW.value
            w_obj.due_date = (now - timedelta(hours=1)).isoformat()
            w_obj.difficulty = 4.0
            w_obj.reps = 3
            w_obj.stability = 15.0
            db.update_word(w_obj)

        # Review words take priority over new words.
        # 5 reviews * ~4 capacity = ~20 capacity.
        # Remaining capacity = ~80. Exactly 4 new words (4 * 20 = 80) can fit!
        mixed_session = db.get_session_words(group_id=gid, limit=20, max_capacity=100)
        mixed_capacity = sum(w.brain_capacity for w in mixed_session)

        review_in_session = [w for w in mixed_session if w.state == CardState.REVIEW.value]
        new_in_session = [w for w in mixed_session if w.state == CardState.NEW.value]

        assert len(review_in_session) == 5
        assert len(new_in_session) == 4
        assert mixed_capacity <= 100
    finally:
        if os.path.exists(db_path):
            try:
                os.remove(db_path)
            except Exception:
                pass


def test_flashcard_session_new_word_skips_1_to_4_rating():
    """Test that reviewing a new card in flashcard session does not prompt for 1-4 rating."""
    import tempfile
    import os
    from unittest.mock import patch
    from vocab.db import Database
    from vocab.sessions.flashcard_session import run_flashcard_session

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        db = Database(db_path)
        gid = db.create_group("New Word Session")
        wid = db.add_word(group_id=gid, word="sonder", definition="realization that each passerby has a life as vivid as your own")

        # When the card front is shown, user presses Enter ("").
        # If the rank screen were shown, it would wait for "1-4" input.
        # But for new words, it must immediately transition to LEARNING and not ask for 1-4!
        # Then next card in queue is the requeued learning card: user presses 'q' to exit.
        user_inputs = ["", "q"]

        def mock_input(*args, **kwargs):
            if user_inputs:
                return user_inputs.pop(0)
            return "q"

        with patch("builtins.input", side_effect=mock_input):
            run_flashcard_session(db, group_id=gid, limit=5)

        updated_card = db.get_word_by_id(wid)
        assert updated_card is not None
        # Word has transitioned from NEW to LEARNING
        assert updated_card.state == CardState.LEARNING.value
    finally:
        if os.path.exists(db_path):
            try:
                os.remove(db_path)
            except Exception:
                pass


def test_adaptive_capacity_limit_default_and_fallback():
    """Test adaptive capacity returns 100 when review data is insufficient."""
    import tempfile
    import os
    from vocab.db import Database

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        db = Database(db_path)
        gid = db.create_group("Test Deck")
        wid = db.add_word(group_id=gid, word="test", definition="test def")

        # 0 reviews -> 100
        assert db.get_adaptive_capacity_limit() == 100
        assert db.get_adaptive_capacity_limit(group_id=gid) == 100

        # 4 reviews (< 5) -> still 100
        for i in range(4):
            db.log_review(
                word_id=wid,
                grade=3,
                review_mode="flashcard",
                scheduled_days=1.0,
                thought_time_seconds=2.0
            )
        assert db.get_adaptive_capacity_limit() == 100
        assert db.get_adaptive_capacity_limit(group_id=gid) == 100
    finally:
        if os.path.exists(db_path):
            try:
                os.remove(db_path)
            except Exception:
                pass


def test_adaptive_capacity_high_vs_low_performance():
    """Test that adaptive capacity increases on high performance and decreases on low performance."""
    import tempfile
    import os
    from vocab.db import Database

    # High performance test
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path_high = f.name
    try:
        db_high = Database(db_path_high)
        gid = db_high.create_group("High Deck")
        wid = db_high.add_word(group_id=gid, word="highword", definition="def")

        # 20 high-quality reviews: all Good (3) or Easy (4), thought time 1.5s
        for _ in range(20):
            db_high.log_review(
                word_id=wid,
                grade=3,
                review_mode="flashcard",
                scheduled_days=2.0,
                thought_time_seconds=1.5
            )

        high_cap = db_high.get_adaptive_capacity_limit()
        # Should expand beyond baseline 100, up to 140
        assert high_cap > 100
        assert high_cap <= 140
    finally:
        if os.path.exists(db_path_high):
            try:
                os.remove(db_path_high)
            except Exception:
                pass

    # Low performance test
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path_low = f.name
    try:
        db_low = Database(db_path_low)
        gid = db_low.create_group("Low Deck")
        wid = db_low.add_word(group_id=gid, word="lowword", definition="def")

        # 20 low-quality reviews: all Again (1), thought time 8.0s
        for _ in range(20):
            db_low.log_review(
                word_id=wid,
                grade=1,
                review_mode="flashcard",
                scheduled_days=0.0,
                thought_time_seconds=8.0
            )

        low_cap = db_low.get_adaptive_capacity_limit()
        # Should contract below baseline 100 down towards 60
        assert low_cap < 100
        assert low_cap >= 60
    finally:
        if os.path.exists(db_path_low):
            try:
                os.remove(db_path_low)
            except Exception:
                pass


def test_get_session_words_adapts_to_user_performance():
    """Test that get_session_words automatically throttles or expands new words based on performance."""
    import tempfile
    import os
    from vocab.db import Database

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        db = Database(db_path)
        gid = db.create_group("Adaptive Deck")
        wid = db.add_word(group_id=gid, word="anchor", definition="anchor def")

        # 10 new words (each takes 20 capacity)
        for i in range(10):
            db.add_word(group_id=gid, word=f"newword{i}", definition=f"def{i}")

        # Simulate poor performance: 15 reviews with grade 1 (Again), thought time 9.0s
        for _ in range(15):
            db.log_review(
                word_id=wid,
                grade=1,
                review_mode="flashcard",
                scheduled_days=0.0,
                thought_time_seconds=9.0
            )

        # Capacity should be clamped to 60.
        # Each new word is 20 capacity, so 60 / 20 = 3 new words can fit.
        low_session = db.get_session_words(group_id=gid, limit=10)
        assert len(low_session) == 3

        # Now simulate stellar performance: 50 reviews with grade 4 (Easy), thought time 1.0s
        for _ in range(50):
            db.log_review(
                word_id=wid,
                grade=4,
                review_mode="flashcard",
                scheduled_days=5.0,
                thought_time_seconds=1.0
            )

        # High performance should expand capacity (>= 120), allowing 6 new words (6 * 20 = 120 <= 140)
        high_cap = db.get_adaptive_capacity_limit()
        assert high_cap >= 120
        high_session = db.get_session_words(group_id=gid, limit=10)
        assert len(high_session) >= 6
    finally:
        if os.path.exists(db_path):
            try:
                os.remove(db_path)
            except Exception:
                pass


def test_card_views_do_not_render_capacity_numbers():
    """Verify that render_flashcard_front and render_flashcard_back do not display capacity numbers."""
    from io import StringIO
    from rich.console import Console
    from vocab.ui import card_views
    from vocab.models import Word

    test_word = Word(
        id=1,
        group_id=1,
        word="quintessential",
        definition="representing the most perfect or typical example of a quality or class",
        state="new"
    )

    capture_console = Console(file=StringIO(), force_terminal=True, width=80)
    orig_console = card_views.console
    try:
        card_views.console = capture_console

        # Render front
        card_views.render_flashcard_front(test_word, queue_index=1, queue_total=5)
        front_output = capture_console.file.getvalue()
        assert "Capacity" not in front_output
        assert "capacity" not in front_output
        assert "/100" not in front_output

        # Clear buffer and render back
        capture_console.file = StringIO()
        card_views.render_flashcard_back(test_word, queue_index=1, queue_total=5)
        back_output = capture_console.file.getvalue()
        assert "Capacity" not in back_output
        assert "capacity" not in back_output
        assert "/100" not in back_output
    finally:
        card_views.console = orig_console


def test_anti_pairing_two_cards():
    """
    Test that for a 2-card set, RecurrentSessionQueue avoids generating the exact same pair (w1, w2)
    when the previous sequence was [w1, w2].
    """
    RecurrentSessionQueue.clear_recent_history()
    w1 = Word(id=101, group_id=1, word="card_a", definition="def_a", state="review")
    w2 = Word(id=102, group_id=1, word="card_b", definition="def_b", state="review")

    # When previous sequence was [w1, w2]
    q = RecurrentSessionQueue([w1, w2], enable_shuffling=True, previous_sequence=[w1, w2])
    seq = [q.next_card().id for _ in range(2)]

    # Must be [102, 101] to eliminate the forward pair (101, 102)
    assert seq == [102, 101]


def test_anti_pairing_three_cards():
    """
    Test that for a 3-card set [w1, w2, w3], previous pairs (w1, w2) and (w2, w3)
    are eliminated in the newly generated sequence.
    """
    RecurrentSessionQueue.clear_recent_history()
    w1 = Word(id=1, group_id=1, word="alpha", definition="d1", state="review")
    w2 = Word(id=2, group_id=1, word="beta", definition="d2", state="review")
    w3 = Word(id=3, group_id=1, word="gamma", definition="d3", state="review")

    q = RecurrentSessionQueue([w1, w2, w3], enable_shuffling=True, previous_sequence=[1, 2, 3])
    seq = [q.next_card().id for _ in range(3)]

    # In sequence [1, 2, 3], forward pairs are (1, 2) and (2, 3).
    # In the generated sequence, none of these forward pairs should repeat.
    generated_pairs = {(seq[0], seq[1]), (seq[1], seq[2])}
    assert (1, 2) not in generated_pairs
    assert (2, 3) not in generated_pairs


def test_anti_pairing_reduces_pair_overlap_across_multiple_sessions():
    """
    Test that across multiple consecutive sessions, card sequence generation
    actively avoids repeated adjacent pairs (pairs of 2) from the preceding session.
    """
    RecurrentSessionQueue.clear_recent_history()
    words = [
        Word(id=i, group_id=1, word=f"w_{i}", definition=f"d_{i}", state="review")
        for i in range(1, 7)
    ]

    prev_seq = [w.id for w in words]
    pair_collisions_total = 0

    for _ in range(15):
        q = RecurrentSessionQueue(words, enable_shuffling=True, previous_sequence=prev_seq)
        curr_seq = []
        while not q.is_empty:
            curr_seq.append(q.next_card().id)

        # Count forward pair collisions between curr_seq and prev_seq
        prev_pairs = {(prev_seq[i], prev_seq[i + 1]) for i in range(len(prev_seq) - 1)}
        curr_pairs = {(curr_seq[i], curr_seq[i + 1]) for i in range(len(curr_seq) - 1)}

        overlap = curr_pairs.intersection(prev_pairs)
        pair_collisions_total += len(overlap)
        prev_seq = curr_seq

    # Across 15 sessions of 6 cards, naive random shuffle would yield ~15 pair collisions.
    # Our de-biasing algorithm should keep total collisions near 0.
    assert pair_collisions_total <= 3, f"Expected minimal pair collisions, got {pair_collisions_total}"


def test_intra_session_requeue_anti_pairing():
    """
    Test that when two consecutive cards fail in an active session,
    re-inserting them does not place them adjacent to each other as a pair again.
    """
    words = [
        Word(id=i, group_id=1, word=f"card_{i}", definition=f"def_{i}", state="review")
        for i in range(1, 9)
    ]

    for _ in range(20):
        q = RecurrentSessionQueue(words, enable_shuffling=True)
        # Card 1 popped and failed
        c1 = q.next_card()
        assert c1 is not None
        q.handle_result(c1, SRSGrade.AGAIN)

        # Card 2 popped immediately after Card 1 (they were an adjacent pair!)
        c2 = q.next_card()
        assert c2 is not None
        q.handle_result(c2, SRSGrade.AGAIN)

        # Find positions of c1 and c2 in the queue
        pos1 = next(i for i, w in enumerate(q.queue) if w.id == c1.id)
        pos2 = next(i for i, w in enumerate(q.queue) if w.id == c2.id)

        # c1 and c2 should NOT be adjacent in the queue (distance > 1)
        assert abs(pos1 - pos2) > 1, f"Failed consecutive cards re-inserted adjacent at {pos1} and {pos2}"


def test_database_recent_review_sequence_integration():
    """
    Test retrieving recent review sequence from Database and passing into RecurrentSessionQueue.
    """
    import os
    import tempfile
    from vocab.db import Database

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        temp_db = Database(db_path)
        gid = temp_db.create_group("De-biasing Deck")
        w1_id = temp_db.add_word(gid, "synapse", "junction")
        w2_id = temp_db.add_word(gid, "neurotransmitter", "chemical")
        w3_id = temp_db.add_word(gid, "dendrite", "receiver")

        now = datetime(2026, 9, 8, 10, 0, 0, tzinfo=timezone.utc)
        temp_db.log_review(w1_id, int(SRSGrade.GOOD), "flashcard", 1.0, now=now)
        temp_db.log_review(w2_id, int(SRSGrade.GOOD), "flashcard", 1.0, now=now + timedelta(seconds=10))
        temp_db.log_review(w3_id, int(SRSGrade.GOOD), "flashcard", 1.0, now=now + timedelta(seconds=20))

        recent_ids = temp_db.get_recent_review_sequence(group_id=gid, limit=10)
        assert recent_ids == [w1_id, w2_id, w3_id]

        words = [
            temp_db.get_word_by_id(w1_id),
            temp_db.get_word_by_id(w2_id),
            temp_db.get_word_by_id(w3_id),
        ]

        q = RecurrentSessionQueue(words, enable_shuffling=True, previous_sequence=recent_ids)
        new_ids = [q.next_card().id for _ in range(3)]

        # New sequence must break the forward pairs (w1_id, w2_id) and (w2_id, w3_id)
        new_pairs = {(new_ids[0], new_ids[1]), (new_ids[1], new_ids[2])}
        assert (w1_id, w2_id) not in new_pairs
        assert (w2_id, w3_id) not in new_pairs
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def test_alternate_old_and_new_equal_sizes():
    """Test that equal numbers of old and new words alternate strictly 1-to-1."""
    old_words = [
        Word(id=i, group_id=1, word=f"old_{i}", definition=f"d_{i}", state="review")
        for i in range(1, 6)
    ]
    new_words = [
        Word(id=10 + i, group_id=1, word=f"new_{i}", definition=f"d_{i}", state="new")
        for i in range(1, 6)
    ]

    alternated = RecurrentSessionQueue._alternate_old_and_new(old_words, new_words, prefer_old_first=True)
    assert len(alternated) == 10

    # Strict 1:1 alternation: Old, New, Old, New, ...
    for idx, card in enumerate(alternated):
        if idx % 2 == 0:
            assert card.state == "review", f"Expected old card at index {idx}, got {card.word}"
        else:
            assert card.state == "new", f"Expected new card at index {idx}, got {card.word}"

    # Verify FIFO / relative order within each type is preserved
    assert [w.id for w in alternated if w.state == "review"] == [1, 2, 3, 4, 5]
    assert [w.id for w in alternated if w.state == "new"] == [11, 12, 13, 14, 15]


def test_alternate_old_and_new_unequal_sizes():
    """Test that unequal sets of cards distribute minority cards uniformly without clustering."""
    # 8 old words, 2 new words
    old_words = [
        Word(id=i, group_id=1, word=f"old_{i}", definition=f"d_{i}", state="review")
        for i in range(1, 9)
    ]
    new_words = [
        Word(id=100 + i, group_id=1, word=f"new_{i}", definition=f"d_{i}", state="new")
        for i in range(1, 3)
    ]

    res = RecurrentSessionQueue._alternate_old_and_new(old_words, new_words, prefer_old_first=True)
    assert len(res) == 10

    # New cards must never be adjacent (no pile-up)
    new_indices = [i for i, w in enumerate(res) if w.state == "new"]
    assert len(new_indices) == 2
    assert abs(new_indices[1] - new_indices[0]) >= 3  # Well spaced across the 10 slots

    # Reverse: 2 old words, 8 new words
    res2 = RecurrentSessionQueue._alternate_old_and_new(old_words[:2], new_words[:2] + [
        Word(id=200 + i, group_id=1, word=f"new_extra_{i}", definition="d", state="new")
        for i in range(6)
    ], prefer_old_first=True)
    assert len(res2) == 10
    old_indices = [i for i, w in enumerate(res2) if w.state == "review"]
    assert len(old_indices) == 2
    assert abs(old_indices[1] - old_indices[0]) >= 3


def test_recurrent_session_queue_alternates_mixed_session():
    """Test that a mixed session in RecurrentSessionQueue pops new and old cards alternately."""
    words = [
        Word(id=1, group_id=1, word="old_1", definition="d1", state="review"),
        Word(id=2, group_id=1, word="old_2", definition="d2", state="review"),
        Word(id=3, group_id=1, word="old_3", definition="d3", state="review"),
        Word(id=4, group_id=1, word="new_1", definition="d4", state="new"),
        Word(id=5, group_id=1, word="new_2", definition="d5", state="new"),
        Word(id=6, group_id=1, word="new_3", definition="d6", state="new"),
    ]

    queue = RecurrentSessionQueue(words, enable_shuffling=True)
    assert queue.remaining_count == 6

    popped = []
    while not queue.is_empty:
        popped.append(queue.next_card())

    states = [w.state for w in popped]
    # In equal 3-and-3 mix, states must alternate: review, new, review, new, review, new
    assert states == ["review", "new", "review", "new", "review", "new"]


def test_recurrent_session_queue_preserves_urgency_while_alternating():
    """
    Test that critically overdue reviews precede normal due reviews,
    while still alternating with new learning cards.
    """
    now = datetime.now(timezone.utc)
    # Overdue review: retrievability < 0.85
    w_overdue = Word(
        id=1, group_id=1, word="overdue_card", definition="d1",
        state="review", due_date=(now - timedelta(days=10)).isoformat(), stability=1.0
    )
    # Normal due today review: retrievability >= 0.85
    w_due = Word(
        id=2, group_id=1, word="due_card", definition="d2",
        state="review", due_date=(now - timedelta(hours=1)).isoformat(), stability=30.0
    )
    w_new1 = Word(id=3, group_id=1, word="new_1", definition="d3", state="new")
    w_new2 = Word(id=4, group_id=1, word="new_2", definition="d4", state="new")

    queue = RecurrentSessionQueue([w_due, w_new1, w_overdue, w_new2], enable_shuffling=True)
    popped = []
    while not queue.is_empty:
        popped.append(queue.next_card())

    # First card should be overdue review (slot 0)
    assert popped[0].id == 1
    # Second card should be new (slot 1)
    assert popped[1].state == "new"
    # Third card should be due review (slot 2)
    assert popped[2].id == 2
    # Fourth card should be new (slot 3)
    assert popped[3].state == "new"


def test_recurrent_session_queue_shuffle_remaining_maintains_alternation():
    """Test that pressing shuffle during a session maintains alternation between old and new cards."""
    words = [
        Word(id=1, group_id=1, word="old_1", definition="d1", state="review"),
        Word(id=2, group_id=1, word="old_2", definition="d2", state="review"),
        Word(id=3, group_id=1, word="old_3", definition="d3", state="review"),
        Word(id=4, group_id=1, word="old_4", definition="d4", state="review"),
        Word(id=5, group_id=1, word="new_1", definition="d5", state="new"),
        Word(id=6, group_id=1, word="new_2", definition="d6", state="new"),
        Word(id=7, group_id=1, word="new_3", definition="d7", state="new"),
        Word(id=8, group_id=1, word="new_4", definition="d8", state="new"),
    ]

    queue = RecurrentSessionQueue(words, enable_shuffling=True)
    # Pop 2 cards
    c1 = queue.next_card()
    c2 = queue.next_card()
    assert c1.state == "review"
    assert c2.state == "new"

    # Shuffle remaining 6 cards
    count = queue.shuffle_remaining()
    assert count == 6

    # Remaining cards must alternate: review, new, review, new, review, new
    remaining_states = [queue.next_card().state for _ in range(6)]
    assert remaining_states == ["review", "new", "review", "new", "review", "new"]


def test_db_get_session_words_alternates_reviews_and_new():
    """Test that Database.get_session_words returns review and new words in alternating order."""
    import os
    from vocab.db import Database
    db_path = "test_alt_db.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    temp_db = Database(db_path)
    try:
        gid = temp_db.create_group("Alternating")
        now = datetime.now(timezone.utc)

        # Add 3 review words
        for i in range(1, 4):
            wid = temp_db.add_word(group_id=gid, word=f"rev_{i}", definition=f"d_{i}")
            w_obj = temp_db.get_word_by_id(wid)
            w_obj.state = CardState.REVIEW.value
            w_obj.due_date = (now - timedelta(hours=i)).isoformat()
            temp_db.update_word(w_obj)

        # Add 3 new words
        for i in range(1, 4):
            temp_db.add_word(group_id=gid, word=f"new_{i}", definition=f"d_{i}")

        session_words = temp_db.get_session_words(group_id=gid, limit=6, max_capacity=200)
        assert len(session_words) == 6

        # Check alternation
        states = [w.state for w in session_words]
        assert states == ["review", "new", "review", "new", "review", "new"]
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def test_cognitive_latency_errand_outlier_ignored():
    """
    Test that thought times exceeding the threshold (>30s) due to errands/distractions
    do NOT penalize the card's stability or inflate its difficulty rating.
    """
    from vocab.srs import MAX_VALID_THOUGHT_TIME, is_valid_thought_time

    assert is_valid_thought_time(2.5) is True
    assert is_valid_thought_time(15.0) is True
    assert is_valid_thought_time(30.0) is True
    assert is_valid_thought_time(30.1) is False
    assert is_valid_thought_time(75.35) is False
    assert is_valid_thought_time(0.0) is False
    assert is_valid_thought_time(-1.0) is False
    assert is_valid_thought_time(None) is False

    word = Word(
        id=142,
        group_id=1,
        word="destitution",
        definition="poverty",
        state=CardState.REVIEW.value,
        interval_days=10.0,
        stability=10.0,
        difficulty=5.0,
        reps=3,
        avg_thought_time=4.0,
        last_thought_time=3.5
    )

    # Standard review with 0.0s thought time
    standard, std_days = SRSEngine.calculate_next_state(word, SRSGrade.GOOD, thought_time_seconds=0.0, apply_fuzz=False)

    # Review where user got distracted by an errand for 75 seconds!
    outlier, out_days = SRSEngine.calculate_next_state(word, SRSGrade.GOOD, thought_time_seconds=75.35, apply_fuzz=False)

    # Review where user actually struggled for 15 seconds (valid hesitation)
    severe, sev_days = SRSEngine.calculate_next_state(word, SRSGrade.GOOD, thought_time_seconds=15.0, apply_fuzz=False)

    # Outlier (errand) should NOT be penalized: its stability should equal standard (1.0x latency multiplier)
    assert out_days == std_days
    assert outlier.difficulty == standard.difficulty
    assert outlier.difficulty < severe.difficulty
    assert out_days > sev_days

    # Outlier must NOT corrupt the card's avg_thought_time or last_thought_time
    assert outlier.avg_thought_time == 4.0
    assert outlier.last_thought_time == 3.5


def test_cognitive_latency_outlier_requeue_prevented():
    """
    Test that an errand distraction (>30s) does NOT cause a learning card to be
    re-queued when the user successfully recalled it (GOOD).
    """
    w1 = Word(id=50, group_id=1, word="synapse", definition="junction", state=CardState.LEARNING.value)
    queue = RecurrentSessionQueue([w1], enable_shuffling=False)

    c = queue.next_card()
    # User answered GOOD, but was away on an errand for 75s
    requeued = queue.handle_result(c, SRSGrade.GOOD, thought_time_seconds=75.0)
    assert requeued is False
    assert queue.remaining_count == 0


def test_universal_srs_formula_outlier_filtering():
    """
    Test that UniversalSRSFormula.calculate_from_entries ignores errand outliers (>30s)
    when computing average thought time and memory consolidation.
    """
    t0 = datetime(2026, 9, 1, 10, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(days=1)
    t2 = t0 + timedelta(days=3)

    entries = [
        {"grade": int(SRSGrade.GOOD), "thought_time_seconds": 2.0, "reviewed_at": t0.isoformat()},
        {"grade": int(SRSGrade.GOOD), "thought_time_seconds": 75.0, "reviewed_at": t1.isoformat()},  # Errand distraction!
        {"grade": int(SRSGrade.GOOD), "thought_time_seconds": 4.0, "reviewed_at": t2.isoformat()},
    ]

    res = UniversalSRSFormula.calculate_from_entries(entries, current_time=t0 + timedelta(days=4), apply_fuzz=False)

    # Average thought time must exclude the 75s errand: (2.0 + 4.0) / 2 = 3.0s
    assert res["avg_thought_time"] == pytest.approx(3.0, rel=1e-2)
    assert res["last_thought_time"] == pytest.approx(4.0, rel=1e-2)


def test_session_stats_outlier_tracking():
    """Test that SessionStats tracks outlier count and excludes them from average latency."""
    from vocab.models import SessionStats

    stats = SessionStats()
    stats.total_reviews = 3
    stats.timed_reviews = 2
    stats.total_thought_time = 6.0  # (2.0s + 4.0s)
    stats.fluent_count = 1
    stats.steady_count = 1
    stats.outlier_thought_count = 1  # 1 review had 75s errand

    assert stats.avg_thought_time == 3.0


def test_mastered_card_properties():
    """Test that a mastered card is never due, has 0 cognitive load, and low urgency."""
    card = Word(
        id=99,
        group_id=1,
        word="omnipresent",
        definition="present everywhere",
        state=CardState.MASTERED.value,
        interval_days=200.0,
        stability=150.0,
        reps=6,
    )
    assert card.is_due() is False
    assert card.brain_capacity == 0
    assert card.urgency_score() == -1000.0
    assert card.format_due_time() == "Mastered"


def test_is_mastery_eligible_criterion_a():
    """
    Criterion A: Card with reps >= 5 and (stability >= 100 or interval >= 180)
    qualifies for permanent mastery retirement.
    """
    # High stability, high reps
    w1 = Word(id=1, group_id=1, word="w1", definition="d1", reps=5, stability=100.0, interval_days=100.0)
    assert SRSEngine.is_mastery_eligible(w1) is True

    # High interval, high reps
    w2 = Word(id=2, group_id=1, word="w2", definition="d2", reps=6, stability=90.0, interval_days=180.0)
    assert SRSEngine.is_mastery_eligible(w2) is True

    # High stability but not enough reps (< 5) -> not eligible yet
    w3 = Word(id=3, group_id=1, word="w3", definition="d3", reps=4, stability=120.0, interval_days=190.0)
    assert SRSEngine.is_mastery_eligible(w3) is False

    # Enough reps but stability and interval both too low (< 100 and < 180) -> not eligible
    w4 = Word(id=4, group_id=1, word="w4", definition="d4", reps=7, stability=45.0, interval_days=50.0)
    assert SRSEngine.is_mastery_eligible(w4) is False


def test_is_mastery_eligible_criterion_b():
    """
    Criterion B: Card with reps >= 3 and 3 consecutive EASY reviews with
    rapid recall thought time (< 3.0s) qualifies for permanent mastery.
    """
    from vocab.models import ReviewLog

    card = Word(id=10, group_id=1, word="swift", definition="fast", reps=3, stability=20.0)

    # 3 consecutive EASY with thought times 1.2s, 1.5s, 0.8s (< 3.0s)
    logs_qualifying = [
        ReviewLog(id=1, word_id=10, grade=int(SRSGrade.EASY), review_mode="flashcard", scheduled_days=5.0, thought_time_seconds=1.2),
        ReviewLog(id=2, word_id=10, grade=int(SRSGrade.EASY), review_mode="flashcard", scheduled_days=10.0, thought_time_seconds=1.5),
        ReviewLog(id=3, word_id=10, grade=int(SRSGrade.EASY), review_mode="flashcard", scheduled_days=20.0, thought_time_seconds=0.8),
    ]
    assert SRSEngine.is_mastery_eligible(card, recent_logs=logs_qualifying) is True

    # Only 2 EASY reviews and 1 GOOD review -> not eligible under Criterion B
    logs_mixed_grade = [
        ReviewLog(id=1, word_id=10, grade=int(SRSGrade.EASY), review_mode="flashcard", scheduled_days=5.0, thought_time_seconds=1.2),
        ReviewLog(id=2, word_id=10, grade=int(SRSGrade.GOOD), review_mode="flashcard", scheduled_days=10.0, thought_time_seconds=1.5),
        ReviewLog(id=3, word_id=10, grade=int(SRSGrade.EASY), review_mode="flashcard", scheduled_days=20.0, thought_time_seconds=0.8),
    ]
    assert SRSEngine.is_mastery_eligible(card, recent_logs=logs_mixed_grade) is False

    # 3 EASY reviews but one was hesitant (thought time 4.5s >= 3.0s) -> not effortless, not eligible
    logs_slow_thought = [
        ReviewLog(id=1, word_id=10, grade=int(SRSGrade.EASY), review_mode="flashcard", scheduled_days=5.0, thought_time_seconds=1.2),
        ReviewLog(id=2, word_id=10, grade=int(SRSGrade.EASY), review_mode="flashcard", scheduled_days=10.0, thought_time_seconds=4.5),
        ReviewLog(id=3, word_id=10, grade=int(SRSGrade.EASY), review_mode="flashcard", scheduled_days=20.0, thought_time_seconds=0.8),
    ]
    assert SRSEngine.is_mastery_eligible(card, recent_logs=logs_slow_thought) is False


def test_calculate_next_state_criterion_a_triggers_mastery():
    """Test that calculate_next_state automatically sets state = 'mastered' when Criterion A is reached."""
    # Mature card on verge of mastery: reps=4 (will become 5), high stability (85d), review EASY
    card = Word(
        id=25,
        group_id=1,
        word="resilience",
        definition="ability to recover quickly",
        state=CardState.REVIEW.value,
        reps=4,
        stability=85.0,
        interval_days=85.0,
        difficulty=2.0
    )
    # Review with EASY grade and fast thought time
    updated, next_days = SRSEngine.calculate_next_state(card, SRSGrade.EASY, thought_time_seconds=1.5, apply_fuzz=False)
    assert updated.reps == 5
    assert updated.stability > 100.0
    assert updated.state == CardState.MASTERED.value






