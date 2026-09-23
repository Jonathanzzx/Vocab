"""
Flashcard review session with adaptive recurrent re-queueing.
"""
from __future__ import annotations
import time
from datetime import datetime, timezone
from typing import Optional, List
from rich.panel import Panel
from rich.table import Table
from rich.box import ROUNDED
from vocab.models import Word, SRSGrade, SessionStats, CardState
from vocab.srs import SRSEngine
from vocab.session_service import create_study_queue
from vocab.db import Database
from vocab.ui.theme import console, render_header, pause_prompt
from vocab.ui.card_views import render_flashcard_front, render_flashcard_back
from vocab.ui.forms import edit_word_form


def run_flashcard_session(
    db: Database,
    group_id: Optional[int] = None,
    limit: int = 20,
    force_all: bool = False,
    shuffle: bool = True,
    auto_add_due: Optional[bool] = None,
    fill_placeholders: bool = True
) -> SessionStats:
    """
    Executes an interactive flashcard review session.
    Cards are selected once within the workload budget; placeholders backfill
    short sessions and repeated attempts stay within the selected batch.
    """
    stats = SessionStats(start_time=datetime.now(timezone.utc))

    # auto_add_due remains accepted for compatibility; sessions use a fixed batch.
    queue = create_study_queue(
        db,
        group_id=group_id,
        limit=limit,
        force_all=force_all,
        fill_placeholders=fill_placeholders,
        shuffle=shuffle,
    )
    words = queue.queue

    if not words:
        render_header("Flashcard Review")
        console.print("[bold bright_green]✦ All caught up! No cards are currently available for review.[/bold bright_green]\n")
        next_session = db.get_recommended_next_session(group_id=group_id)
        if next_session:
            console.print(
                f"[bold cyan]⏰ Recommended Next Session:[/bold cyan] "
                f"[bold bright_white]{next_session['full_label']}[/bold bright_white] "
                f"[dim]({next_session['card_count']} cards mature, ~{next_session['accumulated_capacity']} workload points)[/dim]\n"
            )
        console.print("[dim]You can add more words, switch focus deck, or practice typing mode.[/dim]")
        pause_prompt()
        return stats

    placeholder_count = sum(1 for w in words if getattr(w, "is_placeholder", False))
    new_count = sum(1 for w in words if w.state == CardState.NEW.value)
    due_count = len(words) - placeholder_count - new_count
    if placeholder_count > 0 and due_count == 0 and new_count == 0:
        next_session = db.get_recommended_next_session(group_id=group_id)
        rec_info = f" [dim](suggested review batch: [bold white]{next_session['short_label']}[/bold white], ~{next_session['accumulated_capacity']} cap)[/dim]" if next_session else ""
        console.print(f"[bold cyan]ℹ All caught up! Practicing {placeholder_count} upcoming cards (closest due)[/bold cyan]{rec_info}\n")
    else:
        parts = []
        if due_count > 0:
            parts.append(f"{due_count} due")
        if new_count > 0:
            parts.append(f"{new_count} new")
        if placeholder_count > 0:
            parts.append(f"{placeholder_count} upcoming")
        parts_str = ", ".join(parts) if parts else f"{len(words)} cards"
        if new_count > 0 and (due_count > 0 or placeholder_count > 0):
            parts_str += " • [bold green]alternating[/bold green]"
        next_session = db.get_recommended_next_session(group_id=group_id)
        if next_session and not next_session.get("is_optimal_now"):
            opt_info = f" [dim](suggested review batch: [bold white]{next_session['short_label']}[/bold white], ~{next_session['accumulated_capacity']} cap)[/dim]"
        elif next_session and next_session.get("is_optimal_now"):
            opt_info = " [dim](suggested review batch size)[/dim]"
        else:
            opt_info = ""
        console.print(f"[dim cyan]ℹ Session loaded: {parts_str}{opt_info}[/dim cyan]\n")
    time.sleep(0.4)

    group_obj = db.get_group_by_id(group_id) if group_id else None
    deck_name = group_obj.name if group_obj else "All Groups"

    session_round = 0

    while not queue.is_empty:
        session_round += 1
        current_word = queue.next_card()
        if not current_word:
            break

        recurrent_count = queue.recurrent_counts.get(current_word.id or 0, 0)
        remaining = queue.remaining_count + 1
        recurrent_in_queue = queue.recurrent_active_count

        # Ensure fresh word data from DB if background enrichment updated it
        refreshed = db.get_word_by_id(current_word.id)
        if refreshed:
            refreshed.is_placeholder = getattr(current_word, "is_placeholder", False)
            current_word = refreshed

        # If definition is still missing/pending, resolve it now
        if not current_word.definition or current_word.definition.startswith("[Fetching"):
            from vocab.dictionary import DictionaryService
            zh = DictionaryService.lookup_chinese(current_word.word)
            if zh:
                current_word.definition = zh
                db.update_word(current_word)
            entry = DictionaryService.lookup(current_word.word)
            if entry.phonetic and not current_word.phonetic:
                current_word.phonetic = entry.phonetic
                db.update_word(current_word)

        render_header(f"Review: {deck_name} (Remaining: {remaining} | Recurrent: {recurrent_in_queue})")

        # 1. Show Front of Card
        render_flashcard_front(
            word=current_word,
            queue_index=session_round,
            queue_total=session_round + remaining - 1,
            recurrent_count=recurrent_count
        )

        start_thought_time = time.perf_counter()

        # Wait for user to flip the card
        try:
            user_action = input().strip().lower()
            if user_action in ("q", "quit", "exit"):
                break
            elif user_action == "s":
                queue.queue.insert(0, current_word)
                shuffled_count = queue.shuffle_remaining()
                session_round -= 1
                console.print(f"\n[bold green]↻ Queue shuffled & interleaved! ({shuffled_count} cards remaining)[/bold green]")
                time.sleep(0.8)
                continue
            elif user_action == "e":
                edit_word_form(db, current_word)
                refreshed = db.get_word_by_id(current_word.id)
                if refreshed:
                    current_word = refreshed
                queue.queue.insert(0, current_word)
                session_round -= 1
                continue
            elif user_action == "d":
                confirm = input(f"Delete '{current_word.word}' permanently? [y/N]: ").strip().lower()
                if confirm == "y":
                    db.delete_word(current_word.id)
                    console.print(f"[bold green]✓ Word '{current_word.word}' deleted.[/bold green]")
                    time.sleep(0.8)
                    continue
                else:
                    queue.queue.insert(0, current_word)
                    session_round -= 1
                    continue
        except (KeyboardInterrupt, EOFError):
            break

        thought_time = time.perf_counter() - start_thought_time

        # Check if card is a new word introduction
        is_new_word = (current_word.state == CardState.NEW.value and current_word.reps == 0 and recurrent_count == 0)
        if is_new_word:
            # User studied new word on the front and pressed Enter to continue.
            # Do NOT show the rank 1-4 screen after a new word.
            # Directly transition to LEARNING state, log review, and requeue for active recall.
            review_now = datetime.now(timezone.utc)
            updated_word, scheduled_days = SRSEngine.calculate_next_state(
                current_word, SRSGrade.GOOD, thought_time_seconds=0.0, now=review_now
            )
            updated_word.state = CardState.LEARNING.value
            updated_word.step = 0
            updated_word.reps = 0
            db.update_word(updated_word)
            db.log_review(
                word_id=current_word.id,
                grade=int(SRSGrade.GOOD),
                review_mode="introduction",
                scheduled_days=scheduled_days,
                elapsed_seconds=time.perf_counter() - start_thought_time,
                thought_time_seconds=0.0,
                card_state=CardState.NEW.value, now=review_now
            )
            queue.requeue_card(updated_word, custom_offset=3)
            console.print(f"  [bold cyan]✓ Introduced '{current_word.word}'[/bold cyan] [dim](entered learning queue for recall practice)[/dim]\n")
            time.sleep(0.35)
            continue

        # 2. Show Back of Card with SRS rating (for review & learning recall cards)
        render_header(f"Review: {deck_name} (Remaining: {remaining} | Recurrent: {recurrent_in_queue})")
        render_flashcard_back(
            word=current_word,
            queue_index=session_round,
            queue_total=session_round + remaining - 1,
            recurrent_count=recurrent_count
        )

        # Get Grade
        grade: Optional[SRSGrade] = None
        deleted: bool = False
        while grade is None:
            try:
                choice = input("Your Rating [1-4, s, e, d, q] > ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                choice = "q"

            if choice in ("q", "quit", "exit"):
                grade = None
                break
            elif choice == "s":
                shuffled_count = queue.shuffle_remaining()
                console.print(f"\n[bold green]↻ {shuffled_count} remaining cards shuffled & interleaved![/bold green]\n")
                continue
            elif choice == "e":
                edit_word_form(db, current_word)
                refreshed = db.get_word_by_id(current_word.id)
                if refreshed:
                    current_word = refreshed
                render_header(f"Review: {deck_name} (Remaining: {remaining} | Recurrent: {recurrent_in_queue})")
                render_flashcard_back(
                    word=current_word,
                    queue_index=session_round,
                    queue_total=session_round + remaining - 1,
                    recurrent_count=recurrent_count
                )
                continue
            elif choice == "d":
                confirm = input(f"Delete '{current_word.word}' permanently? [y/N]: ").strip().lower()
                if confirm == "y":
                    db.delete_word(current_word.id)
                    console.print(f"[bold green]✓ Word '{current_word.word}' deleted.[/bold green]\n")
                    deleted = True
                    time.sleep(0.8)
                    break
                else:
                    console.print("[dim]Deletion cancelled.[/dim]\n")
                    continue
            elif choice == "1":
                grade = SRSGrade.AGAIN
            elif choice == "2":
                grade = SRSGrade.HARD
            elif choice == "3":
                grade = SRSGrade.GOOD
            elif choice == "4":
                grade = SRSGrade.EASY
            else:
                console.print("[red]Please enter 1, 2, 3, 4, s to shuffle, e to edit, d to delete, or q to quit.[/red]")

        if deleted:
            continue

        if grade is None:
            # User opted to quit early
            break

        elapsed_sec = time.perf_counter() - start_thought_time

        max_tt = db.get_max_thought_time_threshold() if hasattr(db, "get_max_thought_time_threshold") else 30.0
        is_outlier = (thought_time > max_tt)
        effective_tt = 0.0 if is_outlier else thought_time

        # 3. Calculate Adaptive SRS State with Cognitive Latency & Save to DB
        review_now = datetime.now(timezone.utc)
        updated_word, scheduled_days = SRSEngine.calculate_next_state(
            current_word, grade, thought_time_seconds=effective_tt, now=review_now
        )
        db.update_word(updated_word)
        db.log_review(
            word_id=current_word.id,
            grade=int(grade),
            review_mode="flashcard",
            scheduled_days=scheduled_days,
            elapsed_seconds=elapsed_sec,
            thought_time_seconds=thought_time,
            card_state=current_word.state, now=review_now
        )

        # Check Mastery Qualification (Criterion A or Criterion B)
        mastered_word = db.check_and_update_mastery(current_word.id)
        is_mastered = (mastered_word is not None and mastered_word.state == CardState.MASTERED.value)

        # 4. Handle Recurrent Queueing (incorporates latency)
        if is_mastered:
            queue.completed_word_ids.add(current_word.id)
            stats.mastered_count += 1
            was_requeued = False
        else:
            was_requeued = queue.handle_result(updated_word, grade, thought_time_seconds=effective_tt)

        # Update stats
        stats.total_reviews += 1
        if is_outlier:
            stats.outlier_thought_count += 1
            console.print(f"  [dim yellow]⏱ Thought time: {thought_time:.1f}s (timing outlier > {max_tt:.0f}s — excluded from latency stats)[/dim yellow]")
        elif effective_tt > 0.0:
            stats.total_thought_time += effective_tt
            stats.timed_reviews += 1
            if effective_tt <= 3.0:
                stats.fluent_count += 1
            elif effective_tt <= 7.0:
                stats.steady_count += 1
            else:
                stats.hesitant_count += 1

        if grade == SRSGrade.AGAIN:
            stats.again_count += 1
        elif grade == SRSGrade.HARD:
            stats.hard_count += 1
        elif grade == SRSGrade.GOOD:
            stats.good_count += 1
        elif grade == SRSGrade.EASY:
            stats.easy_count += 1

        # Calculation results expressed purely as flashcard sequence and scheduling
        if is_mastered:
            console.print(f"\n  [bold bright_green]🏆 MASTERED! '{current_word.word}' is retired from review.[/bold bright_green]")
        elif was_requeued:
            console.print("  [dim yellow]↻ Re-queued in session sequence for reinforcement[/dim yellow]")
        elif getattr(current_word, "is_placeholder", False) and grade in (SRSGrade.GOOD, SRSGrade.EASY):
            int_str = SRSEngine.format_interval(scheduled_days)
            console.print(f"  [bold bright_cyan]◷ Early practice complete; next review in {int_str}[/bold bright_cyan]")
        else:
            int_str = SRSEngine.format_interval(scheduled_days)
            console.print(f"  [dim green]✓ Scheduled for {int_str}[/dim green]")

        # Feedback banner
        time.sleep(0.35)

    stats.unique_words = len(queue.completed_word_ids)

    # Rate learning quality & tune adaptive capacity threshold based on load vs. quality
    quality_result = SRSEngine.rate_session_quality(queue=queue, stats=stats)
    tuning_result = db.tune_capacity_threshold(
        load=quality_result["total_load"],
        quality_score=quality_result["quality_score"],
        group_id=group_id
    )

    # Render session wrap-up report
    _render_session_summary(stats, quality_result=quality_result, tuning_result=tuning_result)
    return stats


def _render_session_summary(
    stats: SessionStats,
    quality_result: Optional[Dict[str, Any]] = None,
    tuning_result: Optional[Dict[str, Any]] = None
) -> None:
    """Renders a clean summary report of the completed session."""
    render_header("Session Complete!")

    if stats.total_reviews == 0:
        console.print("[dim]No cards reviewed.[/dim]")
        pause_prompt()
        return

    table = Table(box=ROUNDED, border_style="bright_green", expand=True, title="[bold bright_white]─── ✦ Flashcard Review Summary ───[/bold bright_white]")
    table.add_column("Metric", style="bold cyan")
    table.add_column("Value", style="bold white", justify="right")

    table.add_row("Total Reviews Conducted:", str(stats.total_reviews))
    table.add_row("Unique cards completed:", str(stats.unique_words))
    table.add_row("[red]Again ✕ (Lapses / Recurrent):[/red]", str(stats.again_count))
    table.add_row("[yellow]Hard ▲ (Struggled):[/yellow]", str(stats.hard_count))
    table.add_row("[green]Good ✓ (Solid Recall):[/green]", str(stats.good_count))
    table.add_row("[cyan]Easy ★ (Effortless):[/cyan]", str(stats.easy_count))
    if stats.mastered_count > 0:
        table.add_row("[bold bright_green]🏆 Words Retired (Mastered):[/bold bright_green]", f"[bold bright_green]{stats.mastered_count}[/bold bright_green]")
    table.add_row("Observed recall rate:", f"[bold bright_green]{stats.retention_rate:.1f}%[/bold bright_green]")
    if stats.timed_reviews > 0:
        table.add_row("Average Thought Time:", f"[bold magenta]{stats.avg_thought_time:.1f}s[/bold magenta]")
    if stats.outlier_thought_count > 0:
        table.add_row("[dim]Errand Outliers Disregarded:[/dim]", f"[dim]{stats.outlier_thought_count} card(s)[/dim]")

    if quality_result and quality_result.get("unique_words", 0) > 0:
        q_pct = quality_result["quality_percentage"]
        q_tier = quality_result["quality_tier"]
        tier_color = "bright_green" if q_pct >= 100 else ("yellow" if q_pct >= 80 else "red")
        table.add_section()
        table.add_row("Workload score (heuristic):", f"[{tier_color} bold]{q_pct:.0f}% ({q_tier})[/{tier_color} bold]")
        table.add_row(
            "Attempts per word:",
            f"{quality_result['avg_repetitions']:.2f} [dim](heuristic baseline {quality_result['avg_expected_repetitions']:.2f} for avg diff {quality_result['avg_difficulty']:.1f})[/dim]"
        )
        table.add_row("Session workload:", f"{quality_result['total_load']} workload points")
        if tuning_result and tuning_result.get("delta") != 0:
            d_str = f"+{tuning_result['delta']}" if tuning_result['delta'] > 0 else str(tuning_result['delta'])
            d_color = "bright_green" if tuning_result['delta'] > 0 else "yellow"
            table.add_row("Workload budget (heuristic):", f"{tuning_result['new_threshold']} ([{d_color}]{d_str}[/{d_color}])")

    console.print(table)
    console.print("\n[bold bright_green]✓ Session saved. Return for spaced retrieval practice.[/bold bright_green]")
    pause_prompt()
