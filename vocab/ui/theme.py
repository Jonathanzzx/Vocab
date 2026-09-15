"""Shared, restrained terminal presentation."""
from __future__ import annotations
from rich.console import Console
from rich.theme import Theme
from rich.rule import Rule
from rich.text import Text
from rich.panel import Panel
from rich.box import ROUNDED
from rich.table import Table

PALETTE = Theme({
    "accent": "#7dd3cf", "muted": "#94a3b8", "border": "#475569",
    "heading": "bold #e2e8f0", "success": "#86c8a0", "warning": "#e5ba73",
    "cyan": "#7dd3cf", "bright_cyan": "#7dd3cf", "blue": "#8caacb",
    "bright_blue": "#8caacb", "green": "#86c8a0", "bright_green": "#86c8a0",
    "yellow": "#e5ba73", "bright_yellow": "#e5ba73", "red": "#ed9c9c",
    "bright_red": "#ed9c9c", "magenta": "#b4a8cc", "bright_magenta": "#b4a8cc",
})
console = Console(theme=PALETTE, highlight=False)
BANNER_ART = "[heading]V O C A B[/heading]   [muted]Vocabulary practice[/muted]"


def clear_screen():
    if console.is_terminal:
        console.clear()


def render_header(subtitle=""):
    clear_screen()
    console.print()
    console.print(BANNER_ART)
    console.print("[muted]Spaced review · Active recall · Personal library[/muted]")
    console.print()
    console.print(Rule(Text(subtitle, style="heading"), style="border", align="left"))
    console.print()


def metric_panel(value, label, detail=""):
    text = Text(str(value), style=PALETTE.styles["heading"])
    if detail:
        text.append("\n" + detail, style="not bold #94a3b8")
    return Panel(text, title=Text(label, style=PALETTE.styles["accent"]), title_align="left",
                 border_style=PALETTE.styles["border"], box=ROUNDED, padding=(1, 2))


def metric_grid(panels, width):
    columns = len(panels) if width >= len(panels) * 22 else (2 if width >= 52 else 1)
    grid = Table.grid(expand=True, padding=(0, 1))
    for _ in range(columns):
        grid.add_column(ratio=1)
    for start in range(0, len(panels), columns):
        row = panels[start:start + columns]
        grid.add_row(*row, *([""] * (columns - len(row))))
    return grid


def render_breadcrumb(path):
    console.print(Text("  ›  ".join(path), style="muted"))
    console.print()


def pause_prompt(message="Press Enter to continue..."):
    console.print(Text("\n" + message, style="muted"), end="")
    try:
        input()
    except (KeyboardInterrupt, EOFError):
        pass


def make_key_hint(key, desc):
    return f"[accent]\\[{key}][/accent] {desc}"
