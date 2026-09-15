"""
Import and export utilities for vocabulary data (CSV and JSON).
"""
from __future__ import annotations
import csv
import json
import io
import os
from typing import List, Dict, Any, Tuple
from vocab.db import Database


class DataExporter:
    @staticmethod
    def export_to_json(db: Database, filepath: str, group_id: int | None = None) -> int:
        """Exports groups and words to a JSON file."""
        groups = db.get_groups()
        if group_id is not None:
            groups = [g for g in groups if g.id == group_id]

        export_data = []
        total_words = 0

        for g in groups:
            words = db.get_all_words_for_group(g.id) if hasattr(db, "get_all_words_for_group") else db.get_words(group_id=g.id, limit=10000)
            word_list = []
            for w in words:
                word_list.append({
                    "word": w.word,
                    "definition": w.definition,
                    "phonetic": w.phonetic,
                    "pos": w.pos,
                    "example": w.example,
                    "mnemonic": w.mnemonic,
                    "tags": w.tags,
                    "state": w.state,
                    "interval_days": w.interval_days,
                    "ease_factor": w.ease_factor,
                    "reps": w.reps,
                    "lapses": w.lapses,
                    "due_date": w.due_date,
                })
                total_words += 1

            export_data.append({
                "group_name": g.name,
                "description": g.description,
                "color": g.color,
                "words": word_list
            })

        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)

        return total_words

    @staticmethod
    def export_to_csv(db: Database, filepath: str, group_id: int | None = None) -> int:
        """Exports words to a clean CSV file."""
        words = db.get_words(group_id=group_id, limit=10000)
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)

        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["group", "word", "pos", "phonetic", "definition", "example", "mnemonic", "tags"])
            for w in words:
                writer.writerow([
                    w.group_name or "",
                    w.word,
                    w.pos,
                    w.phonetic,
                    w.definition,
                    w.example,
                    w.mnemonic,
                    w.tags
                ])
        return len(words)

    @staticmethod
    def import_from_json(db: Database, filepath: str) -> Tuple[int, int]:
        """
        Imports groups and words from a JSON file.
        Returns (groups_added, words_added).
        """
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, list):
            raise ValueError("Invalid JSON format: root element must be a list of groups.")

        groups_added = 0
        words_added = 0
        existing_groups = {g.name.lower(): g for g in db.get_groups()}

        for item in data:
            group_name = item.get("group_name", "Imported").strip()
            if not group_name:
                group_name = "Imported"

            if group_name.lower() in existing_groups:
                gid = existing_groups[group_name.lower()].id
            else:
                gid = db.create_group(
                    name=group_name,
                    description=item.get("description", ""),
                    color=item.get("color", "cyan")
                )
                groups_added += 1
                # Update cache
                fresh_group = db.get_group_by_id(gid)
                if fresh_group:
                    existing_groups[group_name.lower()] = fresh_group

            existing_words = {w.word.lower() for w in db.get_words(group_id=gid, limit=10000)}

            for w in item.get("words", []):
                term = w.get("word", "").strip()
                if not term or term.lower() in existing_words:
                    continue

                db.add_word(
                    group_id=gid,
                    word=term,
                    definition=w.get("definition", "").strip(),
                    phonetic=w.get("phonetic", "").strip(),
                    pos=w.get("pos", "").strip(),
                    example=w.get("example", "").strip(),
                    mnemonic=w.get("mnemonic", "").strip(),
                    tags=w.get("tags", "").strip()
                )
                existing_words.add(term.lower())
                words_added += 1

        return groups_added, words_added

    @staticmethod
    def import_from_csv(db: Database, filepath: str, default_group: str = "Imported") -> Tuple[int, int]:
        """
        Imports words from CSV.
        Expected columns: group, word, pos, phonetic, definition, example, mnemonic, tags
        (Or minimal: word, definition)
        Returns (groups_added, words_added).
        """
        groups_added = 0
        words_added = 0
        existing_groups = {g.name.lower(): g for g in db.get_groups()}

        with open(filepath, "r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            header = next(reader, None)
            if not header:
                return 0, 0

            # Normalize header column mapping
            col_map = {col.strip().lower(): idx for idx, col in enumerate(header)}
            group_idx = col_map.get("group")
            word_idx = col_map.get("word")
            def_idx = col_map.get("definition") or col_map.get("meaning") or col_map.get("def")
            pos_idx = col_map.get("pos") or col_map.get("part of speech")
            phonetic_idx = col_map.get("phonetic") or col_map.get("pronunciation")
            example_idx = col_map.get("example") or col_map.get("sentence")
            mnemonic_idx = col_map.get("mnemonic") or col_map.get("hint")
            tags_idx = col_map.get("tags") or col_map.get("tag")

            if word_idx is None or def_idx is None:
                # If header is just data or simple 2 columns: word, definition
                if len(header) >= 2:
                    word_idx = 0
                    def_idx = 1
                else:
                    raise ValueError("CSV must have at least 'word' and 'definition' columns.")

            cache_words_per_group: Dict[int, set] = {}

            for row in reader:
                if not row or len(row) <= word_idx:
                    continue

                term = row[word_idx].strip()
                definition = row[def_idx].strip() if len(row) > def_idx else ""
                if not term or not definition:
                    continue

                gname = (row[group_idx].strip() if group_idx is not None and len(row) > group_idx else "") or default_group
                gname_lower = gname.lower()

                if gname_lower in existing_groups:
                    gid = existing_groups[gname_lower].id
                else:
                    gid = db.create_group(name=gname)
                    groups_added += 1
                    fresh_group = db.get_group_by_id(gid)
                    if fresh_group:
                        existing_groups[gname_lower] = fresh_group

                if gid not in cache_words_per_group:
                    cache_words_per_group[gid] = {w.word.lower() for w in db.get_words(group_id=gid, limit=10000)}

                if term.lower() in cache_words_per_group[gid]:
                    continue

                pos = row[pos_idx].strip() if pos_idx is not None and len(row) > pos_idx else ""
                phonetic = row[phonetic_idx].strip() if phonetic_idx is not None and len(row) > phonetic_idx else ""
                example = row[example_idx].strip() if example_idx is not None and len(row) > example_idx else ""
                mnemonic = row[mnemonic_idx].strip() if mnemonic_idx is not None and len(row) > mnemonic_idx else ""
                tags = row[tags_idx].strip() if tags_idx is not None and len(row) > tags_idx else ""

                db.add_word(
                    group_id=gid,
                    word=term,
                    definition=definition,
                    phonetic=phonetic,
                    pos=pos,
                    example=example,
                    mnemonic=mnemonic,
                    tags=tags
                )
                cache_words_per_group[gid].add(term.lower())
                words_added += 1

        return groups_added, words_added
