# 🧠 Vocab — Adaptive Recurrent Vocabulary Memorization App

A terminal-based vocabulary memorization studio featuring **customizable vocabulary groups** and an **adaptive recurrent review engine** inspired by SuperMemo SM-2, modern FSRS principles, and intra-session memory consolidation.

---

## 🌟 Key Features

### 1. 🗂️ Multiple Vocabulary Groups (Decks)
- Organize words into isolated or combined study groups (e.g. *GRE & Advanced Academic*, *Essential English Idioms*, *Tech & Software Engineering*, *Spanish A1*).
- Switch active focus deck or review **All Groups** together.
- Create, rename, delete, and color-code groups with word counts and due counts.

### 2. ⚡ Adaptive Recurrent Review Engine
- **Intra-Session Recurrent Micro-Spacing**:
  When you fail a card (`Again` or `Hard` in early learning) or demonstrate severe hesitation (>12s), it is immediately re-inserted into the active session queue (~3 cards ahead). You must successfully recall it before the session concludes, guaranteeing short-to-medium term encoding.
- **Cognitive Thought Time (Latency) Adaptation**:
  - Automatically measures the precise duration you take between seeing the card prompt and initiating retrieval.
  - **Fluency Boost** (≤3.0s): Effortless automaticity earns a +12% interval stability bonus.
  - **Friction Penalty** (7.0s - 12.0s): High retrieval effort scales down interval growth by -15% and slightly adjusts ease factor so the card is revisited sooner.
  - **Severe Struggle / Micro-Lapse** (>12.0s): Compresses interval by -30% and flags the card for recurrent reinforcement in the current session.
- **Adaptive Spaced Repetition (SRS)**:
  - Dynamically calculates each card's **Ease Factor** (difficulty multiplier, minimum 1.3).
  - Learning steps: `1m` ➔ `10m` ➔ `1d` graduation.
  - Automatic lapse handling (`relearning` state with interval reduction and ease penalty).
  - Real-time interval previews: before rating, you see exactly what interval each button triggers (e.g., `<1m`, `10m`, `1d`, `4d`).
- **Urgency-Ranked Review Queue**:
  Cards that are most overdue relative to their retention curve ($\text{urgency} = \frac{\Delta t}{I}$) and high-lapse cards are prioritized first.

### 3. 🌅 Circadian Active Time Tracking & Optimal Learning Windows
- **24-Hour Review Distribution Heatmap**: Visualizes review volume across all hours of the day (00:00 to 23:00).
- **Circadian Day Periods Breakdown**:
  - 🌅 **Morning Focus** (06:00 - 11:59)
  - ☀️ **Afternoon Flow** (12:00 - 17:59)
  - 🌆 **Evening Consolidation** (18:00 - 21:59)
  - 🌙 **Night Owl / Late Review** (22:00 - 05:59)
- **Cognitive State Detection**: Detects your personal *Peak Focus Windows* vs *Fatigue Zones* based on hourly recall accuracy and latency.

### 4. 🎮 3 Versatile Review Modes
- **📚 Adaptive Flashcards**:
  - Front: Word, IPA phonetics, part of speech, tags.
  - Back: Rich definition, example sentences with the target word highlighted, memory aids/mnemonics, live latency badges, SRS stats, and 4-tier rating (`1: Again`, `2: Hard`, `3: Good`, `4: Easy`).
- **🎯 Active Recall Challenge (Typing Mode)**:
  - Presents definition, part of speech, context with blanks, and masked letter hints (e.g., `e _ _ _ _ _ _ l`).
  - Evaluates user input using Levenshtein distance: gives instant feedback for exact matches, near-miss typos, or misses, and recurrently re-queues missed words.
- **⚡ Speed Multiple-Choice Quiz**:
  - Rapid-fire 4-choice recognition drill for quick warmups.
  - Distractors are intelligently drawn from the same vocabulary group.

