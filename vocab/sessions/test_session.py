"""
Interactive Vocabulary Proficiency Test & Benchmark Session.
"""
from __future__ import annotations
import time
import json
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.box import ROUNDED, DOUBLE
from vocab.db import Database
from vocab.models import Word, CardState
from vocab.test_service import VocabTestService, TestQuestion
from vocab.ui.theme import console, render_header, pause_prompt


def run_test_session(db: Database, group_id: Optional[int] = None) -> None:
    """Main menu and loop for Vocabulary Proficiency Tests & Benchmarks."""
    while True:
        render_header("Vocabulary Proficiency Test & Benchmark")

        table = Table(
            box=ROUNDED,
            border_style="bright_cyan",
            expand=True,
            title="[bold bright_white]─── Choose Testing Mode ───[/bold bright_white]"
        )
        table.add_column("Key", width=6, justify="center", style="bold yellow")
        table.add_column("Test Mode", style="bold bright_white", width=34)
        table.add_column("Source & Scale", style="cyan", width=22)
        table.add_column("Description", style="dim white")

        table.add_row(
            "[1]",
            "General Vocabulary & Literature",
            "OpenTDB API + Fallback",
            "10 mixed literary & lexical multiple-choice questions"
        )
        table.add_row(
            "[2]",
            "CEFR Proficiency Benchmark",
            "A1 → C2 Leveled Battery",
            "Progressive 12-question staircase to evaluate CEFR tier & vocab size"
        )
        table.add_row(
            "[3]",
            "Synonym & Semantic Challenge",
            "Datamuse API + Fallback",
            "10 questions assessing synonym recognition and lexical nuance"
        )
        table.add_section()
        table.add_row(
            "[4]",
            "View Test History & Progression",
            "Database Analytics",
            "Review past scores, estimated vocabulary growth, and speed trends"
        )

        console.print(table)
        console.print("  [bold yellow]\\[b][/bold yellow] [dim]Back to main menu[/dim]\n")

        try:
            choice = input("Select testing option [1-4, b] > ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            break

        if choice in ("b", "back", "q", "exit", ""):
            break
        elif choice == "1":
            _execute_test(db, group_id, test_type="opentdb", title="General Vocabulary Test (OpenTDB)")
        elif choice == "2":
            _execute_test(db, group_id, test_type="cefr_benchmark", title="CEFR Leveled Benchmark Battery")
        elif choice == "3":
            _execute_test(db, group_id, test_type="datamuse_synonym", title="Synonym & Semantic Challenge")
        elif choice == "4":
            _render_test_history_view(db)


def _execute_test(
    db: Database,
    group_id: Optional[int],
    test_type: str,
    title: str
) -> None:
    """Runs a live timed test with outlier tracking and diagnostic evaluation."""
    render_header(title)
    console.print("[dim cyan]✦ Loading questions from API & benchmark banks...[/dim cyan]\n")

    # Fetch questions based on test type
    if test_type == "opentdb":
        questions = VocabTestService.fetch_opentdb_questions(amount=10)
    elif test_type == "cefr_benchmark":
        questions = VocabTestService.get_leveled_benchmark_questions(amount=12)
    elif test_type == "datamuse_synonym":
        questions = VocabTestService.fetch_datamuse_questions(amount=10)
    else:
        questions = VocabTestService.get_leveled_benchmark_questions(amount=10)

    if not questions:
        console.print("[yellow]Could not load test questions at this time.[/yellow]")
        pause_prompt()
        return

    # Check previous test for delta comparison
    prev_tests = db.get_test_history(limit=1, test_type=test_type)
    prev_test = prev_tests[0] if prev_tests else None

    total_q = len(questions)
    user_answers: List[bool] = []
    answered_questions: List[TestQuestion] = []
    missed_questions: List[TestQuestion] = []
    timed_seconds_list: List[float] = []
    outlier_count = 0

    max_tt = db.get_max_thought_time_threshold() if hasattr(db, "get_max_thought_time_threshold") else 30.0

    for idx, q in enumerate(questions, 1):
        render_header(f"{title} [Question {idx}/{total_q}]")

        # Question prompt card
        content = Text()
        content.append(f"Level: {q.cefr_level}  •  Category: {q.category}\n\n", style="bold cyan")
        content.append(f"{q.prompt}\n\n", style="bold bright_white")

        for c_idx, choice_str in enumerate(q.choices, 1):
            content.append(f"  [{c_idx}]  ", style="bold yellow")
            content.append(f"{choice_str}\n", style="bright_white")

        console.print(Panel(
            content,
            box=ROUNDED,
            border_style="bright_blue",
            title=f"[bold bright_white] Q{idx} of {total_q} [/bold bright_white]"
        ))

        start_time = time.time()
        user_choice = None

        while user_choice is None:
            try:
                raw_in = input("\nEnter choice [1-4, q] > ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                raw_in = "q"

            if raw_in in ("q", "quit", "exit"):
                break
            elif raw_in in ("1", "2", "3", "4"):
                user_choice = int(raw_in) - 1
            else:
                console.print("[red]Please enter a valid option: 1, 2, 3, 4, or q to finish early.[/red]")

        if user_choice is None:
            console.print("\n[yellow]Test stopped early.[/yellow]")
            break

        elapsed = time.time() - start_time
        is_outlier = (elapsed > max_tt)

        if is_outlier:
            outlier_count += 1
            console.print(f"  [dim yellow]⏱ Response time: {elapsed:.1f}s (errand outlier > {max_tt:.0f}s excluded from speed stats)[/dim yellow]")
        else:
            timed_seconds_list.append(elapsed)

        is_correct = (user_choice == q.correct_index)
        user_answers.append(is_correct)
        answered_questions.append(q)

        if is_correct:
            console.print(f"\n[bold bright_green]✓ CORRECT! [{q.correct_index + 1}] {q.correct_answer}[/bold bright_green]")
            if q.explanation:
                console.print(f"[dim]{q.explanation}[/dim]")
        else:
            picked_str = q.choices[user_choice]
            console.print(f"\n[bold red]✕ INCORRECT. You selected: [{user_choice + 1}] '{picked_str}'[/bold red]")
            console.print(f"[bold cyan]Correct answer: [{q.correct_index + 1}] '{q.correct_answer}'[/bold cyan]")
            if q.explanation:
                console.print(f"[dim]{q.explanation}[/dim]")
            missed_questions.append(q)

        time.sleep(1.2)

    if not answered_questions:
        return

    # If stopped early with very few questions, ask user whether to save partial attempt
    if len(answered_questions) < 4:
        console.print(f"\n[dim yellow]⚠ Only {len(answered_questions)} question(s) answered (minimum 5 required for a reliable CEFR benchmark).[/dim yellow]")
        try:
            save_ans = input("Do you want to save this partial attempt to history? [y/N] > ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            save_ans = "n"
        if save_ans not in ("y", "yes"):
            console.print("[dim]Partial attempt discarded without saving.[/dim]\n")
            pause_prompt()
            return

    # Calculate analytical proficiency & CEFR metrics
    avg_speed = (sum(timed_seconds_list) / len(timed_seconds_list)) if timed_seconds_list else 0.0
    evaluation = VocabTestService.estimate_proficiency(
        questions=answered_questions,
        user_correct=user_answers,
        avg_response_time=avg_speed
    )

    # Store in database
    details_payload = json.dumps({
        "questions_count": len(answered_questions),
        "correct_count": evaluation["correct_count"],
        "level_breakdown": evaluation["level_breakdown"],
        "avg_speed": round(avg_speed, 2),
        "outlier_count": outlier_count,
        "is_reliable": evaluation.get("is_reliable", True),
        "sample_warning": evaluation.get("sample_warning")
    })

    db.log_test_result(
        test_type=test_type,
        total_questions=evaluation["total_questions"],
        correct_count=evaluation["correct_count"],
        score_pct=evaluation["score_pct"],
        cefr_level=evaluation["cefr_level"],
        estimated_vocab_size=evaluation["estimated_vocab_size"],
        avg_response_time=avg_speed,
        details_json=details_payload
    )

    # Render Summary & Progress Dashboard
    _render_test_results_summary(
        evaluation=evaluation,
        avg_speed=avg_speed,
        outlier_count=outlier_count,
        prev_test=prev_test
    )

    # Offer to save missed words to vocabulary deck
    if missed_questions:
        _handle_save_missed_words(db, missed_questions, group_id)


def _render_test_results_summary(
    evaluation: Dict[str, Any],
    avg_speed: float,
    outlier_count: int,
    prev_test: Optional[Any]
) -> None:
    """Renders the comprehensive results and evaluation panel."""
    render_header("Vocabulary Benchmark Results")

    summary_table = Table(
        box=ROUNDED,
        border_style="bright_magenta",
        expand=True,
        title="[bold bright_white]─── ✦ Proficiency Assessment ✦ ───[/bold bright_white]"
    )
    summary_table.add_column("Metric", style="bold cyan", width=28)
    summary_table.add_column("Your Result", style="bold white", justify="right")

    score_pct = evaluation["score_pct"]
    score_color = "bright_green" if score_pct >= 80 else ("yellow" if score_pct >= 60 else "bright_red")
    summary_table.add_row(
        "Accuracy Score:",
        f"[{score_color} bold]{evaluation['correct_count']} / {evaluation['total_questions']} ({score_pct:.1f}%)[/{score_color} bold]"
    )

    summary_table.add_row(
        "Estimated CEFR Level:",
        f"[bold bright_green]{evaluation['cefr_label']}[/bold bright_green]"
    )

    summary_table.add_row(
        "Estimated Vocabulary Size:",
        f"[bold bright_cyan]~{evaluation['estimated_vocab_size']:,} words[/bold bright_cyan]"
    )

    if avg_speed > 0:
        summary_table.add_row(
            "Average Response Speed:",
            f"[bold magenta]{avg_speed:.1f}s[/bold magenta] [dim]({evaluation['speed_rating']})[/dim]"
        )

    if outlier_count > 0:
        summary_table.add_row(
            "Errand Outliers Disregarded:",
            f"[dim]{outlier_count} question(s) > 30s[/dim]"
        )

    # Progress Delta Comparison
    if prev_test and evaluation.get("is_reliable", True) and prev_test.total_questions >= 5:
        delta_score = score_pct - prev_test.score_pct
        delta_sign = "+" if delta_score >= 0 else ""
        d_color = "bright_green" if delta_score >= 0 else "yellow"
        delta_vocab = evaluation['estimated_vocab_size'] - prev_test.estimated_vocab_size
        v_sign = "+" if delta_vocab >= 0 else ""

        summary_table.add_section()
        summary_table.add_row(
            "Previous Benchmark Score:",
            f"{prev_test.score_pct:.1f}% ({prev_test.cefr_level})  →  [{d_color}]{delta_sign}{delta_score:.1f}%[/{d_color}]"
        )
        summary_table.add_row(
            "Vocabulary Growth Delta:",
            f"~{prev_test.estimated_vocab_size:,}  →  [{d_color}]{v_sign}{delta_vocab:,} words[/{d_color}]"
        )
    elif prev_test:
        summary_table.add_section()
        summary_table.add_row(
            "Previous Attempt:",
            f"{prev_test.score_pct:.1f}% ({prev_test.cefr_level}, ~{prev_test.estimated_vocab_size:,} words) [dim]({prev_test.total_questions}Q)[/dim]"
        )

    console.print(summary_table)
    console.print()

    if evaluation.get("sample_warning"):
        console.print(Panel(
            f"[bold yellow]⚠ {evaluation['sample_warning']}[/bold yellow]",
            box=ROUNDED,
            border_style="yellow",
            title="[bold yellow] Reliability Advisory [/bold yellow]"
        ))
        console.print()

    # CEFR Level Breakdown Table
    breakdown = evaluation.get("level_breakdown", {})
    if breakdown:
        bd_table = Table(box=ROUNDED, border_style="dim cyan", expand=True, title="[bold bright_white]─── Level-by-Level Performance ───[/bold bright_white]")
        for tier in ["A1", "A2", "B1", "B2", "C1", "C2"]:
            bd_table.add_column(f"[bold]{tier}[/bold]", justify="center")

        cells = []
        for tier in ["A1", "A2", "B1", "B2", "C1", "C2"]:
            data = breakdown.get(tier, {"correct": 0, "total": 0})
            tot = data["total"]
            cor = data["correct"]
            if tot == 0:
                cells.append("[dim]—[/dim]")
            else:
                pct = (cor / tot) * 100.0
                c_str = "bright_green" if pct >= 75 else ("yellow" if pct >= 50 else "red")
                cells.append(f"[{c_str}]{cor}/{tot} ({pct:.0f}%)[/{c_str}]")
        bd_table.add_row(*cells)
        console.print(bd_table)
        console.print()

    # Feedback Panel
    console.print(Panel(
        f"[italic bright_white]{evaluation['feedback']}[/italic bright_white]",
        box=ROUNDED,
        border_style="bright_blue",
        title="[bold bright_white] Linguistic Insights [/bold bright_white]"
    ))
    console.print()


def _handle_save_missed_words(
    db: Database,
    missed: List[TestQuestion],
    group_id: Optional[int]
) -> None:
    """Offers to import missed words into user's study deck for SRS reinforcement."""
    valid_words = [q for q in missed if q.word and len(q.word.split()) <= 3]
    if not valid_words:
        pause_prompt()
        return

    groups = db.get_groups()
    if not groups:
        pause_prompt()
        return

    target_group = None
    if group_id:
        target_group = db.get_group_by_id(group_id)
    if not target_group:
        target_group = groups[0]

    console.print(
        f"[bold yellow]✦ Would you like to add {len(valid_words)} missed words to deck '[/bold yellow]"
        f"[bold cyan]{target_group.name}[/bold cyan][bold yellow]' for Spaced Repetition practice? [y/N]: [/bold yellow]",
        end=""
    )
    try:
        ans = input().strip().lower()
    except (KeyboardInterrupt, EOFError):
        ans = "n"

    if ans in ("y", "yes"):
        added_count = 0
        for q in valid_words:
            # Check if word already exists in database
            existing = db.find_word(q.word)
            if not existing:
                clean_def = q.explanation.replace(f"Correct answer: '{q.correct_answer}'", "").strip(" :.,")
                if not clean_def:
                    clean_def = f"Synonym/meaning: {q.correct_answer}"
                w = Word(
                    id=None,
                    group_id=target_group.id or 1,
                    word=q.word,
                    definition=clean_def,
                    pos="term",
                    example=q.prompt if len(q.prompt) < 120 else "",
                    state=CardState.NEW.value
                )
                db.add_word(w)
                added_count += 1

        console.print(f"\n[bold green]✓ Successfully added {added_count} words to deck '{target_group.name}'! They are ready in your review queue.[/bold green]\n")

    pause_prompt()


def _render_test_history_view(db: Database) -> None:
    """Displays past test logs and CEFR progression over time."""
    render_header("Vocabulary Test History & Progress")

    analytics = db.get_test_analytics()
    if analytics["total_tests"] == 0:
        console.print("[yellow]No vocabulary tests recorded yet. Take a benchmark test to begin tracking your progress![/yellow]\n")
        pause_prompt()
        return

    # Overview Stats Table
    stats_table = Table.grid(padding=(0, 2), expand=True)
    stats_table.add_column(justify="center")
    stats_table.add_column(justify="center")
    stats_table.add_column(justify="center")
    stats_table.add_column(justify="center")

    tot = analytics["total_tests"]
    avg_sc = analytics["avg_score"]
    best_sc = analytics["best_score"]
    latest_bench = analytics.get("latest_benchmark") or analytics.get("latest_test")
    latest_level = latest_bench.cefr_level if latest_bench else "—"
    latest_vocab = f"~{latest_bench.estimated_vocab_size:,}" if latest_bench else "—"

    stats_table.add_row(
        f"[dim]Total Tests:[/dim] [bold bright_cyan]{tot}[/bold bright_cyan]",
        f"[dim]Average Score:[/dim] [bold yellow]{avg_sc:.1f}%[/bold yellow]",
        f"[dim]Best Score:[/dim] [bold bright_green]{best_sc:.1f}%[/bold bright_green]",
        f"[dim]Certified Level:[/dim] [bold bright_magenta]{latest_level} ({latest_vocab} words)[/bold bright_magenta]"
    )

    console.print(Panel(
        stats_table,
        box=ROUNDED,
        border_style="bright_blue",
        title="[bold bright_white] Lifetime Benchmark Progression [/bold bright_white]"
    ))
    console.print()

    # Detailed history table
    history = db.get_test_history(limit=15)
    hist_table = Table(
        box=ROUNDED,
        border_style="bright_cyan",
        expand=True,
        title="[bold bright_white]─── Recent Benchmark Attempts ───[/bold bright_white]"
    )
    hist_table.add_column("Date / Time", style="dim", width=18)
    hist_table.add_column("Test Mode", style="bold white", width=24)
    hist_table.add_column("Score", justify="center", width=16)
    hist_table.add_column("CEFR Level", justify="center", style="bold green", width=16)
    hist_table.add_column("Est. Vocab", justify="right", style="cyan", width=14)
    hist_table.add_column("Avg Speed", justify="right", style="magenta", width=12)

    for item in history:
        date_str = item.tested_at[:16].replace("T", " ")
        mode_label = (
            "OpenTDB General" if item.test_type == "opentdb"
            else ("CEFR Benchmark" if item.test_type == "cefr_benchmark" else "Synonym Drill")
        )
        is_prelim = (item.total_questions < 5)
        prelim_tag = " [dim yellow]*(prelim)[/dim yellow]" if is_prelim else ""
        score_badge = f"{item.correct_count}/{item.total_questions} ({item.score_pct:.0f}%)"
        speed_str = f"{item.avg_response_time:.1f}s" if item.avg_response_time > 0 else "—"
        cefr_display = f"{item.cefr_level}{prelim_tag}"
        hist_table.add_row(
            date_str,
            mode_label,
            score_badge,
            cefr_display,
            f"~{item.estimated_vocab_size:,}",
            speed_str
        )

    console.print(hist_table)
    console.print()
    pause_prompt()
