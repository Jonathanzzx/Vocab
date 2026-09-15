"""
Card display components for flashcards, typing recall, and quiz modes.
"""
from __future__ import annotations
import re
from typing import Dict, Optional, List
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.columns import Columns
from rich.align import Align
from rich.box import ROUNDED, DOUBLE, HEAVY, MINIMAL
from vocab.models import Word, SRSGrade, CardState
from vocab.srs import SRSEngine
from vocab.ui.theme import console, make_key_hint


def _highlight_word_in_example(example: str, target: str) -> Text:
    """Highlights occurrences of target word or its root inside an example sentence."""
    text = Text(example, style="white")
    if not target or not example:
        return text

    # Escape for regex and match word boundaries or common suffixes
    clean_target = re.escape(target.strip())
    pattern = re.compile(rf"\b{clean_target}(?:ed|ing|s|es|ly|tion|al)?\b", re.IGNORECASE)

    for match in pattern.finditer(example):
        start, end = match.span()
        text.stylize("bold yellow underline", start, end)

    return text


def render_flashcard_front(
    word: Word,
    queue_index: int,
    queue_total: int,
    recurrent_count: int = 0
) -> None:
    """Renders the front face of a flashcard."""
    # Build header badges
    group_text = f"[bold white on blue] {word.group_name or 'Default'} [/bold white on blue]"
    progress_text = f"[bold bright_cyan]Card {queue_index}/{queue_total}[/bold bright_cyan]"
    
    status_parts = [group_text, progress_text]
    if getattr(word, "is_placeholder", False):
        status_parts.append(f"[bold cyan on dark_blue] ◷ UPCOMING ({word.format_due_time()}) [/bold cyan on dark_blue]")

    if word.state == CardState.NEW.value:
        status_parts.append("[bold bright_green]● NEW[/bold bright_green]")
    elif word.state in (CardState.LEARNING.value, CardState.RELEARNING.value):
        status_parts.append("[bold magenta]▲ LEARNING[/bold magenta]")
    else:
        status_parts.append(f"[bold bright_blue]✓ REVIEW (Rep {word.reps})[/bold bright_blue]")

    if recurrent_count > 0:
        status_parts.append(f"[bold yellow reverse] ↻ Recurrent Round {recurrent_count + 1} [/bold yellow reverse]")

    header_line = "  ".join(status_parts)

    content = Text()
    content.append("\n")
    content.append(f"  {word.word}\n", style="bold bright_cyan")
    content.append("\n")

    has_sub = False
    if word.phonetic or word.pos or word.tags:
        content.append("  ")
        if word.phonetic:
            content.append(word.phonetic, style="italic bright_green")
            has_sub = True
        if word.pos:
            if has_sub:
                content.append("   ")
            content.append(f"({word.pos})", style="italic yellow")
            has_sub = True
        if word.tags:
            if has_sub:
                content.append("   ")
            content.append(f"tags: {word.tags}", style="dim cyan")
            has_sub = True
        content.append("\n\n")

    is_new = (word.state == CardState.NEW.value)

    if is_new and recurrent_count == 0:
        if word.definition and not word.definition.startswith("[Fetching"):
            content.append("  Definition / Meaning:\n", style="bold yellow")
            content.append(f"  {word.definition}\n\n", style="bold bright_white")
        if word.example:
            content.append("  Example:\n", style="bold cyan")
            content.append(f"  \"{word.example}\"\n\n", style="italic white")
        if word.mnemonic:
            content.append(f"  ★ Mnemonic: {word.mnemonic}\n\n", style="bold yellow")
        content.append("  [New word introduction — study the definition, then press Enter to continue]\n", style="dim cyan")
    else:
        content.append("  Try to recall the definition, context, and usage...\n", style="dim")

    subtitle = (
        "[bold yellow]Press [Enter] to continue[/bold yellow]  [dim]│[/dim]  [bold yellow]\\[s][/bold yellow] [dim]Shuffle[/dim]  [dim]│[/dim]  [bold yellow]\\[a][/bold yellow] [dim]Auto-add[/dim]  [dim]│[/dim]  [bold yellow]\\[e][/bold yellow] [dim]Edit[/dim]  [dim]│[/dim]  [bold yellow]\\[d][/bold yellow] [dim]Del[/dim]  [dim]│[/dim]  [bold yellow]\\[q][/bold yellow] [dim]Quit[/dim]"
        if (is_new and recurrent_count == 0)
        else "[bold yellow]Press [Enter] to reveal[/bold yellow]  [dim]│[/dim]  [bold yellow]\\[s][/bold yellow] [dim]Shuffle[/dim]  [dim]│[/dim]  [bold yellow]\\[a][/bold yellow] [dim]Auto-add[/dim]  [dim]│[/dim]  [bold yellow]\\[e][/bold yellow] [dim]Edit[/dim]  [dim]│[/dim]  [bold yellow]\\[d][/bold yellow] [dim]Del[/dim]  [dim]│[/dim]  [bold yellow]\\[q][/bold yellow] [dim]Quit[/dim]"
    )

    card_panel = Panel(
        content,
        title=f"[bold white] {header_line} [/bold white]",
        subtitle=subtitle,
        border_style="bright_cyan",
        box=ROUNDED,
        padding=(1, 2),
    )

    console.print()
    console.print(card_panel)
    console.print()