### 5. 📊 Analytics, Thought Time & Hesitation Watchlist
- **⏱️ Average Thought Time**: Real-time tracking of recall latency across cards.
- **⚠️ Hesitation Watchlist**: Ranks cards where your recall latency is slowest so you can target cognitive bottlenecks.
- **⚡ Due Today & Forecast**: Tracks overdue cards and forecasts upcoming card volume (+1d, +2d, +3d, +7d).
- **📅 Daily Streak**: Tracks consecutive active learning days.
- **🎯 Retention Accuracy**: Measures your 7-day recall percentage.
- **🌲 Memory Maturity Distribution**: Categorizes words into *New*, *Learning/Lapsed*, *Young (<21 days)*, and *Mature (≥21 days)* with Unicode terminal bar charts.

### 5. 📦 Import / Export & Starter Decks
- Includes curated built-in starter decks:
  - **GRE & Advanced Academic** (concise, fleeting, obdurate, pragmatic, sycophant, anomalous, capricious, esoteric, venerate, alacrity, enervate, equanimity, fastidious, pellucid, misanthrope).
  - **Essential Idioms & Phrasal Verbs** (bite the bullet, burn the midnight oil, cut to the chase, blessing in disguise, take with a grain of salt, etc.).
  - **Tech & Software Engineering** (idempotent, concurrency, memoization, backpressure, polymorphism, deadlock, amortized, deterministic, heuristics, immutable).
- Import & Export via **CSV** or **JSON**.

---

## 🚀 Quick Start

### Launch Interactive Studio
```powershell
python main.py
```

### CLI Direct Commands
You can also launch directly into specific modes:
```powershell
# Flashcard review session (default: 20 cards)
python main.py review

# Review only cards from a specific group
python main.py review --group "GRE & Advanced Academic"

# Active recall typing challenge
python main.py typing

# Speed multiple-choice quiz
python main.py quiz

# Memory analytics and maturity dashboard
python main.py stats

# Add a new word directly from command line
python main.py add

# Export all words to CSV or JSON
python main.py export --file my_vocab_backup.csv
python main.py export --file my_vocab_backup.json

# Import custom vocabulary
python main.py import --file my_words.csv

# List words with filtering and sorting
python main.py list
python main.py list --sort word --order asc
python main.py list --group "Tech & Software Engineering" --state new
python main.py list --due-only --sort due --order asc
python main.py list --search "algorithm" --limit 25
python main.py list --interactive
```

---

## 🗄️ Project Architecture

```
Vocab/
├── vocab/
│   ├── models.py           # Word, Group, ReviewLog, SRSGrade dataclasses
│   ├── db.py               # SQLite database with context manager and migrations
│   ├── srs.py              # Adaptive SRS engine & RecurrentSessionQueue
│   ├── seed_data.py        # Curated starter decks
│   ├── exporter.py         # CSV and JSON import/export
│   ├── ui/
│   │   ├── theme.py        # Rich console styling, banners, helpers
│   │   ├── menu.py         # Dashboard and main menu renderer
│   │   ├── card_views.py   # Flashcards, typing hints, quiz layouts
│   │   ├── stats_views.py  # Retention dashboards, bars, forecasts
│   │   └── forms.py        # Forms for adding/editing words & managing groups
│   ├── sessions/
│   │   ├── flashcard_session.py # Interactive recurrent flashcard review
│   │   ├── typing_session.py    # Active recall typing challenge
│   │   └── quiz_session.py      # Multiple choice rapid drill
│   └── app.py              # Application controller & CLI argument parser
├── tests/                  # Pytest automated test suite (12 tests)
│   ├── test_srs.py
│   ├── test_db.py
│   └── test_export.py
├── main.py                 # Main entry point
└── requirements.txt        # Dependencies
```

---

## 🧪 Running Tests
All components are covered by unit tests:
```powershell
python -m pytest -v
```
