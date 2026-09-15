"""
Main navigation menu and dashboard renderer.
"""
from __future__ import annotations
from typing import Optional, Dict, Any, List
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.columns import Columns
from rich.box import ROUNDED
from vocab.ui.theme import console, render_header
from vocab.models import Group


def render_main_dashboard(
    active_group: Optional[Group],
    stats: Dict[str, Any],
    groups: List[Group],
    auto_add_due: bool = True
) -> None:
    """Renders the top status bar and structured main menu options."""
    render_header("Spaced Repetition Terminal Studio")

    # Group focus banner
    focus_name = active_group.name if active_group else "All Groups (Combined)"
    focus_color = active_group.color if active_group else "bright_cyan"

    due_count = stats.get("due_count", 0)
    total_words = stats.get("total_words", 0)
    mastered_count = stats.get("mastered_count", 0)
    streak_days = stats.get("streak_days", 0)
    retention_rate = stats.get("retention_rate", 0.0)

    # Status Bar
    status_table = Table.grid(padding=(0, 2), expand=True)
    status_table.add_column(justify="left", no_wrap=True)
    status_table.add_column(justify="center", no_wrap=True)
    status_table.add_column(justify="right", no_wrap=True)

    deck_pill = f"◆ [{focus_color} bold]{focus_name}[/{focus_color} bold]"
    next_session = stats.get("next_session")
    mastered_str = f"  [dim]•[/dim]  [bold bright_green]🏆 {mastered_count} Mastered[/bold bright_green]" if mastered_count > 0 else ""
    if due_count > 0:
        if next_session and next_session.get("is_optimal_now"):
            due_pill = f"[bold bright_red]● {due_count} Due[/bold bright_red] [bold bright_green](Optimal now!)[/bold bright_green]  [dim]•[/dim]  [bright_cyan]{total_words} Cards[/bright_cyan]{mastered_str}"
        elif next_session:
            due_pill = f"[bold bright_red]● {due_count} Due[/bold bright_red]  [dim]•[/dim]  [bold cyan]Optimal: {next_session['short_label']}[/bold cyan]  [dim]•[/dim]  [bright_cyan]{total_words} Cards[/bright_cyan]{mastered_str}"
        else:
            due_pill = f"[bold bright_red]● {due_count} Due[/bold bright_red]  [dim]•[/dim]  [bright_cyan]{total_words} Cards[/bright_cyan]{mastered_str}"
    else:
        next_pill_str = f"  [dim]•[/dim]  [bold cyan]Optimal: {next_session['short_label']}[/bold cyan]" if next_session else ""
        due_pill = f"[bold bright_green]✓ Caught Up[/bold bright_green]{next_pill_str}  [dim]•[/dim]  [bright_cyan]{total_words} Cards[/bright_cyan]{mastered_str}"

    streak_pill = f"[bold bright_yellow]★ {streak_days}d Streak[/bold bright_yellow]"
    retention_pill = f"[bold green]✦ {retention_rate:.0f}% Recall[/bold green]" if retention_rate > 0 else "[dim]✦ —[/dim]"

    status_table.add_row(
        deck_pill,
        due_pill,
        f"{streak_pill}  [dim]•[/dim]  {retention_pill}"
    )

    console.print(Panel(
        status_table,
        box=ROUNDED,
        border_style="bright_blue",
        title="[bold bright_white] Dashboard Overview [/bold bright_white]"
    ))
    console.print()

    # Menu Options Table
    menu_table = Table(
        box=ROUNDED,
        border_style="bright_blue",
        expand=True,
        title="[bold bright_white]─── Studio Actions ───[/bold bright_white]"
    )
    menu_table.add_column("Key", width=6, justify="center", style="bold yellow")
    menu_table.add_column("Action", style="bold bright_white", min_width=36)
    menu_table.add_column("Description", style="dim white")

    if due_count > 0:
        if next_session and next_session.get("is_optimal_now"):
            due_badge = f" [bold bright_green]({due_count} ready • Optimal now!)[/bold bright_green]"
            due_desc = f"Optimal session ready ({due_count} cards, ~{next_session['accumulated_capacity']}/{next_session['max_capacity']} cap, minimal placeholders)"
        elif next_session:
            due_badge = f" [bold bright_yellow]({due_count} ready • Optimal: {next_session['short_label']})[/bold bright_yellow]"
            due_desc = f"Next optimal session: {next_session['full_label']} ({next_session['card_count']} cards, ~{next_session['accumulated_capacity']}/{next_session['max_capacity']} cap, minimal placeholders)"
        else:
            due_badge = f" [bold bright_red]({due_count} ready)[/bold bright_red]"
            due_desc = "Adaptive recurrent spaced repetition session"
    elif next_session:
        due_badge = f" [bold green](all caught up! Optimal: {next_session['short_label']})[/bold green]"
        due_desc = f"Next optimal session: {next_session['full_label']} ({next_session['card_count']} cards, ~{next_session['accumulated_capacity']}/{next_session['max_capacity']} cap)"
    else:
        due_badge = " [bold green](all caught up!)[/bold green]"
        due_desc = "Practice upcoming cards ahead of time (closest due)"

    # Study & Memory Drills
    menu_table.add_row("[1]", f"Review Due Flashcards{due_badge}", due_desc)
    menu_table.add_row("[2]", "Active Recall Challenge", "Type words from definitions with recurrent correction")
    menu_table.add_row("[3]", "Speed Multiple-Choice Quiz", "Fast 4-choice recognition drill with speed bonuses")
    menu_table.add_row("[t]", "Vocabulary Test & Benchmark", "Test CEFR proficiency, estimate vocab size, and track progress")
    menu_table.add_section()

    # Vocabulary Library
    menu_table.add_row("[4]", "Select / Switch Focus Deck", "Choose a specific group or study all decks combined")
    menu_table.add_row("[5]", "Auto-Add Words", "Continuous entry with automatic background Chinese & phonics")
    menu_table.add_row("[6]", "Manage, Edit & Delete Words", "Browse, search, edit definitions, or inspect cards")
    menu_table.add_section()

    # Analytics & Deck Management
    menu_table.add_row("[7]", "Memory Analytics & Forecast", "Deep dive into forgetting curves, circadian rhythm, & latency")
    menu_table.add_row("[8]", "Manage Groups / Decks", "Create, rename, customize color, or delete decks")
    menu_table.add_row("[9]", "Import / Export / Decks", "Import/Export CSV, JSON, or reload curated starter decks")
    menu_table.add_section()

    # Settings & Exit
    menu_table.add_row("\\[q]", "Exit", "Save and exit the application")

    console.print(menu_table)
    console.print()

