"""Shared bounded study sessions for the terminal and browser interfaces."""
from typing import Optional

from vocab.db import Database
from vocab.srs import RecurrentSessionQueue


def retire_one_point_words(db: Database, group_id: Optional[int] = None) -> int:
    """Retire established one-point cards whose latest recall was successful."""
    retired = 0
    word_count = db.count_words(group_id=group_id)
    for word in db.get_words(group_id=group_id, limit=max(1, word_count)):
        if word.state == "review" and word.brain_capacity == 1:
            mastered = db.check_and_update_mastery(word.id)
            retired += int(mastered is not None and mastered.state == "mastered")
    return retired


def create_study_queue(
    db: Database,
    group_id: Optional[int] = None,
    *,
    limit: int = 20,
    force_all: bool = False,
    fill_placeholders: bool = True,
    shuffle: bool = True,
) -> RecurrentSessionQueue:
    """Select one workload-limited batch, using the terminal's queue policy.

    Repeated attempts stay in this batch. Additional due words belong to the
    next session, so continuing cannot bypass the initial workload budget.
    """
    retire_one_point_words(db, group_id)
    words = db.get_session_words(
        group_id=group_id,
        limit=limit,
        force_all=force_all,
        fill_placeholders=fill_placeholders,
    )
    return RecurrentSessionQueue(
        words,
        reinsert_offset=3,
        enable_shuffling=shuffle,
        enable_interleaving=shuffle,
        previous_sequence=db.get_recent_review_sequence(group_id=group_id, limit=40),
    )
