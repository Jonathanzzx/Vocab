"""
Dictionary API service for automatic phonetic, pronunciation,
and linguistic metadata lookup.

Uses the free Datamuse linguistic API (with Free Dictionary API fallback)
to resolve IPA phonetics and parts of speech without requiring an API key.
"""
from __future__ import annotations
import json
import urllib.request
import urllib.parse
import urllib.error
import re
import difflib
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Dict, Optional, List, Callable, Any, Tuple


@dataclass
class DictionaryEntry:
    word: str
    phonetic: str = ""
    pos: str = ""
    definition: str = ""
    example: str = ""


# In-memory session caches to avoid redundant API queries
_LOOKUP_CACHE: Dict[str, DictionaryEntry] = {}
_CHINESE_CACHE: Dict[str, str] = {}
_EXISTENCE_CACHE: Dict[str, Tuple[bool, Optional[str]]] = {}

POS_MAPPING = {
    "n": "noun",
    "v": "verb",
    "adj": "adj",
    "adv": "adv",
    "u": "term",
}


class DictionaryService:
    """
    Public Dictionary API lookup client.
    Fetches phonetic pronunciations (IPA) and part of speech.
    """

    @classmethod
    def lookup(cls, word: str, timeout: float = 3.5) -> DictionaryEntry:
        """
        Looks up phonetic transcription and part of speech for a given word or phrase.
        Returns a DictionaryEntry with resolved phonetics, or empty defaults if not found.
        """
        clean_word = word.strip()
        if not clean_word:
            return DictionaryEntry(word=clean_word)

        cache_key = clean_word.lower()
        if cache_key in _LOOKUP_CACHE:
            return _LOOKUP_CACHE[cache_key]

        # 1. Attempt Datamuse lookup
        entry = cls._lookup_datamuse(clean_word, timeout=timeout)

        # 2. If no phonetic found and it's a multi-word phrase, resolve words individually
        if not entry.phonetic and " " in clean_word:
            entry = cls._lookup_compound_phrase(clean_word, timeout=timeout)

        # 3. Fallback to Free Dictionary API if still missing phonetic
        if not entry.phonetic:
            entry = cls._lookup_free_dictionary(clean_word, timeout=timeout)

        # Cache result
        _LOOKUP_CACHE[cache_key] = entry
        return entry

    @classmethod
    def check_word_exists(
        cls, word: str, timeout: float = 3.5, db: Optional[Any] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Looks up whether a word or term exists in standard dictionaries / lexicons.
        Returns:
            (is_valid: bool, suggestion: Optional[str])
            - is_valid: True if the word is recognized and not a typo.
            - suggestion: Suggested correct spelling if a likely typo was detected, else None.
        """
        clean = word.strip().lower()
        if not clean:
            return False, None

        # Strip surrounding quotes and punctuation
        clean = re.sub(r'^[^\w\s]+|[^\w\s]+$', '', clean)
        if not clean:
            return False, None

        if clean in _EXISTENCE_CACHE:
            return _EXISTENCE_CACHE[clean]

        # Check local DB if available
        if db is not None:
            try:
                existing = db.get_words(search=clean, limit=1)
                if existing and existing[0].word.lower() == clean:
                    res = (True, None)
                    _EXISTENCE_CACHE[clean] = res
                    return res
            except Exception:
                pass

        # Check existing memory caches
        if clean in _CHINESE_CACHE and _CHINESE_CACHE[clean]:
            res = (True, None)
            _EXISTENCE_CACHE[clean] = res
            return res

        if clean in _LOOKUP_CACHE:
            cached = _LOOKUP_CACHE[clean]
            if getattr(cached, "phonetic", None) or getattr(cached, "definition", None) or getattr(cached, "pos", None):
                res = (True, None)
                _EXISTENCE_CACHE[clean] = res
                return res

        # 1. Multi-word phrase check (e.g. 'action potential', 'give up')
        if " " in clean:
            try:
                encoded = urllib.parse.quote(clean)
                url = f"https://api.datamuse.com/words?sp={encoded}&md=d&max=3"
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) VocabApp/1.0"}
                )
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        if data:
                            top_w = data[0].get("word", "").lower()
                            if top_w == clean and data[0].get("defs"):
                                res = (True, None)
                                _EXISTENCE_CACHE[clean] = res
                                return res
                            if top_w != clean and data[0].get("defs"):
                                ratio = difflib.SequenceMatcher(None, clean, top_w).ratio()
                                sug = top_w if ratio >= 0.70 else None
                                res = (False, sug)
                                _EXISTENCE_CACHE[clean] = res
                                return res
            except Exception:
                pass

            # Fallback: validate sub-words individually
            sub_words = clean.split()
            sub_results = [cls.check_word_exists(sw, timeout=timeout, db=db) for sw in sub_words]
            if all(valid for valid, _ in sub_results):
                res = (True, None)
                _EXISTENCE_CACHE[clean] = res
                return res
            parts = [sug if (not valid and sug) else sw for (valid, sug), sw in zip(sub_results, sub_words)]
            has_sug = any(not valid and sug for valid, sug in sub_results)
            res = (False, " ".join(parts) if has_sug else None)
            _EXISTENCE_CACHE[clean] = res
            return res

        # 2. Single word lookup via Datamuse
        try:
            encoded = urllib.parse.quote(clean)
            url = f"https://api.datamuse.com/words?sp={encoded}&md=d&max=5"
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) VocabApp/1.0"}
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    if data:
                        top = data[0]
                        top_w = top.get("word", "").lower()
                        defs = top.get("defs", [])

                        # Check if Wiktionary explicitly flagged it as misspelling
                        for d in defs:
                            d_lower = d.lower()
                            if "misspelling of" in d_lower or "spelling error" in d_lower:
                                m = re.search(r"misspelling of\s+([a-zA-Z\-]+)", d, re.IGNORECASE)
                                sug = m.group(1).lower() if m else (data[1].get("word", "").lower() if len(data) > 1 else None)
                                res = (False, sug)
                                _EXISTENCE_CACHE[clean] = res
                                return res

                        # Exact match with definitions -> valid word
                        if top_w == clean and defs:
                            res = (True, None)
                            _EXISTENCE_CACHE[clean] = res
                            return res

                        # Exact match but no definitions (e.g. psycology) -> check for alternatives with definitions
                        if top_w == clean and not defs:
                            for alt in data[1:]:
                                if alt.get("defs"):
                                    alt_w = alt.get("word", "").lower()
                                    ratio = difflib.SequenceMatcher(None, clean, alt_w).ratio()
                                    if ratio >= 0.70:
                                        res = (False, alt_w)
                                        _EXISTENCE_CACHE[clean] = res
                                        return res

                        # Top result differs from query -> typo suggestion
                        if top_w != clean and (top.get("defs") or top.get("score", 0) > 1000):
                            ratio = difflib.SequenceMatcher(None, clean, top_w).ratio()
                            sug = top_w if ratio >= 0.70 else None
                            res = (False, sug)
                            _EXISTENCE_CACHE[clean] = res
                            return res
        except Exception:
            pass

        # 3. Youdao fallback check for legitimate foreign / modern terms
        try:
            encoded = urllib.parse.quote(clean)
            url = f"http://dict.youdao.com/suggest?q={encoded}&num=1&doctype=json"
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) VocabApp/1.0"}
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    entries = data.get("data", {}).get("entries", [])
                    if entries and entries[0].get("entry", "").lower() == clean:
                        res = (True, None)
                        _EXISTENCE_CACHE[clean] = res
                        return res
        except Exception:
            pass

        # 4. Sounds-like suggestion fallback via Datamuse words?sl=
        try:
            encoded = urllib.parse.quote(clean)
            url = f"https://api.datamuse.com/words?sl={encoded}&max=3"
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) VocabApp/1.0"}
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    for cand in data:
                        cand_w = cand.get("word", "").lower()
                        if cand_w != clean:
                            ratio = difflib.SequenceMatcher(None, clean, cand_w).ratio()
                            if ratio >= 0.75:
                                res = (False, cand_w)
                                _EXISTENCE_CACHE[clean] = res
                                return res
        except Exception:
            pass

        res = (False, None)
        _EXISTENCE_CACHE[clean] = res
        return res

    @classmethod
    def _lookup_datamuse(cls, word: str, timeout: float = 3.5) -> DictionaryEntry:
        """Queries Datamuse API for IPA phonetics, part of speech, and definitions."""
        try:
            encoded = urllib.parse.quote(word)
            url = f"https://api.datamuse.com/words?sp={encoded}&qe=sp&md=rpd&ipa=1"
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) VocabApp/1.0"}
            )
            with urllib.request.urlopen(req, timeout=timeout) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode("utf-8"))
                    if data and isinstance(data, list):
                        match = data[0]
                        tags = match.get("tags", [])

                        # Extract IPA
                        ipa = ""
                        for t in tags:
                            if t.startswith("ipa_pron:"):
                                raw_ipa = t.replace("ipa_pron:", "").strip()
                                if raw_ipa:
                                    ipa = f"/{raw_ipa}/"
                                    break

                        # Extract Part of Speech
                        pos = ""
                        for t in tags:
                            if t in POS_MAPPING:
                                pos = POS_MAPPING[t]
                                break

                        # Extract definition if available
                        definition = ""
                        defs = match.get("defs", [])
                        if defs:
                            first_def = defs[0]
                            # Often formatted as "n\tdefinition text"
                            if "\t" in first_def:
                                definition = first_def.split("\t", 1)[1].strip()
                            else:
                                definition = first_def.strip()

                        return DictionaryEntry(
                            word=word,
                            phonetic=ipa,
                            pos=pos,
                            definition=definition
                        )
        except Exception:
            pass

        return DictionaryEntry(word=word)

    @classmethod
    def _lookup_compound_phrase(cls, phrase: str, timeout: float = 3.5) -> DictionaryEntry:
        """Looks up multi-word phrases word by word and merges their phonetics."""
        sub_words = phrase.split()
        sub_phonetics = []
        first_pos = ""

        for sw in sub_words:
            sub_entry = cls._lookup_datamuse(sw, timeout=timeout)
            if sub_entry.phonetic:
                clean_p = sub_entry.phonetic.strip("/")
                sub_phonetics.append(clean_p)
            else:
                sub_phonetics.append(sw)
            if not first_pos and sub_entry.pos:
                first_pos = sub_entry.pos

        combined_ipa = f"/{' '.join(sub_phonetics)}/" if sub_phonetics else ""
        return DictionaryEntry(
            word=phrase,
            phonetic=combined_ipa,
            pos=first_pos or "noun"
        )

    @classmethod
    def _lookup_free_dictionary(cls, word: str, timeout: float = 2.5) -> DictionaryEntry:
        """Fallback lookup using Free Dictionary API."""
        try:
            encoded = urllib.parse.quote(word)
            url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{encoded}"
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) VocabApp/1.0"}
            )
            with urllib.request.urlopen(req, timeout=timeout) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode("utf-8"))
                    if data and isinstance(data, list):
                        first_item = data[0]
                        phonetic = first_item.get("phonetic", "")
                        if not phonetic:
                            phonetics_list = first_item.get("phonetics", [])
                            for p in phonetics_list:
                                if p.get("text"):
                                    phonetic = p.get("text")
                                    break

                        pos = ""
                        meanings = first_item.get("meanings", [])
                        if meanings:
                            pos = meanings[0].get("partOfSpeech", "")

                        return DictionaryEntry(
                            word=word,
                            phonetic=phonetic,
                            pos=pos
                        )
        except Exception:
            pass

        return DictionaryEntry(word=word)

    @classmethod
    def lookup_chinese(cls, word: str, timeout: float = 3.0) -> str:
        """
        Looks up automatic Chinese translation / definition for a word or phrase.
        Uses Youdao dictionary with Google Translate and MyMemory fallbacks.
        Results are cached in-memory.
        """
        clean_word = word.strip()
        if not clean_word:
            return ""

        cache_key = clean_word.lower()
        if cache_key in _CHINESE_CACHE:
            return _CHINESE_CACHE[cache_key]

        meaning = ""

        # 1. Attempt Youdao Dictionary Suggest API
        try:
            encoded = urllib.parse.quote(clean_word)
            url = f"http://dict.youdao.com/suggest?q={encoded}&num=1&doctype=json"
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) VocabApp/1.0"}
            )
            with urllib.request.urlopen(req, timeout=timeout) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode("utf-8"))
                    entries = data.get("data", {}).get("entries", [])
                    if entries and entries[0].get("explain"):
                        meaning = entries[0]["explain"].strip()
        except Exception:
            pass

        # 2. Fallback to Google Translate web client API
        if not meaning:
            try:
                encoded = urllib.parse.quote(clean_word)
                url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=zh-CN&dt=t&q={encoded}"
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) VocabApp/1.0"}
                )
                with urllib.request.urlopen(req, timeout=timeout) as response:
                    if response.status == 200:
                        data = json.loads(response.read().decode("utf-8"))
                        parts = [part[0] for part in data[0] if part and part[0]]
                        if parts:
                            meaning = "".join(parts).strip()
            except Exception:
                pass

        # 3. Fallback to MyMemory translation API
        if not meaning:
            try:
                encoded = urllib.parse.quote(clean_word)
                url = f"https://api.mymemory.translated.net/get?q={encoded}&langpair=en|zh-CN"
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) VocabApp/1.0"}
                )
                with urllib.request.urlopen(req, timeout=timeout) as response:
                    if response.status == 200:
                        data = json.loads(response.read().decode("utf-8"))
                        text = data.get("responseData", {}).get("translatedText", "")
                        if text and not text.startswith("MYMEMORY WARNING"):
                            meaning = text.strip()
            except Exception:
                pass

        if meaning:
            _CHINESE_CACHE[cache_key] = meaning

        return meaning


class BackgroundEnricher:
    """
    Non-blocking background enricher that automatically queries dictionary
    and translation APIs to populate phonetics and Chinese definitions.
    Prevents input interruption by running queries asynchronously.
    """
    _executor: Optional[ThreadPoolExecutor] = None
    _lock = threading.Lock()

    @classmethod
    def _get_executor(cls) -> ThreadPoolExecutor:
        with cls._lock:
            if cls._executor is None:
                cls._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="VocabEnricher")
            return cls._executor

    @classmethod
    def enrich(
        cls,
        db: Any,
        word_id: int,
        word_text: str,
        needs_chinese: bool = False,
        on_complete: Optional[Callable[[Any], None]] = None
    ) -> None:
        """
        Dispatches background enrichment task for a word.
        Returns immediately so terminal input can proceed without delay.
        """
        executor = cls._get_executor()
        executor.submit(cls._enrich_worker, db, word_id, word_text, needs_chinese, on_complete)

    @classmethod
    def _enrich_worker(
        cls,
        db: Any,
        word_id: int,
        word_text: str,
        needs_chinese: bool,
        on_complete: Optional[Callable[[Any], None]] = None
    ) -> None:
        try:
            chinese_meaning = ""
            if needs_chinese:
                chinese_meaning = DictionaryService.lookup_chinese(word_text)

            dict_entry = DictionaryService.lookup(word_text)

            word = db.get_word_by_id(word_id)
            if not word:
                return

            updated = False
            if needs_chinese:
                if chinese_meaning:
                    word.definition = chinese_meaning
                    updated = True
                elif dict_entry.definition and (not word.definition or word.definition.startswith("[")):
                    word.definition = dict_entry.definition
                    updated = True
                elif not word.definition or word.definition.startswith("["):
                    word.definition = "(No definition found - press 'e' to edit)"
                    updated = True

            if dict_entry.phonetic and not word.phonetic:
                word.phonetic = dict_entry.phonetic
                updated = True

            if dict_entry.pos and not word.pos:
                word.pos = dict_entry.pos
                updated = True

            if dict_entry.example and not word.example:
                word.example = dict_entry.example
                updated = True

            if updated:
                db.update_word(word)

            if on_complete:
                try:
                    on_complete(word)
                except Exception:
                    pass
        except Exception:
            pass

    @classmethod
    def shutdown(cls, wait: bool = False, timeout: float = 3.0) -> None:
        """Gracefully closes background worker pool."""
        with cls._lock:
            if cls._executor is not None:
                cls._executor.shutdown(wait=wait)
                cls._executor = None
