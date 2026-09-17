"""Local browser interface for the terminal vocabulary application."""
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from threading import RLock
from time import monotonic
import csv
import io
import json
import secrets
import sqlite3
import tempfile

from flask import Flask, jsonify, render_template, request, session, send_file
from flask.json.provider import DefaultJSONProvider
from werkzeug.exceptions import BadRequest, Conflict, HTTPException, NotFound

from vocab.dictionary import (
    BackgroundEnricher,
    DictionaryService,
    _CHINESE_CACHE,
    _LOOKUP_CACHE,
)
from vocab.exporter import DataExporter
from vocab.seed_data import seed_database
from .storage import WebDatabase
from .study import StudySession, CheckSession


class JSONProvider(DefaultJSONProvider):
    @staticmethod
    def default(value):
        if is_dataclass(value):
            return asdict(value)
        if isinstance(value, datetime):
            return value.isoformat()
        return DefaultJSONProvider.default(value)


def create_app(db_path=None, *, testing=False, seed=True):
    app = Flask(__name__)
    app.json = JSONProvider(app)
    app.json.sort_keys = False
    app.config.update(SECRET_KEY=secrets.token_hex(32), TESTING=testing,
        MAX_CONTENT_LENGTH=5 * 1024 * 1024, SESSION_COOKIE_SAMESITE="Strict",
        SESSION_COOKIE_HTTPONLY=True, TRUSTED_HOSTS=["localhost", "127.0.0.1", "[::1]"])
    db = WebDatabase(db_path)
    app.extensions["vocab_db"] = db
    active, lock = {}, RLock()
    if seed and not db.get_setting("example_decks_initialized"):
        if not db.get_groups():
            seed_database(db)
        db.set_setting("example_decks_initialized", "true")

    @app.before_request
    def protect_mutations():
        if "owner" not in session:
            session["owner"] = secrets.token_hex(24)
            session["csrf"] = secrets.token_hex(24)
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            if not secrets.compare_digest(request.headers.get("X-CSRF-Token", ""), session["csrf"]):
                raise BadRequest("Session verification failed. Reload the page and try again.")

    @app.after_request
    def headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; img-src 'self' data:; frame-ancestors 'none'; form-action 'self'; base-uri 'self'"
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify(error=error.description), error.code

    @app.errorhandler(sqlite3.IntegrityError)
    def integrity_error(error):
        return jsonify(error="A deck with this name already exists, or the selected deck was deleted."), 409

    def body():
        data = request.get_json()
        if not isinstance(data, dict):
            raise BadRequest("Send a JSON object.")
        return data

    def integer(value, default=None, low=1, high=1000000000):
        if value in (None, ""):
            return default
        try:
            number = int(value)
            if isinstance(value, bool) or str(number) != str(value) or not low <= number <= high:
                raise ValueError
            return number
        except (TypeError, ValueError):
            raise BadRequest(f"Expected a whole number between {low} and {high}.")

    def group(value):
        gid = integer(value)
        if gid is not None and not db.get_group_by_id(gid):
            raise NotFound("Deck not found.")
        return gid

    def text(data, key, required=False, maximum=10000):
        value = data.get(key, "")
        if not isinstance(value, str) or len(value) > maximum or (required and not value.strip()):
            raise BadRequest(f"{key.replace('_', ' ').title()} must be {'nonempty ' if required else ''}text (up to {maximum} characters).")
        return value.strip()

    def get_word(wid):
        word = db.get_word_by_id(wid)
        if not word:
            raise NotFound("Word not found.")
        return word

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/bootstrap")
    def bootstrap():
        return jsonify(csrf=session["csrf"], groups=db.get_groups(),
            threshold=db.get_max_thought_time_threshold(),
            keyboard_controls=db.get_setting("web_keyboard_controls", "true").lower() in ("true", "1", "yes"))

    @app.get("/api/dashboard")
    def dashboard():
        gid = group(request.args.get("group_id"))
        return jsonify(stats=db.get_stats_summary(gid), groups=db.get_groups(),
            forecast=db.get_due_forecast(gid), hourly=db.get_hourly_activity(gid),
            periods=db.get_circadian_periods_summary(gid), latency=db.get_latency_analytics(gid))

    @app.route("/api/groups", methods=["GET", "POST"])
    def groups():
        if request.method == "GET":
            return jsonify(groups=db.get_groups())
        data = body()
        gid = db.create_group(text(data, "name", True, 100), text(data, "description"), text(data, "color") or "cyan")
        return jsonify(group=db.get_group_by_id(gid)), 201

    @app.route("/api/groups/<int:gid>", methods=["PATCH", "DELETE"])
    def change_group(gid):
        group(gid)
        if request.method == "DELETE":
            db.delete_group(gid)
        else:
            data = body()
            db.update_group(gid, text(data, "name", True, 100), text(data, "description"), text(data, "color") or "cyan")
        return jsonify(ok=True)

    @app.route("/api/words", methods=["GET", "POST"])
    def words():
        if request.method == "GET":
            filters = {key: request.args.get(key) or None for key in ("search", "state", "pos", "tag")}
            filters.update(group_id=group(request.args.get("group_id")), due_only=request.args.get("due_only") == "true")
            return jsonify(words=db.get_words(**filters, sort_by=request.args.get("sort", "word"),
                sort_order=request.args.get("order", "asc"), limit=integer(request.args.get("limit"), 30, high=100),
                offset=integer(request.args.get("offset"), 0, low=0)), total=db.count_words(**filters))
        data = body()
        gid = group(data.get("group_id"))
        if gid is None:
            raise BadRequest("Choose a deck.")
        values = {key: text(data, key, key in ("word", "definition"), 500 if key == "word" else 10000)
                  for key in ("word", "definition", "phonetic", "pos", "example", "mnemonic", "tags")}
        wid = db.add_word(gid, **values)
        return jsonify(word=get_word(wid)), 201

    @app.post("/api/words/quick")
    def quick_word():
        """Save one entry from the terminal-style continuous add loop."""
        data = body()
        gid = group(data.get("group_id"))
        if gid is None:
            raise BadRequest("Choose a deck.")
        entry = text(data, "entry", True, 10503)
        if entry.lower() in (":q", "quit", "exit", ":quit", ":exit"):
            return jsonify(quit=True)

        if ":" in entry:
            word_text, definition = entry.split(":", 1)
        elif "=" in entry:
            word_text, definition = entry.split("=", 1)
        elif " - " in entry:
            word_text, definition = entry.split(" - ", 1)
        else:
            word_text, definition = entry, ""
        word_text, definition = word_text.strip(), definition.strip()
        if not word_text:
            raise BadRequest("Enter a word before the definition separator.")
        if len(word_text) > 500:
            raise BadRequest("Word must be text up to 500 characters.")
        if len(definition) > 10000:
            raise BadRequest("Definition must be text up to 10000 characters.")

        cached_entry = _LOOKUP_CACHE.get(word_text.lower())
        cached_chinese = _CHINESE_CACHE.get(word_text.lower())
        needs_chinese = not definition and not cached_chinese
        if not definition:
            definition = cached_chinese or "[Fetching Chinese meaning...]"
        phonetic = cached_entry.phonetic if cached_entry else ""
        pos = cached_entry.pos if cached_entry else ""

        with db.transaction():
            with db.get_connection() as connection:
                duplicate = connection.execute(
                    "SELECT id FROM words WHERE group_id = ? AND LOWER(TRIM(word)) = ? LIMIT 1",
                    (gid, word_text.lower()),
                ).fetchone()
            if duplicate:
                return jsonify(word=get_word(duplicate["id"]), duplicate=True, enriching=False)
            wid = db.add_word(
                gid, word_text, definition, phonetic=phonetic, pos=pos,
                example="", mnemonic="", tags="",
            )

        # Start network work only after the row is committed and visible to the worker.
        BackgroundEnricher.enrich(
            db=db, word_id=wid, word_text=word_text, needs_chinese=needs_chinese
        )
        return jsonify(
            word=get_word(wid), duplicate=False,
            enriching=needs_chinese or not cached_entry,
        ), 201

    @app.route("/api/words/<int:wid>", methods=["GET", "PATCH", "DELETE"])
    def change_word(wid):
        with db.transaction():
            word = get_word(wid)
            if request.method == "DELETE":
                db.delete_word(wid)
                return jsonify(ok=True)
            if request.method == "PATCH":
                data = body()
                for key in ("word", "definition", "phonetic", "pos", "example", "mnemonic", "tags"):
                    if key in data:
                        setattr(word, key, text(data, key, key in ("word", "definition"), 500 if key == "word" else 10000))
                if "group_id" in data:
                    word.group_id = group(data["group_id"])
                    if word.group_id is None:
                        raise BadRequest("Choose a deck.")
                db.update_word(word)
                if "retired" in data:
                    if type(data["retired"]) is not bool:
                        raise BadRequest("Retired must be true or false.")
                    db.set_word_mastery(wid, data["retired"])
            return jsonify(word=get_word(wid), reviews=db.get_word_review_logs(wid))

    @app.post("/api/dictionary")
    def dictionary():
        word = text(body(), "word", True, 100)
        entry = DictionaryService.lookup(word)
        chinese = DictionaryService.lookup_chinese(word)
        valid, suggestion = DictionaryService.check_word_exists(word)
        return jsonify(entry=entry, chinese=chinese, valid=valid, suggestion=suggestion)

    @app.post("/api/sessions")
    def start_session():
        data = body()
        data["group_id"] = group(data.get("group_id"))
        data["limit"] = integer(data.get("limit"), 20, high=100)
        for key in ("shuffle", "auto_add_due", "force_all", "fill_placeholders"):
            if key in data and type(data[key]) is not bool:
                raise BadRequest(f"{key} must be true or false.")
        if data.get("level") and data["level"] not in ("A1", "A2", "B1", "B2", "C1", "C2"):
            raise BadRequest("Unknown item level.")
        new = CheckSession(db, data) if data.get("mode") == "check" else StudySession(db, data)
        sid = secrets.token_urlsafe(24)
        with lock:
            # Bound memory and expire abandoned sessions after a day.
            for key, value in list(active.items()):
                if monotonic() - value[2] > 86400:
                    del active[key]
            if len(active) >= 200:
                raise Conflict("Too many open sessions. Restart the local server to clear abandoned sessions.")
            active[sid] = [session["owner"], new, monotonic()]
        return jsonify(id=sid, **new.view()), 201

    @app.route("/api/sessions/<sid>", methods=["GET", "POST"])
    def study(sid):
        with lock:
            item = active.get(sid)
            if item is None or item[0] != session["owner"]:
                raise NotFound("Session expired. Saved reviews are safe; start a new session.")
            item[2] = monotonic()
            result = item[1].act(body()) if request.method == "POST" else item[1].view()
            return jsonify(id=sid, **result)

    @app.get("/api/checks")
    def checks():
        return jsonify(history=db.get_test_history(limit=100), analytics=db.get_test_analytics())

    @app.delete("/api/checks/<int:tid>")
    def delete_check(tid):
        db.delete_test_history(tid)
        return jsonify(ok=True)

    @app.get("/api/export")
    def export():
        fmt = request.args.get("format", "json")
        if fmt not in ("json", "csv"):
            raise BadRequest("Choose JSON or CSV.")
        gid = group(request.args.get("group_id"))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / f"vocab-export.{fmt}"
            getattr(DataExporter, f"export_to_{fmt}")(db, str(path), gid)
            content = path.read_bytes()
        return send_file(io.BytesIO(content), as_attachment=True, download_name=f"vocab-export.{fmt}",
            mimetype="application/json" if fmt == "json" else "text/csv")

    @app.post("/api/import")
    def import_words():
        upload = request.files.get("file")
        if not upload or not upload.filename:
            raise BadRequest("Select a CSV or JSON file.")
        try:
            content = upload.read().decode("utf-8-sig")
            if upload.filename.lower().endswith(".csv"):
                reader = csv.DictReader(io.StringIO(content))
                if not reader.fieldnames or "word" not in reader.fieldnames or not ({"definition", "meaning"} & set(reader.fieldnames)):
                    raise ValueError("CSV needs word and definition (or meaning) columns.")
                decks = {}
                for row in reader:
                    name = row.get("group") or "Imported"
                    words = decks.setdefault(name, [])
                    words.append({**{k: row.get(k) or "" for k in ("word", "phonetic", "pos", "example", "mnemonic", "tags")},
                                  "definition": row.get("definition") or row.get("meaning") or ""})
                data = [{"group_name": name, "words": words} for name, words in decks.items()]
            elif upload.filename.lower().endswith(".json"):
                data = json.loads(content)
            else:
                raise ValueError("Choose a CSV or JSON file.")
            if not isinstance(data, list):
                raise ValueError("JSON must contain a list of decks.")
            for deck in data:
                if not isinstance(deck, dict) or not isinstance(deck.get("words"), list):
                    raise ValueError("Each deck needs a words list.")
                text(deck, "group_name", True, 100)
                for key in ("description", "color"):
                    text(deck, key)
                for word in deck["words"]:
                    if not isinstance(word, dict):
                        raise ValueError("Each word must be an object.")
                    for key in ("word", "definition", "phonetic", "pos", "example", "mnemonic", "tags"):
                        text(word, key, key in ("word", "definition"), 500 if key == "word" else 10000)
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "import.json"
                path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                with db.transaction():
                    groups_added, words_added = DataExporter.import_from_json(db, str(path))
            return jsonify(groups_added=groups_added, words_added=words_added)
        except (ValueError, UnicodeError) as error:
            raise BadRequest(str(error))

    @app.post("/api/maintenance")
    def maintenance():
        data = body()
        action = data.get("action")
        with lock, db.transaction():
            if action == "seed":
                result = {"words_added": seed_database(db)}
            elif action == "sync":
                result = {"words_updated": db.sync_all_word_states()}
            elif action == "cleanup":
                result = db.cleanup_thought_time_outliers()
            elif action == "threshold":
                threshold = integer(data.get("value"), low=1, high=3600)
                if threshold is None:
                    raise BadRequest("Enter a threshold.")
                db.set_setting("max_thought_time", str(threshold))
                result = {"threshold": db.get_max_thought_time_threshold()}
            elif action == "keyboard":
                enabled = data.get("enabled")
                if type(enabled) is not bool:
                    raise BadRequest("Keyboard controls must be true or false.")
                db.set_setting("web_keyboard_controls", str(enabled).lower())
                result = {"keyboard_controls": enabled}
            else:
                raise BadRequest("Unknown maintenance action.")
        return jsonify(result)

    @app.get("/api/research")
    def research():
        return jsonify(content=(Path(__file__).resolve().parents[2] / "docs" / "RESEARCH.md").read_text(encoding="utf-8"))

    return app


def run_web(db_path=None, port=8766):
    from waitress import serve
    if not 1 <= port <= 65535:
        raise ValueError("Port must be between 1 and 65535.")
    app = create_app(db_path)
    print(f"Vocab web: http://127.0.0.1:{port}\nDatabase: {app.extensions['vocab_db'].db_path}\nPress Ctrl+C to stop.", flush=True)
    serve(app, host="127.0.0.1", port=port, threads=6)
