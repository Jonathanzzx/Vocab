"""
Unit tests for Dictionary API service.
"""
import pytest
from vocab.dictionary import DictionaryService, DictionaryEntry, _LOOKUP_CACHE


def test_dictionary_lookup_caching():
    """Test that dictionary lookups are cached in memory."""
    test_word = "neuron"
    res1 = DictionaryService.lookup(test_word)
    assert res1.word == test_word

    cache_key = test_word.lower()
    assert cache_key in _LOOKUP_CACHE
    assert _LOOKUP_CACHE[cache_key] == res1

    # Second lookup should return identical cached object
    res2 = DictionaryService.lookup(test_word)
    assert res2 is res1


def test_dictionary_lookup_phonetics():
    """Test that phonetic pronunciations are retrieved and formatted as /ipa/."""
    entry = DictionaryService.lookup("hippocampus")
    assert entry.word == "hippocampus"
    if entry.phonetic:
        assert entry.phonetic.startswith("/")
        assert entry.phonetic.endswith("/")
        assert entry.pos in ("noun", "n", "term", "")


def test_dictionary_lookup_compound_phrase():
    """Test that multi-word terms are looked up and phonetics are merged."""
    entry = DictionaryService.lookup("action potential")
    assert entry.word == "action potential"
    if entry.phonetic:
        assert entry.phonetic.startswith("/")
        assert entry.phonetic.endswith("/")


def test_dictionary_lookup_graceful_fallback():
    """Test that unknown words or empty strings do not crash and return cleanly."""
    empty_entry = DictionaryService.lookup("")
    assert empty_entry.word == ""
    assert empty_entry.phonetic == ""

    # Nonexistent or random word returns DictionaryEntry without error
    bogus = DictionaryService.lookup("qwertyuiopasdfghjklzxcvbnm12345")
    assert isinstance(bogus, DictionaryEntry)
    assert bogus.word == "qwertyuiopasdfghjklzxcvbnm12345"


def test_dictionary_lookup_chinese():
    """Test Chinese translation lookup and caching."""
    from vocab.dictionary import _CHINESE_CACHE

    assert DictionaryService.lookup_chinese("") == ""

    # Test lookup of a known word
    result = DictionaryService.lookup_chinese("neuron")
    if result:
        # If network available, should return Chinese text and be cached
        assert "neuron" in _CHINESE_CACHE
        assert _CHINESE_CACHE["neuron"] == result
        # Cached lookup returns quickly
        assert DictionaryService.lookup_chinese("neuron") == result


def test_background_enricher():
    """Test non-blocking BackgroundEnricher updates word definition and phonetics in DB."""
    import os
    import tempfile
    import threading
    from vocab.db import Database
    from vocab.dictionary import BackgroundEnricher

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        db = Database(db_path)
        grp_id = db.create_group("Test Deck")
        word_id = db.add_word(
            group_id=grp_id,
            word="dopamine",
            definition="[Fetching Chinese meaning...]"
        )

        done_event = threading.Event()

        def on_done(updated_word):
            done_event.set()

        BackgroundEnricher.enrich(
            db=db,
            word_id=word_id,
            word_text="dopamine",
            needs_chinese=True,
            on_complete=on_done
        )

        # Wait up to 10 seconds for background thread
        finished = done_event.wait(timeout=10.0)
        assert finished, "Background enrichment timed out"

        refreshed = db.get_word_by_id(word_id)
        assert refreshed is not None
        assert refreshed.definition != "[Fetching Chinese meaning...]"
        assert len(refreshed.definition) > 0
    finally:
        if os.path.exists(db_path):
            try:
                os.remove(db_path)
            except Exception:
                pass


def test_auto_add_words_and_ctrl_c_quit():
    """Test auto-add continuous loop and graceful Ctrl+C (KeyboardInterrupt) quit."""
    import os
    import tempfile
    from unittest.mock import patch
    from vocab.db import Database
    from vocab.ui.forms import add_word_form

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        db = Database(db_path)
        gid = db.create_group("Biology")

        # Simulate typing 'axon', 'dopamine', then KeyboardInterrupt (Ctrl+C)
        inputs = ["axon", "dopamine"]
        def mock_prompt(*args, **kwargs):
            if inputs:
                return inputs.pop(0)
            raise KeyboardInterrupt()

        with patch("vocab.ui.forms.prompt", side_effect=mock_prompt):
            add_word_form(db, current_group_id=gid)

        words = db.get_words(group_id=gid)
        word_texts = [w.word for w in words]
        assert "axon" in word_texts
        assert "dopamine" in word_texts
        assert len(words) == 2
    finally:
        if os.path.exists(db_path):
            try:
                os.remove(db_path)
            except Exception:
                pass


