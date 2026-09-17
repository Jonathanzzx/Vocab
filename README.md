# Vocab

A focused terminal and web workspace for vocabulary practice: spaced review, active
recall, and a searchable personal library.

## Getting started

Requires Python 3.10 or later.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

On macOS or Linux, use `.venv/bin/python` instead. Study data is stored in
`vocab_data.db` in the working directory. Back up that file to preserve decks,
review history and settings.

## Web version

```powershell
.\.venv\Scripts\python.exe main.py web
```

Open [Vocab in your browser](http://127.0.0.1:8766). The responsive web app includes
flashcards, typing, recognition quizzes, vocabulary checks, deck and word editors,
dictionary lookup, statistics, CSV/JSON transfer, and maintenance controls. It
uses the same database and scheduling code as the terminal app.
Terminal-style study keys are enabled by default and can be toggled under
**Data & settings** in the web interface.

**Add word** opens a continuous entry loop: choose a deck once, press Enter
after each word, and keep typing. Missing definitions and phonetics are enriched
in the background. The loop also accepts `word: definition`, `word = definition`,
and `word - definition`, and skips existing words in that deck.

Use `--db path/to/library.db` to select a library and `--port 8767` to change the
port. The default server is local to your computer. See [Web guide](docs/WEB.md)
for session behavior, data formats, and development notes.

## Practice and organize

- **Flashcards:** recall the meaning before revealing it, then rate Again,
  Hard, Good or Easy. New words get an introduction and follow-up retrieval.
- **Typing:** retrieve a word from its definition and context, with spelling feedback.
- **Recognition quiz:** practise multiple choice without extending recall schedules.
- **Vocabulary check:** see item accuracy, a 95% Wilson interval and scores by
  item level. These informal questions do not certify CEFR or vocabulary size.
- **Library:** group, search, edit and retire words; import and export CSV or JSON.
- **Statistics:** review counts, observed recall, response times, time-of-day
  activity and upcoming work. No-data values appear as a dash.

The home screen adapts to terminal width and height and reflows while you resize
the window. Smaller windows use compact metrics and menus; larger windows show
descriptions and panels. Every action keeps its keyboard shortcut, and resizing
preserves the command you are typing. App icons are retained.

## Learning method

The scheduler uses the published **SM-2 interval and ease equations**, with
explicit short learning steps. Spacing and retrieval practice are informed by
Cepeda et al. (2006) and Karpicke & Roediger (2008). Response time does not change
intervals, early successful practice preserves due dates, and quick answers
never retire a card automatically.

Read [Learning methods and evidence](docs/RESEARCH.md) for papers, equations,
parameter choices, measurement limits, and legacy-data behavior. Workload
budgets and queue mixing are application heuristics. This is not an FSRS
implementation or a guarantee of a particular retention rate.

## Commands

```powershell
python main.py review
python main.py web
python main.py review --group "GRE & Advanced Academic"
python main.py typing
python main.py quiz
python main.py stats
python main.py add
python main.py list --search "algorithm" --limit 25
python main.py list --due-only --sort due --order asc
python main.py list --interactive
python main.py export --file my_vocab_backup.json
python main.py export --file my_vocab_backup.csv
python main.py import --file my_words.csv
```

Dictionary enrichment and external question sources need an internet connection.
Saved vocabulary and the local review scheduler work offline.

## Existing libraries

Opening the app preserves saved schedules and historical timings. Future rated
recall uses the new scheduler. Existing retired words remain retired and can be
reactivated in the word editor. Explicit history synchronization rebuilds
schedules with the current algorithm; see the research notes before using it.

## Development

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

| Module | Responsibility |
| --- | --- |
| `vocab/scheduler.py` | SM-2 scheduling, preview and history replay |
| `vocab/srs.py` | Session queues and workload heuristics |
| `vocab/measurement.py` | Wilson score intervals |
| `vocab/models.py`, `vocab/db.py` | Models, SQLite persistence and reports |
| `vocab/sessions/` | Flashcards, typing, quizzes and vocabulary checks |
| `vocab/ui/` | Theme, dashboard, cards, statistics and forms |
| `vocab/web/` | Flask API, browser sessions and responsive interface |
| `vocab/dictionary.py`, `vocab/exporter.py` | Enrichment and data exchange |
| `tests/` | Scheduler, persistence, UI and service regressions |