def render_flashcard_back(
    word: Word,
    queue_index: int,
    queue_total: int,
    recurrent_count: int = 0
) -> None:
    """Renders the revealed back face of a flashcard with SRS rating options."""
    group_text = f"[bold white on blue] {word.group_name or 'Default'} [/bold white on blue]"
    progress_text = f"[bold bright_cyan]Card {queue_index}/{queue_total}[/bold bright_cyan]"
    
    status_parts = [group_text, progress_text]
    if getattr(word, "is_placeholder", False):
        status_parts.append(f"[bold cyan on dark_blue] ◷ UPCOMING ({word.format_due_time()}) [/bold cyan on dark_blue]")

    if word.state == CardState.NEW.value:
        status_parts.append("[bold bright_green]● NEW[/bold bright_green]")
    elif word.state in (CardState.LEARNING.value, CardState.RELEARNING.value):
        status_parts.append("[bold magenta]▲ LEARNING[/bold magenta]")
    else:
        status_parts.append(f"[bold bright_blue]✓ REVIEW (Rep {word.reps})[/bold bright_blue]")

    if recurrent_count > 0:
        status_parts.append(f"[bold yellow reverse] ↻ Recurrent Round {recurrent_count + 1} [/bold yellow reverse]")

    header_line = "  ".join(status_parts)

    body = Table.grid(padding=(0, 2))
    body.add_column("Key", style="bold cyan", width=14)
    body.add_column("Value", style="white")

    # Word header
    term_text = Text(word.word, style="bold bright_cyan")
    if word.phonetic:
        term_text.append(f"  {word.phonetic}", style="italic bright_green")
    if word.pos:
        term_text.append(f"  ({word.pos})", style="italic yellow")
    body.add_row("Word:", term_text)
    body.add_row("", "")

    # Definition
    body.add_row("Meaning:", Text(word.definition, style="bold bright_white"))

    # Example sentence
    if word.example:
        body.add_row("", "")
        example_text = _highlight_word_in_example(word.example, word.word)
        body.add_row("Example:", example_text)

    # Mnemonic or Root Memory Aid
    if word.mnemonic:
        body.add_row("", "")
        mnemonic_text = Text(f"★ {word.mnemonic}", style="bold yellow")
        body.add_row("Mnemonic:", mnemonic_text)

    # Spaced Repetition Stats bar
    body.add_row("", "")
    srs_meta = Text()
    srs_meta.append(f"Reps: {word.reps}  │  Lapses: {word.lapses}  │  Ease: {word.ease_factor:.2f}  │  Interval: {SRSEngine.format_interval(word.interval_days)}", style="dim")
    body.add_row("SRS Stats:", srs_meta)

    card_panel = Panel(
        body,
        title=f"[bold white] {header_line} [/bold white]",
        border_style="bright_green",
        box=ROUNDED,
        padding=(1, 2),
    )

    console.print()
    console.print(card_panel)

    # Render adaptive rating buttons with interval previews
    previews = SRSEngine.preview_intervals(word)

    btn_table = Table(box=ROUNDED, border_style="dim", show_header=True, expand=True)
    btn_table.add_column("[1] Again ✕", justify="center", style="bold red")
    btn_table.add_column("[2] Hard ▲", justify="center", style="bold yellow")
    btn_table.add_column("[3] Good ✓", justify="center", style="bold green")
    btn_table.add_column("[4] Easy ★", justify="center", style="bold bright_cyan")

    btn_table.add_row(
        f"Forgot / Re-test\n[dim cyan]Next: {previews[SRSGrade.AGAIN]}[/dim cyan]",
        f"Struggled\n[dim cyan]Next: {previews[SRSGrade.HARD]}[/dim cyan]",
        f"Recalled OK\n[dim cyan]Next: {previews[SRSGrade.GOOD]}[/dim cyan]",
        f"Mastered\n[dim cyan]Next: {previews[SRSGrade.EASY]}[/dim cyan]",
    )

    console.print(btn_table)
    console.print("  " + "  [dim]│[/dim]  ".join([
        make_key_hint("1-4", "Rate recall"),
        make_key_hint("s", "Shuffle"),
        make_key_hint("a", "Auto-add"),
        make_key_hint("e", "Edit"),
        make_key_hint("d", "Delete"),
        make_key_hint("q", "Save & Exit"),
    ]))
    console.print()


