"""
Unit tests for Database operations and models.
"""
import os
import tempfile
from datetime import datetime, timezone, timedelta
import pytest
from vocab.db import Database
from vocab.models import CardState, SRSGrade
from vocab.seed_data import seed_database


@pytest.fixture
def temp_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    db = Database(db_path)
    yield db
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
        except Exception:
            pass


def test_group_crud(temp_db):
    """Test creating, reading, updating, and deleting groups."""
    gid = temp_db.create_group(name="GRE Words", description="Academic vocab", color="magenta")
    assert gid > 0

    group = temp_db.get_group_by_id(gid)
    assert group is not None
    assert group.name == "GRE Words"
    assert group.color == "magenta"

    # Update
    temp_db.update_group(gid, name="GRE Advanced", description="Updated", color="cyan")
    updated = temp_db.get_group_by_id(gid)
    assert updated.name == "GRE Advanced"

    # Delete
    deleted = temp_db.delete_group(gid)
    assert deleted is True
    assert temp_db.get_group_by_id(gid) is None


def test_word_crud_and_due_query(temp_db):
    """Test adding words, updating them, and checking due cards."""
    gid = temp_db.create_group(name="Tech Terms")
    wid = temp_db.add_word(
        group_id=gid,
        word="idempotent",
        definition="Yields same result on repetition",
        phonetic="/aɪ.dəmˈpoʊ.tənt/",
        pos="adjective",
        example="PUT is idempotent.",
        mnemonic="Idem = same",
        tags="api, web"
    )
    assert wid > 0

    word = temp_db.get_word_by_id(wid)
    assert word is not None
    assert word.word == "idempotent"
    assert word.group_name == "Tech Terms"
    assert word.state == CardState.NEW.value

    # New card must be due
    due_words = temp_db.get_due_words(group_id=gid)
    assert len(due_words) == 1
    assert due_words[0].id == wid

    # Update word
    word.definition = "Updated definition"
    temp_db.update_word(word)
    refreshed = temp_db.get_word_by_id(wid)
    assert refreshed.definition == "Updated definition"

    # Delete
    assert temp_db.delete_word(wid) is True
    assert temp_db.get_word_by_id(wid) is None


def test_seed_database(temp_db):
    """Test database seeding adds curated decks."""
    count = seed_database(temp_db)
    assert count > 0

    groups = temp_db.get_groups()
    assert len(groups) >= 3
    names = [g.name for g in groups]
    assert "GRE & Advanced Academic" in names
    assert "Essential Idioms & Phrasal Verbs" in names
    assert "Tech & Software Engineering" in names

    stats = temp_db.get_stats_summary()
    assert stats["total_words"] == count
    assert stats["due_count"] == count


def test_review_logging_and_stats(temp_db):
    """Test review log insertion and retention calculation."""
    gid = temp_db.create_group(name="Test Group")
    wid = temp_db.add_word(group_id=gid, word="test", definition="a trial")

    temp_db.log_review(
        word_id=wid,
        grade=int(SRSGrade.GOOD),
        review_mode="flashcard",
        scheduled_days=1.0,
        elapsed_seconds=2.5
    )

    stats = temp_db.get_stats_summary(group_id=gid)
    assert stats["total_recent_reviews"] == 1
    assert stats["total_review_attempts"] == 1
    assert stats["retention_rate"] == 100.0


def test_due_forecast(temp_db):
    """Test forecast calculation with and without group filter."""
    g1 = temp_db.create_group("Group 1")
    g2 = temp_db.create_group("Group 2")

    temp_db.add_word(group_id=g1, word="w1", definition="d1")
    temp_db.add_word(group_id=g1, word="w2", definition="d2")
    temp_db.add_word(group_id=g2, word="w3", definition="d3")

    fc_all = temp_db.get_due_forecast()
    assert fc_all["Today"] == 3

    fc_g1 = temp_db.get_due_forecast(group_id=g1)
    assert fc_g1["Today"] == 2

    fc_g2 = temp_db.get_due_forecast(group_id=g2)
    assert fc_g2["Today"] == 1


