"""
Multiple-choice speed quiz session with recurrent re-drill on mistakes.
"""
from __future__ import annotations
import random
import time
from datetime import datetime, timezone
from typing import Optional, List
from rich.panel import Panel
from rich.table import Table
from rich.box import ROUNDED
from vocab.models import Word, SRSGrade, SessionStats, CardState
from vocab.srs import SRSEngine, RecurrentSessionQueue
from vocab.db import Database
from vocab.ui.theme import console, render_header, pause_prompt
from vocab.ui.card_views import render_quiz_question


def run_quiz_session(
    db: Database,
    group_id: Optional[int] = None,
    limit: int = 15,
    force_all: bool = False,
    shuffle: bool = True,
    auto_add_due: Optional[bool] = None,
    fill_placeholders: bool = True
) -> SessionStats:
    """Runs a rapid-fire multiple choice vocabulary quiz."""
    stats = SessionStats(start_time=datetime.now(timezone.utc))

    if auto_add_due is None:
        setting_val = db.get_setting("auto_add_due", default="true")
        auto_add_due = setting_val.lower() in ("true", "1", "yes")

    words = db.get_session_words(
        group_id=group_id,
        limit=limit,
        force_all=force_all,
        fill_placeholders=fill_placeholders
    )

    if not words:
        render_header("Speed Quiz")
        console.print("[bold bright_green]✦ All caught up! No cards currently available for quiz review.[/bold bright_green]\n")
        next_session = db.get_recommended_next_session(group_id=group_id)
        if next_session:
            console.print(
                f"[bold cyan]⏰ Recommended Next Session:[/bold cyan] "
                f"[bold bright_white]{next_session['full_label']}[/bold bright_white] "
                f"[dim]({next_session['card_count']} cards mature, ~{next_session['accumulated_capacity']} workload points)[/dim]\n"
            )
        pause_prompt()
        return stats

    # We need at least a few words to generate distractors
    all_words = db.get_words(group_id=group_id, limit=100)
    if len(all_words) < 4:
        all_words = db.get_words(limit=100)
        if len(all_words) < 4:
            render_header("Speed Quiz")
            console.print("[yellow]You need at least 4 words in the database to run multiple choice quiz mode.[/yellow]")
            pause_prompt()
            return stats

    placeholder_count = sum(1 for w in words if getattr(w, "is_placeholder", False))
    new_count = sum(1 for w in words if w.state in ("new", "learning") and not getattr(w, "is_placeholder", False))
    due_count = len(words) - placeholder_count - new_count

    if placeholder_count > 0 and due_count == 0 and new_count == 0:
        next_session = db.get_recommended_next_session(group_id=group_id)
        rec_info = f" [dim](suggested review batch: [bold white]{next_session['short_label']}[/bold white])[/dim]" if next_session else ""
        console.print(f"[bold cyan]ℹ All caught up! Practicing {placeholder_count} upcoming cards with closest due times.[/bold cyan]{rec_info}\n")
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
        opt_info = f" [dim](suggested review batch: [bold white]{next_session['short_label']}[/bold white])[/dim]" if next_session and not next_session.get("is_optimal_now") else ""
        console.print(f"[dim cyan]ℹ Loaded {parts_str}{opt_info}[/dim cyan]\n")
    time.sleep(0.4)

    recent_seq = db.get_recent_review_sequence(group_id=group_id, limit=40)
    queue = RecurrentSessionQueue(
        words,
        reinsert_offset=3,
        enable_shuffling=shuffle,
        enable_interleaving=shuffle,
        previous_sequence=recent_seq
    )
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

        # Pick 3 distractors
        distractor_candidates = [w.word for w in all_words if w.word.lower() != current_word.word.lower()]
        distractors = random.sample(distractor_candidates, min(3, len(distractor_candidates)))
        choices = distractors + [current_word.word]
        random.shuffle(choices)
        correct_index = choices.index(current_word.word) + 1

        render_header(f"Speed Quiz: {deck_name} (Remaining: {remaining} | Recurrent: {recurrent_in_queue})")

        render_quiz_question(
            word=current_word,
            choices=choices,
            queue_index=session_round,
            queue_total=session_round + remaining - 1,
            recurrent_count=recurrent_count
        )

        start_time = time.perf_counter()

        selected_num = None
        while selected_num is None:
            try:
                choice_input = input("Option [1-4, s, q] > ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                choice_input = "q"

            if choice_input in ("q", "quit", "exit"):
                break
            elif choice_input == "s":
                shuffled_count = queue.shuffle_remaining()
                console.print(f"\n[bold green]↻ Remaining {shuffled_count} questions shuffled & interleaved![/bold green]\n")
                continue
            elif choice_input in ("1", "2", "3", "4"):
                selected_num = int(choice_input)
            else:
                console.print("[red]Please enter 1, 2, 3, 4, s to shuffle, or q to quit.[/red]")

        if selected_num is None:
            break

        elapsed_sec = time.perf_counter() - start_time

        if selected_num == correct_index:
            # Correct!
            grade = SRSGrade.GOOD
            console.print(f"\n[bold green]✓ CORRECT! '{current_word.word}'[/bold green]")
            if current_word.example:
                console.print(f"[dim italic]\"{current_word.example}\"[/dim italic]")
            stats.good_count += 1
        else:
            # Incorrect!
            grade = SRSGrade.AGAIN
            chosen_word = choices[selected_num - 1]
            console.print(f"\n[bold red]✕ INCORRECT! You picked '{chosen_word}'.[/bold red]")
            console.print(f"[bold cyan]Correct answer: [{correct_index}] '{current_word.word}'[/bold cyan]")
            if current_word.mnemonic:
                console.print(f"[yellow]Mnemonic: ★ {current_word.mnemonic}[/yellow]")
            stats.again_count += 1

        max_tt = db.get_max_thought_time_threshold() if hasattr(db, "get_max_thought_time_threshold") else 30.0
        is_outlier = (elapsed_sec > max_tt)
        effective_tt = 0.0 if is_outlier else elapsed_sec

        # Recognition is practice-only: preserve the free-recall schedule.
        updated_word = current_word
        scheduled_days = current_word.interval_days
        db.log_review(
            word_id=current_word.id,
            grade=int(grade),
            review_mode="quiz",
            scheduled_days=scheduled_days,
            elapsed_seconds=elapsed_sec,
            thought_time_seconds=elapsed_sec,
            card_state=current_word.state
        )

        # Check Mastery Qualification (Criterion A or Criterion B)
        mastered_word = db.check_and_update_mastery(current_word.id)
        is_mastered = (mastered_word is not None and mastered_word.state == CardState.MASTERED.value)

        if is_mastered:
            queue.completed_word_ids.add(current_word.id)
            stats.mastered_count += 1
            was_requeued = False
        else:
            was_requeued = queue.handle_result(updated_word, grade, thought_time_seconds=effective_tt)

        stats.total_reviews += 1
        if is_outlier:
            stats.outlier_thought_count += 1
            console.print(f"  [dim yellow]⏱ Quiz response: {elapsed_sec:.1f}s (timing outlier > {max_tt:.0f}s — excluded from latency stats)[/dim yellow]")
        elif effective_tt > 0.0:
            stats.total_thought_time += effective_tt
            stats.timed_reviews += 1
            if effective_tt <= 3.0:
                stats.fluent_count += 1
            elif effective_tt <= 7.0:
                stats.steady_count += 1
            else:
                stats.hesitant_count += 1

        if is_mastered:
            console.print(f"\n[bold bright_green]🏆 MASTERED! '{current_word.word}' is retired from review.[/bold bright_green]")
        elif was_requeued:
            console.print("[dim red]↻ Missed! Added back to queue to re-test you in a moment.[/dim red]")
        else:
            int_str = SRSEngine.format_interval(scheduled_days)
            if getattr(current_word, "is_placeholder", False) and grade in (SRSGrade.GOOD, SRSGrade.EASY):
                console.print(f"[bold bright_cyan]✓ Practice recorded; recall schedule unchanged[/bold bright_cyan]")
            else:
                console.print(f"[dim green]✓ Practice recorded; recall schedule unchanged[/dim green]")

        time.sleep(1.0)

    stats.unique_words = len(queue.completed_word_ids)

    # Rate learning quality & tune adaptive capacity threshold based on load vs. quality
    quality_result = SRSEngine.rate_session_quality(queue=queue, stats=stats)
    tuning_result = db.tune_capacity_threshold(
        load=quality_result["total_load"],
        quality_score=quality_result["quality_score"],
        group_id=group_id
    )

    # Summary
    _render_quiz_summary(stats, quality_result=quality_result, tuning_result=tuning_result)
    return stats


def _render_quiz_summary(
    stats: SessionStats,
    quality_result: Optional[Dict[str, Any]] = None,
    tuning_result: Optional[Dict[str, Any]] = None
) -> None:
    render_header("Quiz Finished!")
    if stats.total_reviews == 0:
        pause_prompt()
        return

    table = Table(box=ROUNDED, border_style="bright_magenta", expand=True, title="[bold bright_white]─── ✦ Speed Quiz Summary ───[/bold bright_white]")
    table.add_column("Metric", style="bold cyan")
    table.add_column("Value", style="bold white", justify="right")

    table.add_row("Total Questions Answered:", str(stats.total_reviews))
    table.add_row("Unique words completed:", str(stats.unique_words))
    table.add_row("[green]✓ Correct Answers:[/green]", f"[bold green]{stats.good_count + stats.easy_count}[/bold green]")
    table.add_row("[red]✕ Incorrect (Re-drilled):[/red]", f"[bold red]{stats.again_count}[/bold red]")
    if stats.mastered_count > 0:
        table.add_row("[bold bright_green]🏆 Words Retired (Mastered):[/bold bright_green]", f"[bold bright_green]{stats.mastered_count}[/bold bright_green]")
    table.add_row("Quiz Accuracy:", f"[bold bright_green]{stats.retention_rate:.1f}%[/bold bright_green]")
    if stats.timed_reviews > 0:
        table.add_row("Average Response Time:", f"[bold magenta]{stats.avg_thought_time:.1f}s[/bold magenta]")
    if stats.outlier_thought_count > 0:
        table.add_row("[dim]Errand Outliers Disregarded:[/dim]", f"[dim]{stats.outlier_thought_count} question(s)[/dim]")

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
    pause_prompt()