def test_auto_add_custom_definition_and_duplicate_skip():
    """Test custom definition syntax (word: def) and duplicate skipping in auto-add."""
    import os
    import tempfile
    from unittest.mock import patch
    from vocab.db import Database
    from vocab.ui.forms import add_word_form

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        db = Database(db_path)
        gid = db.create_group("Neuroscience")
        db.add_word(group_id=gid, word="synapse", definition="junction")

        # Duplicate 'synapse', then custom definition 'myelin: fatty insulator', then ':q'
        inputs = ["synapse", "myelin: fatty insulator", ":q"]
        def mock_prompt(*args, **kwargs):
            if inputs:
                return inputs.pop(0)
            return ""

        with patch("vocab.ui.forms.prompt", side_effect=mock_prompt):
            add_word_form(db, current_group_id=gid)

        words = db.get_words(group_id=gid)
        word_map = {w.word: w.definition for w in words}

        # Duplicate skipped
        assert len([w for w in words if w.word == "synapse"]) == 1
        # Custom definition stored
        assert "myelin" in word_map
        assert word_map["myelin"] == "fatty insulator"
    finally:
        if os.path.exists(db_path):
            try:
                os.remove(db_path)
            except Exception:
                pass


def test_flashcard_front_shows_definition_on_new_words():
    """Test that render_flashcard_front displays definition on new words."""
    from io import StringIO
    from rich.console import Console
    from vocab.models import Word, CardState
    from vocab.ui import card_views

    new_word = Word(
        id=1,
        group_id=1,
        word="dissuade",
        definition="to persuade someone not to do something",
        phonetic="/dɪˈsweɪd/",
        pos="verb",
        state=CardState.NEW.value,
        reps=0
    )

    buf = StringIO()
    test_console = Console(file=buf, force_terminal=False, color_system=None)
    orig_console = card_views.console
    card_views.console = test_console
    try:
        card_views.render_flashcard_front(new_word, 1, 5)
        output = buf.getvalue()
        assert "dissuade" in output
        assert "to persuade someone not to do something" in output
        assert "Definition / Meaning" in output
        assert "NEW" in output
    finally:
        card_views.console = orig_console


def test_flashcard_front_hides_definition_on_review_words():
    """Test that render_flashcard_front hides definition on review words for active recall."""
    from io import StringIO
    from rich.console import Console
    from vocab.models import Word, CardState
    from vocab.ui import card_views

    review_word = Word(
        id=2,
        group_id=1,
        word="dissuade",
        definition="secret definition should not appear on front",
        phonetic="/dɪˈsweɪd/",
        pos="verb",
        state=CardState.REVIEW.value,
        reps=2
    )

    buf = StringIO()
    test_console = Console(file=buf, force_terminal=False, color_system=None)
    orig_console = card_views.console
    card_views.console = test_console
    try:
        card_views.render_flashcard_front(review_word, 1, 5)
        output = buf.getvalue()
        assert "dissuade" in output
        assert "secret definition should not appear on front" not in output
        assert "Try to recall the definition" in output
    finally:
        card_views.console = orig_console


def test_flashcard_front_hides_definition_on_learning_words():
    """Test that render_flashcard_front hides definition on learning words even with reps=0."""
    from io import StringIO
    from rich.console import Console
    from vocab.models import Word, CardState
    from vocab.ui import card_views

    learning_word = Word(
        id=3,
        group_id=1,
        word="affinity",
        definition="natural liking or sympathy",
        phonetic="/əˈfɪn.ə.ti/",
        pos="noun",
        state=CardState.LEARNING.value,
        step=1,
        reps=0  # reps is 0 during learning steps!
    )

    buf = StringIO()
    test_console = Console(file=buf, force_terminal=False, color_system=None)
    orig_console = card_views.console
    card_views.console = test_console
    try:
        card_views.render_flashcard_front(learning_word, 1, 5)
        output = buf.getvalue()
        assert "affinity" in output
        assert "natural liking or sympathy" not in output
        assert "Definition / Meaning" not in output
        assert "LEARNING" in output
        assert "Try to recall the definition" in output
        assert "Press [Enter] to reveal" in output
    finally:
        card_views.console = orig_console