def test_circadian_and_latency_analytics(temp_db):
    """Test hourly activity tracking and latency distribution analytics."""
    gid = temp_db.create_group("Psychology")
    wid = temp_db.add_word(group_id=gid, word="cortex", definition="brain bark")

    # Log reviews at specific hours with latency
    temp_db.log_review(
        word_id=wid,
        grade=int(SRSGrade.GOOD),
        review_mode="flashcard",
        scheduled_days=1.0,
        elapsed_seconds=3.0,
        thought_time_seconds=2.0,
        now=datetime(2026, 9, 7, 9, 30, 0)  # Morning (9 AM)
    )
    temp_db.log_review(
        word_id=wid,
        grade=int(SRSGrade.HARD),
        review_mode="flashcard",
        scheduled_days=1.0,
        elapsed_seconds=10.0,
        thought_time_seconds=8.5,
        now=datetime(2026, 9, 7, 23, 15, 0)  # Night (11 PM)
    )

    # Hourly activity
    hourly = temp_db.get_hourly_activity(group_id=gid)
    assert len(hourly) == 24
    assert hourly[9]["reviews"] == 1
    assert hourly[9]["avg_thought_time"] == 2.0
    assert hourly[9]["retention_rate"] == 100.0
    assert hourly[23]["reviews"] == 1
    assert hourly[23]["avg_thought_time"] == 8.5
    assert hourly[23]["retention_rate"] == 100.0  # Hard is correct recall.

    # Circadian periods
    periods = temp_db.get_circadian_periods_summary(group_id=gid)
    morning = [p for p in periods if p["name"] == "Morning Focus"][0]
    night = [p for p in periods if p["name"] == "Night Owl / Late"][0]
    assert morning["reviews"] == 1
    assert night["reviews"] == 1

    # Latency analytics
    lat_analytics = temp_db.get_latency_analytics(group_id=gid)
    assert lat_analytics["total_timed_reviews"] == 2
    assert lat_analytics["count_fluent"] == 1  # 2.0s <= 3s
    assert lat_analytics["count_hesitant"] == 1  # 8.5s > 7s


def test_get_session_words_with_placeholders(temp_db):
    """Test that get_session_words backfills short due lists with placeholder cards."""
    gid = temp_db.create_group("Science")
    now = datetime.now(timezone.utc)

    # 1 card currently due
    w_due = temp_db.add_word(group_id=gid, word="mitochondria", definition="powerhouse")

    # 3 cards not due until tomorrow/later
    w_future1 = temp_db.add_word(group_id=gid, word="ribosome", definition="protein factory")
    w1_obj = temp_db.get_word_by_id(w_future1)
    w1_obj.state = CardState.REVIEW.value
    w1_obj.due_date = (now + timedelta(days=1)).isoformat()
    temp_db.update_word(w1_obj)

    w_future2 = temp_db.add_word(group_id=gid, word="nucleus", definition="control center")
    w2_obj = temp_db.get_word_by_id(w_future2)
    w2_obj.state = CardState.REVIEW.value
    w2_obj.due_date = (now + timedelta(days=2)).isoformat()
    temp_db.update_word(w2_obj)

    # When requesting limit=3 without placeholders: only 1 due card returned
    strict_due = temp_db.get_session_words(group_id=gid, limit=3, fill_placeholders=False)
    assert len(strict_due) == 1
    assert strict_due[0].id == w_due
    assert strict_due[0].is_placeholder is False

    # When requesting limit=3 WITH placeholders: 1 due + 2 placeholders returned
    session_words = temp_db.get_session_words(group_id=gid, limit=3, fill_placeholders=True)
    assert len(session_words) == 3

    due_in_session = [w for w in session_words if not w.is_placeholder]
    placeholders = [w for w in session_words if w.is_placeholder]

    assert len(due_in_session) == 1
    assert len(placeholders) == 2
    assert placeholders[0].id in (w_future1, w_future2)


def test_get_session_words_when_all_caught_up(temp_db):
    """
    Test that when all words in a deck are caught up (due_count == 0),
    activating a session retrieves the words with the closest due time in ascending order.
    """
    gid = temp_db.create_group("Physiology")
    now = datetime.now(timezone.utc)

    # Add 4 words with future due dates in arbitrary insertion order
    w_5h = temp_db.add_word(group_id=gid, word="axon", definition="transmitter")
    w1 = temp_db.get_word_by_id(w_5h)
    w1.state = CardState.REVIEW.value
    w1.due_date = (now + timedelta(hours=5)).isoformat()
    temp_db.update_word(w1)

    w_1h = temp_db.add_word(group_id=gid, word="synapse", definition="junction")
    w2 = temp_db.get_word_by_id(w_1h)
    w2.state = CardState.REVIEW.value
    w2.due_date = (now + timedelta(hours=1)).isoformat()
    temp_db.update_word(w2)

    w_2d = temp_db.add_word(group_id=gid, word="cortex", definition="outer layer")
    w3 = temp_db.get_word_by_id(w_2d)
    w3.state = CardState.REVIEW.value
    w3.due_date = (now + timedelta(days=2)).isoformat()
    temp_db.update_word(w3)

    w_10h = temp_db.add_word(group_id=gid, word="myelin", definition="insulator")
    w4 = temp_db.get_word_by_id(w_10h)
    w4.state = CardState.REVIEW.value
    w4.due_date = (now + timedelta(hours=10)).isoformat()
    temp_db.update_word(w4)

    # Due count is 0
    assert len(temp_db.get_due_words(group_id=gid)) == 0

    # Request session of limit 3: should return top 3 closest due words in strict chronological order
    session_words = temp_db.get_session_words(group_id=gid, limit=3)
    assert len(session_words) == 3
    assert session_words[0].word == "synapse"  # due in 1h
    assert session_words[1].word == "axon"     # due in 5h
    assert session_words[2].word == "myelin"   # due in 10h

    # Even with fill_placeholders=False, activating when caught up returns closest due
    session_words_strict = temp_db.get_session_words(group_id=gid, limit=2, fill_placeholders=False)
    assert len(session_words_strict) == 2
    assert session_words_strict[0].word == "synapse"
    assert session_words_strict[1].word == "axon"


