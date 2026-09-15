"""
Theme, colors, headers, and UI styling utilities using Rich.
"""
from __future__ import annotations
import os
import sys
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich.align import Align
from rich.rule import Rule


console = Console()

BANNER_ART = r"""
 [bold bright_cyan]██╗   ██╗ ██████╗  ██████╗ █████╗ ██████╗ [/bold bright_cyan]  [bold bright_white]VOCAB STUDIO[/bold bright_white]
 [bold cyan]██║   ██║██╔═══██╗██╔════╝██╔══██╗██╔══██╗[/bold cyan]  [dim cyan]Adaptive Spaced Repetition[/dim cyan]
 [bold cyan]██║   ██║██║   ██║██║     ███████║██████╔╝[/bold cyan]  [bold yellow]Recurrent Memory Engine[/bold yellow]
 [bold deep_sky_blue1]╚██╗ ██╔╝██║   ██║██║     ██╔══██║██╔══██╗[/bold deep_sky_blue1]  [dim]v1.0.0 • Terminal Edition[/dim]
  [bold dodger_blue1]╚████╔╝ ╚██████╔╝╚██████╗██║  ██║██████╔╝[/bold dodger_blue1]
   [bold dodger_blue1]╚═══╝   ╚═════╝  ╚═════╝╚═╝  ╚═╝╚═════╝ [/bold dodger_blue1]
"""


def clear_screen() -> None:
    """Cross-platform screen clear."""
    os.system("cls" if os.name == "nt" else "clear")


def render_header(subtitle: str = "") -> None:
    """Renders the top banner and current context with an elegant rule."""
    clear_screen()
    console.print(BANNER_ART)
    if subtitle:
        console.print(Rule(title=f"[bold bright_cyan]◆ {subtitle} ◆[/bold bright_cyan]", style="bright_blue", characters="─"))
        console.print()


def render_breadcrumb(path: list[str]) -> None:
    """Prints a styled navigation breadcrumb."""
    parts = []
    for i, p in enumerate(path):
        if i == len(path) - 1:
            parts.append(f"[bold bright_white]{p}[/bold bright_white]")
        else:
            parts.append(f"[dim cyan]{p}[/dim cyan]")
    console.print("  " + " [dim]›[/dim] ".join(parts))
    console.print()


def pause_prompt(message: str = "Press Enter to continue...") -> None:
    """Displays a prompt waiting for user to press enter."""
    console.print(f"\n[dim]{message}[/dim]", end="")
    try:
        input()
    except (KeyboardInterrupt, EOFError):
        pass


def make_key_hint(key: str, desc: str) -> str:
    """Formats a keyboard shortcut hint."""
    return f"[bold yellow]\\[{key}][/bold yellow] [white]{desc}[/white]"

