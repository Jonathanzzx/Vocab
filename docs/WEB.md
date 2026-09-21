# Web interface

## Run locally

Install the project's requirements, then start the server from the repository:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py web
```

On macOS/Linux use `.venv/bin/python`. Open <http://127.0.0.1:8766>.
Stop the server with Ctrl+C. No JavaScript build step or external asset host is
required. Flask serves the API and interface through Waitress.

The default database is `vocab_data.db` in the current directory, exactly as in
the terminal app. To select a different library or port:

```powershell
python main.py web --db "D:\Vocabulary\library.db" --port 8767
```

The server binds to `127.0.0.1`. This version is a single-user local application.
A public or multi-user deployment would need authentication, user-specific data
storage, HTTPS, and persistent session storage before exposure.

## Feature map

| Browser view | Features |
| --- | --- |
| Overview | Deck scope, due counts, streak, recall accuracy, forecast, practice launch |
| Flashcards | Word-to-meaning recall, new-word introductions, reveal, four grades, interval previews |
| Typing | Definition-to-word recall, exact/near/missed spelling feedback |
| Recognition | Multiple-choice word selection; preserves recall schedules |
| Session options | Initial limit, shuffle, upcoming cards, cram, newly due additions |
| In-session controls | Edit/delete/retire current word, skip, shuffle, add due, finish |
| Library | Search, deck/state/POS/tag/due filters, sorting, pagination, review history |
| Continuous add | Keep one deck selected, press Enter after each word, skip duplicates, and enrich missing definitions in the background |
| Word editor | Definitions, phonetics, examples, memory cues, tags, deck moves, dictionary/Chinese lookup |
| Decks | Create, rename, describe, choose terminal accent color, browse, study, delete |
| Insights | All-time and 7-day recall attempts, retention, streak, library stages, 7-day forecast, time-of-day summaries, hourly activity, response-time bands/outliers, hesitant words, and deck workload |
| Vocabulary check | Offline curated items, OpenTDB, Datamuse, item levels, Wilson interval, saved results and deletion |
| Data & settings | CSV/JSON import/export, timing threshold, starter decks, explicit history replay and outlier cleanup |
| Research | Papers, scheduling equations, evidence and measurement limitations |

## Keyboard controls

Terminal-style keyboard controls are enabled by default and can be switched off
under **Data & settings → Learning preferences & maintenance**. The preference is
stored with the library and therefore applies to every browser using that local
server. Shortcuts never fire while you are editing an ordinary form field.

| Context | Input | Action |
| --- | --- | --- |
| Overview | `1`, `2`, `3`, `t` | Start flashcards, typing, quiz, or vocabulary check |
| Overview | `4`–`9` | Choose deck, add word, library, insights, decks, data/settings |
| Flashcards | `Enter` | Introduce a new word, reveal, or continue |
| Flashcards | `1`–`4` | Again, Hard, Good, Easy |
| Flashcards | `s`, `a`, `e`, `d`, `q` | Shuffle, toggle auto-add, edit, delete, finish |
| Recognition/check | `1`–`4`, `s`, `q` | Choose, shuffle when available, finish |
| Typing answer | `:s`, `:shuffle`, `shuffle` | Shuffle the remaining queue |
| Typing answer | `:q`, `quit`, `exit` | Finish the session |
| Typing answer | `skip`, `?`, empty + `Enter` | Record an unsuccessful recall and reveal the answer |

`Space` also reveals a web flashcard. Buttons remain available whether keyboard
controls are on or off.

## Continuous word entry

Choose **Add word** to open the same fast entry loop as the terminal app. The
selected deck stays in place and focus returns to the input after every save, so
you can keep typing without reopening the editor. Enter a word by itself for
background dictionary and Chinese enrichment, or include a definition as
`word: definition`, `word = definition`, or `word - definition`. Matching words
in the selected deck are skipped case-insensitively. Enter `:q`, `quit`, or
`exit`, or choose **Done**, to end the loop. The detailed editor remains
available for phonetics, examples, memory cues, and tags.

Flashcards and typing use `SRSEngine` and `RecurrentSessionQueue`, shared with
the terminal sessions. The browser adapts their interaction model to HTTP; it
does not implement a second interval formula. Introductory exposures do not
count as recall attempts. Hard and Again cards return later in the session.
Successful early reviews preserve their long-term schedule. Typing gives Good
for exact recall and Hard for edit distance at most two, matching the terminal.

The initial queue is bounded by the selected limit and the existing workload
heuristic. Auto-add can extend it as other words become due. Response time is
measured by the server from card presentation to reveal/answer, so network time
is included. Timing is descriptive and does not alter the SM-2 interval formula.
Review forecasts use UTC calendar days, as in the shared database service.

## Persistence and concurrent use

Each completed review saves the updated card and its history event in one SQLite
transaction. Browser requests include a card token so duplicate submissions
cannot grade a card twice. If a word changes elsewhere while a browser card is
open, saving that stale card is rejected; skip it to continue with fresh data.

You can navigate away and resume from Overview, or reload an active browser
session. Queues live in server memory and expire after a day of inactivity.
Restarting the server ends those queues, but completed reviews remain saved.
Vocabulary checks save their result on Finish or after continuing past the last
answer. A partial check saves only the answered items when you choose Finish.

The local server uses same-origin requests, signed HttpOnly/SameSite cookies,
CSRF tokens, trusted loopback hostnames, and no remote scripts or fonts. These
are local browser boundaries, not a public account/authentication system.

## Data exchange

CSV uses UTF-8, with `word` and `definition` (or `meaning`) required. Optional
columns are `group`, `phonetic`, `pos`, `example`, `mnemonic`, and `tags`.
JSON uses the same format as the terminal exporter:

```json
[
  {
    "group_name": "Reading",
    "description": "Words from this month's books",
    "color": "cyan",
    "words": [
      {"word": "salient", "definition": "Most noticeable or important", "tags": "reading"}
    ]
  }
]
```

Uploads are limited to 5 MB. The entire file is validated before import and
database changes are committed together. Matching words within the same deck
are skipped, case-insensitively. Imports create new learning schedules even if
JSON includes exported scheduling fields. Exported vocabulary is not a full
review-history backup. To preserve the complete library, close both interfaces
and copy the SQLite database file.

Dictionary lookups and online question sources need internet access. They use
the existing dictionary and test services. Lookup fills empty fields and appends
available Chinese text; the editor lets you review the result before saving.
Online question sources fall back to the offline bank if unavailable. Source
categories on individual questions identify the actual items returned.

## Development

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

`tests/test_web.py` exercises Flask's test client against disposable databases,
including shared scheduling, transaction rollback, stale/duplicate responses,
cross-browser isolation, all practice modes, import validation, and persistence.
Use a separate database for manual browser checks:

```powershell
python main.py web --db web_preview.db --port 8766
```