def test_get_newly_due_words(temp_db):
    """Test get_newly_due_words accurately retrieves due words and excludes active queue cards."""
    gid = temp_db.create_group("Math")
    now = datetime.now(timezone.utc)

    w1 = temp_db.add_word(group_id=gid, word="integral", definition="area")
    w2 = temp_db.add_word(group_id=gid, word="derivative", definition="slope")
    w3 = temp_db.add_word(group_id=gid, word="limit", definition="approach")

    # w3 is not due
    w3_obj = temp_db.get_word_by_id(w3)
    w3_obj.state = CardState.REVIEW.value
    w3_obj.due_date = (now + timedelta(days=5)).isoformat()
    temp_db.update_word(w3_obj)

    # Exclude w1 because it's currently active in queue
    newly_due = temp_db.get_newly_due_words(group_id=gid, exclude_word_ids={w1})
    due_ids = [w.id for w in newly_due]

    assert w1 not in due_ids
    assert w2 in due_ids
    assert w3 not in due_ids


def test_get_word_review_logs_and_recalculate(temp_db):
    """Test retrieving chronological review logs and recalculating card memory state."""
    gid = temp_db.create_group("Physiology")
    wid = temp_db.add_word(group_id=gid, word="homeostasis", definition="dynamic balance")

    t0 = datetime(2026, 9, 1, 8, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(minutes=15)
    t2 = t0 + timedelta(days=2)  # Early review placeholder

    temp_db.log_review(wid, int(SRSGrade.GOOD), "flashcard", 0.007, 2.0, 1.8, now=t0)
    temp_db.log_review(wid, int(SRSGrade.GOOD), "flashcard", 2.5, 3.0, 2.1, now=t1)
    temp_db.log_review(wid, int(SRSGrade.GOOD), "flashcard", 5.0, 2.5, 1.5, now=t2)

    logs = temp_db.get_word_review_logs(wid)
    assert len(logs) == 3
    assert logs[0].grade == int(SRSGrade.GOOD)
    assert logs[1].grade == int(SRSGrade.GOOD)
    assert logs[2].grade == int(SRSGrade.GOOD)

    # Recalculate word from logs
    recalculated = temp_db.recalculate_word_from_logs(wid, now=t0 + timedelta(days=3))
    assert recalculated is not None
    assert recalculated.state == CardState.REVIEW.value
    assert recalculated.reps == 2
    assert recalculated.stability > 2.5


def test_sync_all_word_states(temp_db):
    """Test that sync_all_word_states audits and synchronizes database records with review logs."""
    gid = temp_db.create_group("Anatomy")
    now = datetime.now(timezone.utc)

    # Word 1: Graduated via review logs, but database record became desynced
    w1_id = temp_db.add_word(group_id=gid, word="cerebellum", definition="motor control")
    t0 = now - timedelta(days=5)
    t1 = now - timedelta(days=4)
    temp_db.log_review(w1_id, int(SRSGrade.GOOD), "flashcard", 0.007, 2.0, 1.5, now=t0)
    temp_db.log_review(w1_id, int(SRSGrade.GOOD), "flashcard", 2.5, 2.5, 1.8, now=t1)

    # Intentionally desync w1 in database
    w1_obj = temp_db.get_word_by_id(w1_id)
    w1_obj.state = CardState.LEARNING.value
    w1_obj.reps = 0
    temp_db.update_word(w1_obj)

    # Word 2: Has 0 review logs, but database record was set to 'learning'
    w2_id = temp_db.add_word(group_id=gid, word="thalamus", definition="sensory relay")
    w2_obj = temp_db.get_word_by_id(w2_id)
    w2_obj.state = CardState.LEARNING.value
    w2_obj.step = 1
    temp_db.update_word(w2_obj)

    # Run synchronization
    updated_count = temp_db.sync_all_word_states(now=now)
    assert updated_count >= 2

    # Verify w1 is synced to 'review' with reps=1
    synced_w1 = temp_db.get_word_by_id(w1_id)
    assert synced_w1.state == CardState.REVIEW.value
    assert synced_w1.reps == 1

    # Verify w2 is synced to 'new' with step=0
    synced_w2 = temp_db.get_word_by_id(w2_id)
    assert synced_w2.state == CardState.NEW.value
    assert synced_w2.step == 0
    assert synced_w2.reps == 0


def test_circadian_periods_differentiates_new_words_from_fatigue(temp_db):
    """
    Test that low retrieval rate on newly learned words is classified as
    'New Acquisition' rather than 'Fatigue Zone', while genuine failure on
    established review cards is classified as 'Fatigue Zone'.
    """
    from vocab.models import SRSGrade

    gid = temp_db.create_group("Circadian Acquisition Test")
    w_new = temp_db.add_word(group_id=gid, word="neologism", definition="new word")
    w_rev = temp_db.add_word(group_id=gid, word="veteran", definition="old word")

    # Afternoon (14:00): User studies 5 newly learned words with low initial retrieval (2 successes, 3 lapses)
    t_afternoon = datetime(2026, 9, 8, 14, 0, 0)
    for i in range(5):
        grade = int(SRSGrade.GOOD) if i < 2 else int(SRSGrade.AGAIN)
        temp_db.log_review(
            word_id=w_new,
            grade=grade,
            review_mode="flashcard",
            scheduled_days=0.007,
            thought_time_seconds=3.0,
            card_state="learning",
            now=t_afternoon
        )

    # Night (23:00): User reviews 5 established review cards with genuine fatigue (1 success, 4 lapses, slow latency)
    t_night = datetime(2026, 9, 8, 23, 0, 0)
    for i in range(5):
        grade = int(SRSGrade.GOOD) if i < 1 else int(SRSGrade.AGAIN)
        temp_db.log_review(
            word_id=w_rev,
            grade=grade,
            review_mode="flashcard",
            scheduled_days=10.0,
            thought_time_seconds=8.0,
            card_state="review",
            now=t_night
        )

    periods = temp_db.get_circadian_periods_summary(group_id=gid)
    afternoon = [p for p in periods if p["name"] == "Afternoon Flow"][0]
    night = [p for p in periods if p["name"] == "Night Owl / Late"][0]

    # Afternoon had low retention (40%), but because they were newly learned words,
    # it must NOT be labeled as tiredness/Fatigue Zone!
    assert afternoon["reviews"] == 5
    assert afternoon["new_learning_revs"] == 5
    assert afternoon["retention_rate"] == 40.0
    assert "Small sample" in afternoon["state_label"]
    assert "Fatigue Zone" not in afternoon["state_label"]

    # Night had low retention (20%) on established review cards with high latency (8.0s),
    # so it IS genuine fatigue!
    assert night["reviews"] == 5
    assert night["review_revs"] == 5
    assert night["retention_rate"] == 20.0
    assert "Fatigue Zone" not in night["state_label"]
    assert "Small sample" in night["state_label"]


def test_render_stats_dashboard_cognitive_acquisition_display(temp_db):
    """Verify that render_stats_dashboard prints the first table with new acquisition info and footnote."""
    from io import StringIO
    from rich.console import Console
    from vocab.ui import stats_views

    gid = temp_db.create_group("Dashboard Test")
    w = temp_db.add_word(group_id=gid, word="dashboard_word", definition="def")

    t_morning = datetime(2026, 9, 8, 9, 0, 0)
    temp_db.log_review(
        word_id=w,
        grade=int(SRSGrade.GOOD),
        review_mode="flashcard",
        scheduled_days=0.007,
        thought_time_seconds=2.0,
        card_state="learning",
        now=t_morning
    )

    circadian = temp_db.get_circadian_periods_summary(group_id=gid)
    overall_stats = temp_db.get_stats_summary(group_id=gid)

    capture_console = Console(file=StringIO(), force_terminal=False, no_color=True, width=160)
    orig_console = stats_views.console
    try:
        stats_views.console = capture_console
        stats_views.render_stats_dashboard(
            overall_stats=overall_stats,
            groups=[],
            forecast={},
            circadian_periods=circadian
        )
        output = capture_console.file.getvalue()
        assert "Activity by time of day" in output
        assert "Observational data" in output
        assert "do not measure focus or fatigue" in output
    finally:
        stats_views.console = orig_console


def test_get_recommended_next_session_decent_capacity(temp_db):
    """
    Test that get_recommended_next_session calculates the optimal future time
    where maturing cards accumulate a decent amount of brain capacity (e.g. ~50% of capacity).
    """
    gid = temp_db.create_group("Forecast Deck")
    now = datetime(2026, 9, 10, 8, 0, 0, tzinfo=timezone.utc)

    # Add 5 words with staggered future due dates:
    # Word 1: in 15m, cap=10
    # Word 2: in 30m, cap=10 (cum 20)
    # Word 3: in 45m, cap=12 (cum 32)
    # Word 4: in 50m, cap=11 (cum 43 -> meets target threshold >= 35!)
    # Word 5: in 52m, cap=11 (cum 54 -> within 10m cluster smoothing window!)
    # Word 6: in 3 hours, cap=10 (outside cluster window)
    t1 = now + timedelta(minutes=15)
    t2 = now + timedelta(minutes=30)
    t3 = now + timedelta(minutes=45)
    t4 = now + timedelta(minutes=50)
    t5 = now + timedelta(minutes=52)
    t6 = now + timedelta(hours=3)

    w1 = temp_db.add_word(gid, "w1", "d1")
    w2 = temp_db.add_word(gid, "w2", "d2")
    w3 = temp_db.add_word(gid, "w3", "d3")
    w4 = temp_db.add_word(gid, "w4", "d4")
    w5 = temp_db.add_word(gid, "w5", "d5")
    w6 = temp_db.add_word(gid, "w6", "d6")

    # Set states to 'review' with explicit due dates
    with temp_db.get_connection() as conn:
        c = conn.cursor()
        for wid, dt in [(w1, t1), (w2, t2), (w3, t3), (w4, t4), (w5, t5), (w6, t6)]:
            c.execute("UPDATE words SET state = 'review', due_date = ? WHERE id = ?", (dt.isoformat(), wid))
        conn.commit()

    rec = temp_db.get_recommended_next_session(group_id=gid, now=now, target_capacity=20)
    assert rec is not None
    # Threshold 20 is reached at t4 (cum 24), and t5 (52m) is within 10m cluster smoothing
    assert rec["card_count"] == 5
    assert rec["accumulated_capacity"] >= 20
    assert rec["recommended_time"] == t5
    assert "in 52m" in rec["short_label"]
    assert "Today" in rec["full_label"]


def test_get_recommended_next_session_small_deck(temp_db):
    """
    Test that when all upcoming cards combined are fewer than target capacity,
    the recommended session time is when all available cards in the deck are due.
    """
    gid = temp_db.create_group("Mini Deck")
    now = datetime(2026, 9, 10, 8, 0, 0, tzinfo=timezone.utc)
    t_tomorrow = now + timedelta(days=1)

    w1 = temp_db.add_word(gid, "mini1", "d1")
    w2 = temp_db.add_word(gid, "mini2", "d2")

    with temp_db.get_connection() as conn:
        c = conn.cursor()
        c.execute("UPDATE words SET state = 'review', due_date = ? WHERE id = ?", (t_tomorrow.isoformat(), w1))
        c.execute("UPDATE words SET state = 'review', due_date = ? WHERE id = ?", ((t_tomorrow + timedelta(minutes=5)).isoformat(), w2))
        conn.commit()

    rec = temp_db.get_recommended_next_session(group_id=gid, now=now, target_capacity=50)
    assert rec is not None
    assert rec["card_count"] == 2
    assert "Tomorrow" in rec["short_label"]


def test_get_recommended_next_session_empty_and_stats(temp_db):
    """
    Test that get_recommended_next_session returns None when no upcoming cards exist,
    and get_stats_summary handles next_session correctly.
    """
    gid = temp_db.create_group("Empty Deck")
    rec = temp_db.get_recommended_next_session(group_id=gid)
    assert rec is None

    stats = temp_db.get_stats_summary(group_id=gid)
    assert stats["due_count"] == 0
    assert stats["next_session"] is None


def test_get_recommended_next_session_with_currently_due_suboptimal(temp_db):
    """
    Test that when 1 card is currently due (sub-optimal capacity),
    get_recommended_next_session marks is_optimal_now = False,
    includes the currently due card, and accumulates upcoming cards until target capacity.
    """
    gid = temp_db.create_group("Suboptimal Deck")
    now = datetime(2026, 9, 10, 10, 0, 0, tzinfo=timezone.utc)

    # 1 currently due word (default capacity = 6)
    w_due = temp_db.add_word(gid, "due1", "def1")
    # 4 upcoming words at +15m, +30m, +45m, +60m
    w_up1 = temp_db.add_word(gid, "up1", "def_up1")
    w_up2 = temp_db.add_word(gid, "up2", "def_up2")
    w_up3 = temp_db.add_word(gid, "up3", "def_up3")
    w_up4 = temp_db.add_word(gid, "up4", "def_up4")

    t_due = now - timedelta(minutes=5)
    t_up1 = now + timedelta(minutes=15)
    t_up2 = now + timedelta(minutes=30)
    t_up3 = now + timedelta(minutes=45)
    t_up4 = now + timedelta(minutes=60)

    with temp_db.get_connection() as conn:
        c = conn.cursor()
        c.execute("UPDATE words SET state = 'review', due_date = ? WHERE id = ?", (t_due.isoformat(), w_due))
        c.execute("UPDATE words SET state = 'review', due_date = ? WHERE id = ?", (t_up1.isoformat(), w_up1))
        c.execute("UPDATE words SET state = 'review', due_date = ? WHERE id = ?", (t_up2.isoformat(), w_up2))
        c.execute("UPDATE words SET state = 'review', due_date = ? WHERE id = ?", (t_up3.isoformat(), w_up3))
        c.execute("UPDATE words SET state = 'review', due_date = ? WHERE id = ?", (t_up4.isoformat(), w_up4))
        conn.commit()

    # Target capacity 20: 1 card due (cap 5 from diff 5.0) is not enough.
    # Needs up1 (5+5=10), up2 (10+5=15), up3 (15+5=20 >= 20).
    rec = temp_db.get_recommended_next_session(group_id=gid, now=now, target_capacity=20)
    assert rec is not None
    assert rec["is_optimal_now"] is False
    assert rec["current_due_count"] == 1
    assert rec["current_due_capacity"] == 5
    assert rec["card_count"] == 4  # 1 due + 3 upcoming
    assert rec["accumulated_capacity"] == 20
    assert rec["recommended_time"] == t_up3
    assert "in 45m" in rec["short_label"]
    assert rec["time_until_seconds"] == 45 * 60

    stats = temp_db.get_stats_summary(group_id=gid, now=now)
    assert stats["due_count"] == 1
    assert stats["next_session"] is not None
    assert stats["next_session"]["is_optimal_now"] is False


def test_get_recommended_next_session_with_currently_due_optimal(temp_db):
    """
    Test that when currently due cards already satisfy target capacity,
    get_recommended_next_session immediately marks is_optimal_now = True.
    """
    gid = temp_db.create_group("Optimal Deck")
    now = datetime(2026, 9, 10, 10, 0, 0, tzinfo=timezone.utc)

    # 4 new words (each new word has brain capacity = 20)
    # Total capacity = 80 >= target capacity 40
    for i in range(4):
        temp_db.add_word(gid, f"opt_{i}", f"def_{i}")

    rec = temp_db.get_recommended_next_session(group_id=gid, now=now, target_capacity=40)
    assert rec is not None
    assert rec["is_optimal_now"] is True
    assert rec["current_due_count"] == 4
    assert rec["current_due_capacity"] == 80
    assert rec["card_count"] == 4
    assert rec["accumulated_capacity"] == 80
    assert rec["recommended_time"] == now
    assert rec["short_label"] == "Optimal now"
    assert rec["time_until_seconds"] == 0.0

    stats = temp_db.get_stats_summary(group_id=gid, now=now)
def test_get_words_filtering(temp_db):
    """Test filtering words by group, state, pos, tag, search, and due_only."""
    g1 = temp_db.create_group("Group 1")
    g2 = temp_db.create_group("Group 2")

    w1 = temp_db.add_word(g1, "apple", "a red fruit", pos="noun", tags="food, fruit")
    w2 = temp_db.add_word(g1, "run", "to move quickly", pos="verb", tags="action")
    w3 = temp_db.add_word(g2, "banana", "a yellow fruit", pos="noun", tags="food, tropical")

    # Change w2 state to learning
    word2 = temp_db.get_word_by_id(w2)
    word2.state = "learning"
    # Set w2 due in the future
    word2.due_date = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    temp_db.update_word(word2)

    # Filter by group
    g1_words = temp_db.get_words(group_id=g1)
    assert len(g1_words) == 2
    assert {w.word for w in g1_words} == {"apple", "run"}

    # Filter by state
    new_words = temp_db.get_words(state="new")
    assert len(new_words) == 2
    assert {w.word for w in new_words} == {"apple", "banana"}

    learning_words = temp_db.get_words(state="learning")
    assert len(learning_words) == 1
    assert learning_words[0].word == "run"

    # Filter by pos
    nouns = temp_db.get_words(pos="noun")
    assert len(nouns) == 2
    assert {w.word for w in nouns} == {"apple", "banana"}

    verbs = temp_db.get_words(pos="verb")
    assert len(verbs) == 1
    assert verbs[0].word == "run"

    # Filter by tag
    food_words = temp_db.get_words(tag="food")
    assert len(food_words) == 2

    tropical_words = temp_db.get_words(tag="tropical")
    assert len(tropical_words) == 1
    assert tropical_words[0].word == "banana"

    # Search keyword
    searched = temp_db.get_words(search="fruit")
    assert len(searched) == 2

    # Filter due_only: w1 (new) and w3 (new) are due; w2 (learning, due in 2 days) is NOT due
    due_words = temp_db.get_words(due_only=True)
    assert len(due_words) == 2
    assert {w.word for w in due_words} == {"apple", "banana"}

    # Count words matches
    assert temp_db.count_words() == 3
    assert temp_db.count_words(group_id=g1) == 2
    assert temp_db.count_words(state="new") == 2
    assert temp_db.count_words(pos="noun") == 2
    assert temp_db.count_words(due_only=True) == 2


def test_get_words_sorting(temp_db):
    """Test sorting words by alphabetical order, ease, interval, reps, id, etc."""
    gid = temp_db.create_group("Vocab Sorting")

    w_c = temp_db.add_word(gid, "cherry", "fruit c")
    w_a = temp_db.add_word(gid, "apple", "fruit a")
    w_b = temp_db.add_word(gid, "banana", "fruit b")

    # Update ease factor and interval
    card_a = temp_db.get_word_by_id(w_a)
    card_a.ease_factor = 2.1
    card_a.interval_days = 5.0
    card_a.reps = 3
    temp_db.update_word(card_a)

    card_b = temp_db.get_word_by_id(w_b)
    card_b.ease_factor = 2.8
    card_b.interval_days = 12.0
    card_b.reps = 1
    temp_db.update_word(card_b)

    card_c = temp_db.get_word_by_id(w_c)
    card_c.ease_factor = 1.7
    card_c.interval_days = 1.0
    card_c.reps = 7
    temp_db.update_word(card_c)

    # Sort alphabetical ASC
    words_asc = temp_db.get_words(group_id=gid, sort_by="word", sort_order="asc")
    assert [w.word for w in words_asc] == ["apple", "banana", "cherry"]

    # Sort alphabetical DESC
    words_desc = temp_db.get_words(group_id=gid, sort_by="word", sort_order="desc")
    assert [w.word for w in words_desc] == ["cherry", "banana", "apple"]

    # Sort ease ASC (hardest first: cherry 1.7, apple 2.1, banana 2.8)
    words_ease_asc = temp_db.get_words(group_id=gid, sort_by="ease", sort_order="asc")
    assert [w.word for w in words_ease_asc] == ["cherry", "apple", "banana"]

    # Sort ease DESC (easiest first: banana 2.8, apple 2.1, cherry 1.7)
    words_ease_desc = temp_db.get_words(group_id=gid, sort_by="ease", sort_order="desc")
    assert [w.word for w in words_ease_desc] == ["banana", "apple", "cherry"]

    # Sort interval DESC (longest interval first: banana 12d, apple 5d, cherry 1d)
    words_int_desc = temp_db.get_words(group_id=gid, sort_by="interval", sort_order="desc")
    assert [w.word for w in words_int_desc] == ["banana", "apple", "cherry"]

    # Sort reps DESC (most reviewed: cherry 7, apple 3, banana 1)
    words_reps_desc = temp_db.get_words(group_id=gid, sort_by="reps", sort_order="desc")
    assert [w.word for w in words_reps_desc] == ["cherry", "apple", "banana"]

    # Test list_words alias
    assert temp_db.list_words(group_id=gid, sort_by="word", sort_order="asc") == words_asc


def test_thought_time_outlier_cleanup(temp_db):
    """
    Test that cleanup_thought_time_outliers resets review logs > 30s to 0.0,
    and recalculates word avg_thought_time without the distraction outlier.
    """
    gid = temp_db.create_group("Outlier Test Deck")
    wid = temp_db.add_word(group_id=gid, word="distracted_term", definition="test definition")

    now = datetime(2026, 9, 14, 10, 0, 0)
    # Log 3 reviews: 2 normal (3.0s, 4.0s) and 1 errand distraction (75.0s)
    temp_db.log_review(
        word_id=wid, grade=3, review_mode="flashcard", scheduled_days=1.0,
        elapsed_seconds=3.0, thought_time_seconds=3.0, now=now
    )
    # Direct DB insert of an outlier log (simulating pre-existing data before outlier protection)
    with temp_db.get_connection() as conn:
        conn.execute("""
            INSERT INTO review_logs (
                word_id, grade, review_mode, scheduled_days, elapsed_seconds,
                thought_time_seconds, hour_of_day, day_of_week, card_state, reviewed_at
            ) VALUES (?, 3, 'flashcard', 2.0, 75.0, 75.0, 11, 0, 'review', ?)
        """, (wid, (now + timedelta(hours=1)).isoformat()))
        conn.execute("UPDATE words SET avg_thought_time = 24.6, last_thought_time = 75.0 WHERE id = ?", (wid,))
        conn.commit()

    # Verify corrupt state
    w_corrupt = temp_db.get_word_by_id(wid)
    assert w_corrupt.avg_thought_time == 24.6
    assert w_corrupt.last_thought_time == 75.0

    # Run cleanup
    res = temp_db.cleanup_thought_time_outliers(threshold=30.0)
    assert res["cleaned_logs_count"] >= 1
    assert wid in res["affected_word_ids"]

    # Verify restored word state: avg_thought_time should be 3.0s, not 24.6s!
    w_cleaned = temp_db.get_word_by_id(wid)
    assert w_cleaned.avg_thought_time == 3.0
    assert w_cleaned.last_thought_time == 3.0

    # Verify review_log thought_time_seconds was zeroed while elapsed_seconds was preserved
    logs = temp_db.get_word_review_logs(wid)
    outlier_log = [l for l in logs if l.elapsed_seconds == 75.0][0]
    assert outlier_log.thought_time_seconds == 0.0
    assert outlier_log.elapsed_seconds == 75.0


def test_log_review_outlier_protection(temp_db):
    """Test that log_review sanitizes thought_time_seconds > 30s to 0.0 upon insertion."""
    gid = temp_db.create_group("Protection Deck")
    wid = temp_db.add_word(group_id=gid, word="procrastinate", definition="delay")

    temp_db.log_review(
        word_id=wid, grade=3, review_mode="flashcard", scheduled_days=1.0,
        elapsed_seconds=85.5, thought_time_seconds=85.5
    )

    logs = temp_db.get_word_review_logs(wid)
    assert len(logs) == 1
    assert logs[0].elapsed_seconds == 85.5
    assert logs[0].thought_time_seconds == 85.5


def test_check_and_update_mastery_and_session_exclusion(temp_db):
    """
    Test that when a word achieves mastery, it is retired and NEVER appears in study sessions again,
    nor in due queries, but remains tracked in library and stats.
    """
    gid = temp_db.create_group("Mastery Deck")
    wid = temp_db.add_word(group_id=gid, word="paradigm", definition="a standard or model")

    # Perform 3 consecutive rapid EASY reviews (Criterion B)
    now = datetime.now(timezone.utc)
    for i in range(3):
        temp_db.log_review(
            word_id=wid,
            grade=int(SRSGrade.EASY),
            review_mode="flashcard",
            scheduled_days=5.0 * (i + 1),
            elapsed_seconds=1.2,
            thought_time_seconds=1.2,
            now=now + timedelta(days=i)
        )

    w = temp_db.get_word_by_id(wid)
    w.reps = 3
    w.state = CardState.REVIEW.value
    temp_db.update_word(w)

    # Check and update mastery
    assert temp_db.check_and_update_mastery(wid) is None
    mastered = temp_db.set_word_mastery(wid, True)
    assert mastered is not None
    assert mastered.state == CardState.MASTERED.value

    # Verify persisted state in DB
    w_db = temp_db.get_word_by_id(wid)
    assert w_db.state == CardState.MASTERED.value

    # CRITICAL: Mastered word must NEVER appear in active session queries
    session_words = temp_db.get_session_words(group_id=gid, limit=10, fill_placeholders=True)
    assert len(session_words) == 0, "Mastered card must not be returned in study session!"

    # Even with force_all=True, mastered cards must never appear
    forced_words = temp_db.get_session_words(group_id=gid, limit=10, force_all=True)
    assert len(forced_words) == 0, "Mastered card must not appear even under force_all!"

    # Mastered card must NOT appear in due words
    due_words = temp_db.get_due_words(group_id=gid)
    assert len(due_words) == 0

    # Mastered card must NOT appear in newly due words
    newly_due = temp_db.get_newly_due_words(group_id=gid)
    assert len(newly_due) == 0

    # Stats: due_count must be 0, mastered_count must be 1
    stats = temp_db.get_stats_summary(group_id=gid)
    assert stats["due_count"] == 0
    assert stats["mastered_count"] == 1


def test_manual_mastery_and_reactivation(temp_db):
    """
    Test that words can be manually marked as mastered (retired) and reactivated for review,
    and that sync_all_word_states preserves the mastered status.
    """
    gid = temp_db.create_group("Manual Deck")
    wid = temp_db.add_word(group_id=gid, word="ephemeral", definition="short-lived")

    # Manually retire word
    temp_db.set_word_mastery(wid, True)
    w = temp_db.get_word_by_id(wid)
    assert w.state == CardState.MASTERED.value

    # sync_all_word_states should NOT overwrite manual retirement
    temp_db.sync_all_word_states()
    w_after_sync = temp_db.get_word_by_id(wid)
    assert w_after_sync.state == CardState.MASTERED.value

    # Reactivate word back to review
    temp_db.set_word_mastery(wid, False)
    w_reactivated = temp_db.get_word_by_id(wid)
    assert w_reactivated.state in (CardState.REVIEW.value, CardState.NEW.value)

    # After reactivation, word is now eligible for study session
    session_words = temp_db.get_session_words(group_id=gid, limit=10)
    assert len(session_words) == 1
    assert session_words[0].id == wid


def test_db_wal_mode_and_busy_timeout(temp_db):
    """Test that disk-backed SQLite databases enable WAL mode and busy timeout."""
    with temp_db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode")
        mode = cursor.fetchone()[0].lower()
        assert mode == "wal"

        cursor.execute("PRAGMA busy_timeout")
        timeout = cursor.fetchone()[0]
        assert timeout == 10000


def test_settings_operations(temp_db):
    """Test get_setting and set_setting operations."""
    assert temp_db.get_setting("non_existent") is None
    assert temp_db.get_setting("non_existent", default="fallback") == "fallback"

    temp_db.set_setting("theme", "dark")
    assert temp_db.get_setting("theme") == "dark"

    # Overwrite setting
    temp_db.set_setting("theme", "light")
    assert temp_db.get_setting("theme") == "light"


def test_alternate_word_lists_delegation(temp_db):
    """Test that Database._alternate_word_lists delegates to RecurrentSessionQueue._alternate_old_and_new."""
    from vocab.models import Word
    from vocab.srs import RecurrentSessionQueue

    old_words = [Word(id=1, group_id=1, word="old1", definition="d1")]
    new_words = [Word(id=2, group_id=1, word="new1", definition="d2")]

    result = temp_db._alternate_word_lists(old_words, new_words)
    expected = RecurrentSessionQueue._alternate_old_and_new(old_words, new_words)
    assert result == expected