def test_dictionary_check_word_exists_valid():
    """Test check_word_exists correctly validates real English words and terms."""
    valid, sug = DictionaryService.check_word_exists("apple")
    assert valid is True
    assert sug is None

    valid, sug = DictionaryService.check_word_exists("neuron")
    assert valid is True
    assert sug is None

    valid, sug = DictionaryService.check_word_exists("action potential")
    assert valid is True
    assert sug is None


def test_dictionary_check_word_exists_typo_with_suggestion():
    """Test check_word_exists identifies misspellings and suggests correct spellings."""
    valid, sug = DictionaryService.check_word_exists("testostrone")
    assert valid is False
    assert sug == "testosterone"

    valid, sug = DictionaryService.check_word_exists("psycology")
    assert valid is False
    assert sug == "psychology"

    valid, sug = DictionaryService.check_word_exists("definately")
    assert valid is False
    assert sug == "definitely"


def test_dictionary_check_word_exists_gibberish_and_empty():
    """Test check_word_exists handles empty input and random gibberish without crash."""
    valid, sug = DictionaryService.check_word_exists("")
    assert valid is False
    assert sug is None

    valid, sug = DictionaryService.check_word_exists("   ")
    assert valid is False
    assert sug is None

    valid, sug = DictionaryService.check_word_exists("asdfghjk")
    assert valid is False
    assert sug is None


def test_add_word_form_tracks_and_passes_unexpected_words():
    """Test that add_word_form detects unexpected words and passes them at session end."""
    import os
    import tempfile
    from unittest.mock import patch
    from vocab.db import Database
    from vocab.ui.forms import add_word_form

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        db = Database(db_path)
        gid = db.create_group("Session Typo Deck")

        # Enter a valid word 'axon' and a typo word 'testostrone', then ':q'
        inputs = ["axon", "testostrone", ":q"]
        def mock_prompt(*args, **kwargs):
            if inputs:
                return inputs.pop(0)
            return "k"  # In review_unexpected_words prompt, choose 'k' (keep)

        passed_unexpected = []
        def capture_unexpected(words):
            passed_unexpected.extend(words)

        with patch("vocab.ui.forms.prompt", side_effect=mock_prompt):
            add_word_form(db, current_group_id=gid, on_unexpected=capture_unexpected)

        # Check that 'testostrone' was captured in unexpected words list
        unexpected_words_list = add_word_form.last_unexpected_words
        words_found = [u["word"] for u in unexpected_words_list]
        assert "testostrone" in words_found
        assert "axon" not in words_found

        # Check that callback received the unexpected words list
        callback_words = [u["word"] for u in passed_unexpected]
        assert "testostrone" in callback_words

        # Check typo suggestion was populated
        typo_item = next(u for u in unexpected_words_list if u["word"] == "testostrone")
        assert typo_item["suggestion"] == "testosterone"
    finally:
        if os.path.exists(db_path):
            try:
                os.remove(db_path)
            except Exception:
                pass


def test_review_unexpected_words_apply_suggestions():
    """Test review_unexpected_words auto-fixes typos when user chooses 'A'."""
    import os
    import tempfile
    from unittest.mock import patch
    from vocab.db import Database
    from vocab.ui.forms import review_unexpected_words

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        db = Database(db_path)
        gid = db.create_group("Typo Fix Deck")
        wid = db.add_word(group_id=gid, word="testostrone", definition="male hormone")

        unexpected = [
            {"id": wid, "word": "testostrone", "suggestion": "testosterone", "group_id": gid}
        ]

        with patch("vocab.ui.forms.prompt", return_value="a"):
            review_unexpected_words(db, unexpected)

        updated = db.get_word_by_id(wid)
        assert updated is not None
        assert updated.word == "testosterone"
    finally:
        if os.path.exists(db_path):
            try:
                os.remove(db_path)
            except Exception:
                pass


def test_review_unexpected_words_delete():
    """Test review_unexpected_words deletes accidental entries when user chooses 'D'."""
    import os
    import tempfile
    from unittest.mock import patch
    from vocab.db import Database
    from vocab.ui.forms import review_unexpected_words

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        db = Database(db_path)
        gid = db.create_group("Typo Delete Deck")
        wid = db.add_word(group_id=gid, word="asdfghjk", definition="")

        unexpected = [
            {"id": wid, "word": "asdfghjk", "suggestion": None, "group_id": gid}
        ]

        with patch("vocab.ui.forms.prompt", return_value="d"):
            review_unexpected_words(db, unexpected)

        assert db.get_word_by_id(wid) is None
    finally:
        if os.path.exists(db_path):
            try:
                os.remove(db_path)
            except Exception:
                pass