def render_typing_prompt(
    word: Word,
    queue_index: int,
    queue_total: int,
    recurrent_count: int = 0
) -> None:
    """Renders the prompt for active recall typing mode."""
    group_text = f"[bold white on blue] {word.group_name or 'Default'} [/bold white on blue]"
    progress_text = f"[bold bright_cyan]Card {queue_index}/{queue_total}[/bold bright_cyan]"
    status_line = f"{group_text}  {progress_text}"

    if getattr(word, "is_placeholder", False):
        due_str = word.format_due_time()
        status_line += f"  [bold cyan on dark_blue] ◷ UPCOMING ({due_str}) [/bold cyan on dark_blue]"
    if word.state == CardState.NEW.value:
        status_line += "  [bold bright_green]● NEW[/bold bright_green]"
    elif word.state in (CardState.LEARNING.value, CardState.RELEARNING.value):
        status_line += "  [bold magenta]▲ LEARNING[/bold magenta]"
    else:
        status_line += f"  [bold bright_blue]✓ REVIEW (Rep {word.reps})[/bold bright_blue]"
    if recurrent_count > 0:
        status_line += "  [bold yellow reverse] ↻ Recurrent Re-test [/bold yellow reverse]"

    body = Table.grid(padding=(0, 2))
    body.add_column("Field", style="bold cyan", width=14)
    body.add_column("Content", style="white")

    if word.pos:
        body.add_row("Type:", Text(f"({word.pos})", style="italic yellow"))
    body.add_row("Meaning:", Text(word.definition, style="bold bright_white"))

    if word.example:
        # Mask the target word in the example sentence with blanks
        blanked = re.sub(re.escape(word.word), "[ _____ ]", word.example, flags=re.IGNORECASE)
        body.add_row("Context:", Text(blanked, style="italic dim"))

    body.add_row("", "")
    body.add_row("Word Hint:", Text(word.masked_word(), style="bold bright_yellow"))

    panel = Panel(
        body,
        title=f"[bold white] {status_line} [/bold white]",
        subtitle="[dim]Type word & press [bold yellow][Enter][/bold yellow]  │  [bold yellow]:s[/bold yellow] Shuffle  │  [bold yellow]:a[/bold yellow] Auto-add  │  [bold yellow]skip[/bold yellow] Reveal[/dim]",
        border_style="bright_yellow",
        box=ROUNDED,
        padding=(1, 2)
    )

    console.print()
    console.print(panel)
    console.print()


def render_quiz_question(
    word: Word,
    choices: List[str],
    queue_index: int,
    queue_total: int,
    recurrent_count: int = 0
) -> None:
    """Renders a multiple choice speed quiz question."""
    group_text = f"[bold white on blue] {word.group_name or 'Default'} [/bold white on blue]"
    progress_text = f"[bold bright_cyan]Question {queue_index}/{queue_total}[/bold bright_cyan]"
    status_line = f"{group_text}  {progress_text}"

    if getattr(word, "is_placeholder", False):
        due_str = word.format_due_time()
        status_line += f"  [bold cyan on dark_blue] ◷ UPCOMING ({due_str}) [/bold cyan on dark_blue]"
    if word.state == CardState.NEW.value:
        status_line += "  [bold bright_green]● NEW[/bold bright_green]"
    elif word.state in (CardState.LEARNING.value, CardState.RELEARNING.value):
        status_line += "  [bold magenta]▲ LEARNING[/bold magenta]"
    else:
        status_line += f"  [bold bright_blue]✓ REVIEW (Rep {word.reps})[/bold bright_blue]"
    if recurrent_count > 0:
        status_line += "  [bold yellow reverse] ↻ Recurrent Re-test [/bold yellow reverse]"

    content = Text()
    content.append("\n  Definition:\n", style="bold cyan")
    content.append(f"  \"{word.definition}\"\n\n", style="bold bright_white")

    if word.pos:
        content.append("  Part of speech: ", style="dim")
        content.append(f"{word.pos}\n\n", style="italic yellow")

    content.append("  Choose the correct word:\n", style="dim")

    for i, choice in enumerate(choices, 1):
        content.append(f"   [{i}]  ", style="bold yellow")
        content.append(f"{choice}\n", style="bold bright_white")

    panel = Panel(
        content,
        title=f"[bold white] {status_line} [/bold white]",
        subtitle="[bold yellow][1-4][/bold yellow] [dim]Select option[/dim]  [dim]│[/dim]  [bold yellow]\\[s][/bold yellow] [dim]Shuffle[/dim]  [dim]│[/dim]  [bold yellow]\\[a][/bold yellow] [dim]Auto-add[/dim]  [dim]│[/dim]  [bold yellow]\\[q][/bold yellow] [dim]Quit[/dim]",
        border_style="bright_magenta",
        box=ROUNDED,
        padding=(1, 2),
    )

    console.print()
    console.print(panel)
    console.print()
