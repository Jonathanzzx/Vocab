"""
Statistics, analytics, circadian time-of-day tracking, and latency views using Rich.
"""
from __future__ import annotations
from typing import Dict, Any, List, Optional
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.columns import Columns
from rich.box import ROUNDED, SIMPLE_HEAVY
from vocab.ui.theme import console
from vocab.models import Group, Word


def _generate_bar(ratio: float, width: int = 24, fill_color: str = "green") -> str:
    """Renders a Unicode text progress bar."""
    ratio = max(0.0, min(1.0, ratio))
    filled_blocks = int(round(ratio * width))
    empty_blocks = width - filled_blocks
    return f"[{fill_color}]{'█' * filled_blocks}[/{fill_color}][dim]{'░' * empty_blocks}[/dim]"


def render_stats_dashboard(
    overall_stats: Dict[str, Any],
    groups: List[Group],
    forecast: Dict[str, int],
    selected_group_name: str = "All Groups",
    circadian_periods: Optional[List[Dict[str, Any]]] = None,
    hourly_activity: Optional[List[Dict[str, Any]]] = None,
    latency_stats: Optional[Dict[str, Any]] = None,
) -> None:
    """Renders the comprehensive learning analytics and cognitive circadian dashboard."""
    total_words = overall_stats.get("total_words", 0)
    due_count = overall_stats.get("due_count", 0)
    streak_days = overall_stats.get("streak_days", 0)
    retention_rate = overall_stats.get("retention_rate", 0.0)
    new_count = overall_stats.get("new_count", 0)
    learning_count = overall_stats.get("learning_count", 0)
    young_count = overall_stats.get("young_count", 0)
    mature_count = overall_stats.get("mature_count", 0)

    avg_thought = latency_stats.get("overall_avg_thought_time", 0.0) if latency_stats else 0.0

    # 1. Top metric cards
    card_due = Panel(
        f"[bold bright_red]{due_count}[/bold bright_red]\n[dim]Ready[/dim]",
        title="[bold bright_red]● Due[/bold bright_red]",
        border_style="bright_red",
        box=ROUNDED,
    )
    card_streak = Panel(
        f"[bold bright_yellow]{streak_days}d[/bold bright_yellow]\n[dim]Days[/dim]",
        title="[bold bright_yellow]★ Streak[/bold bright_yellow]",
        border_style="bright_yellow",
        box=ROUNDED,
    )
    card_retention = Panel(
        f"[bold bright_green]{retention_rate:.1f}%[/bold bright_green]\n[dim]7-Day[/dim]",
        title="[bold bright_green]✓ Rate[/bold bright_green]",
        border_style="bright_green",
        box=ROUNDED,
    )
    card_thought = Panel(
        f"[bold bright_magenta]{avg_thought:.1f}s[/bold bright_magenta]\n[dim]Speed[/dim]",
        title="[bold bright_magenta]⏱ Latency[/bold bright_magenta]",
        border_style="bright_magenta",
        box=ROUNDED,
    )
    card_total = Panel(
        f"[bold bright_cyan]{total_words}[/bold bright_cyan]\n[dim]Total[/dim]",
        title="[bold bright_cyan]■ Cards[/bold bright_cyan]",
        border_style="bright_cyan",
        box=ROUNDED,
    )

    console.print(Columns([card_due, card_streak, card_retention, card_thought, card_total], equal=True))
    console.print()

    # 2. Circadian Day Periods & Optimal Study Windows
    if circadian_periods:
        circ_table = Table(
            box=ROUNDED,
            border_style="bright_cyan",
            expand=True,
            title="[bold bright_white]─── Active Time Periods & Circadian Performance ───[/bold bright_white]"
        )
        circ_table.add_column("Time Period", style="bold white", width=24)
        circ_table.add_column("Active Time", justify="right", style="cyan", width=14)
        circ_table.add_column("Reviews", justify="right", width=14)
        circ_table.add_column("Avg Latency", justify="right", style="magenta", width=14)
        circ_table.add_column("Retention Rate", justify="right", style="green", width=18)
        circ_table.add_column("Cognitive Status", justify="center", width=22)

        for p in circadian_periods:
            time_str = f"{p['active_minutes']} mins" if p['active_minutes'] > 0 else "[dim]0m[/dim]"
            latency_str = f"{p['avg_thought_time']}s" if p['avg_thought_time'] > 0 else "[dim]—[/dim]"

            rev_cnt = p['reviews']
            new_cnt = p.get('new_learning_revs', 0)
            if rev_cnt > 0 and 0 < new_cnt < rev_cnt:
                rev_str = f"{rev_cnt} [dim]({new_cnt} new)[/dim]"
            elif rev_cnt > 0 and new_cnt == rev_cnt:
                rev_str = f"{rev_cnt} [dim](all new)[/dim]"
            elif rev_cnt > 0:
                rev_str = str(rev_cnt)
            else:
                rev_str = "0"

            if rev_cnt > 0:
                review_ret = p.get('review_retention_rate')
                if review_ret is not None and new_cnt > 0:
                    ret_str = f"{p['retention_rate']:.1f}% [dim]({review_ret:.0f}% rev)[/dim]"
                elif new_cnt > 0 and p.get('review_revs', 0) == 0:
                    ret_str = f"{p['retention_rate']:.1f}% [dim](new)[/dim]"
                else:
                    ret_str = f"{p['retention_rate']:.1f}%"
            else:
                ret_str = "[dim]—[/dim]"

            circ_table.add_row(
                f"{p['icon']} {p['name']}",
                time_str,
                rev_str,
                latency_str,
                ret_str,
                p['state_label']
            )
        console.print(circ_table)
        console.print("[dim italic]  ℹ Cognitive analysis note: Low retrieval on newly learned words reflects natural memory encoding, not tiredness or fatigue.[/dim italic]")
        console.print()

    # 3. 24-Hour Activity Visualizer
    if hourly_activity:
        max_revs = max([h["reviews"] for h in hourly_activity] or [1])
        hour_blocks = []
        for h in hourly_activity:
            hour_num = h["hour"]
            revs = h["reviews"]
            if revs == 0:
                char = "·"
                color = "dim"
            elif revs < max_revs * 0.33:
                char = "▃"
                color = "blue"
            elif revs < max_revs * 0.66:
                char = "▅"
                color = "bright_cyan"
            else:
                char = "█"
                color = "bold bright_green"
            hour_blocks.append(f"[{color}]{char}[/{color}]")

        chart_line = "".join(f" {b} " for b in hour_blocks)
        labels_line = "".join(f"{h:02d} " for h in range(24))

        chart_panel = Panel(
            f"{chart_line}\n[dim]{labels_line}[/dim]\n[dim]Hours: 00:00 (Midnight) ────────────────── 12:00 (Noon) ────────────────── 23:00 (Night)[/dim]",
            title="[bold bright_white]─── 24-Hour Review Distribution Heatmap ───[/bold bright_white]",
            box=ROUNDED,
            border_style="bright_blue"
        )
        console.print(chart_panel)
        console.print()

    # 4. Cognitive Latency Breakdown & Hesitation Watchlist
    if latency_stats and latency_stats.get("total_timed_reviews", 0) > 0:
        total_timed = latency_stats["total_timed_reviews"]
        c_fluent = latency_stats["count_fluent"]
        c_steady = latency_stats["count_steady"]
        c_hesitant = latency_stats["count_hesitant"]

        lat_table = Table(
            box=ROUNDED,
            border_style="bright_magenta",
            expand=True,
            title="[bold bright_white]─── Cognitive Recall Latency & Fluency Distribution ───[/bold bright_white]"
        )
        lat_table.add_column("Recall Fluency", style="bold", width=24)
        lat_table.add_column("Count", justify="right", width=10)
        lat_table.add_column("Percentage", justify="right", width=12)
        lat_table.add_column("Visual Distribution", width=30)

        categories = [
            ("✦ Fluent Recall (<3s)", c_fluent, "bright_green"),
            ("✓ Steady Retrieval (3-7s)", c_steady, "bright_cyan"),
            ("▲ High Hesitation (>7s)", c_hesitant, "bright_yellow"),
        ]

        for label, count, color in categories:
            pct = (count / total_timed * 100.0) if total_timed > 0 else 0.0
            bar = _generate_bar(pct / 100.0, width=24, fill_color=color)
            lat_table.add_row(f"[{color}]{label}[/{color}]", str(count), f"{pct:.1f}%", bar)

        console.print(lat_table)
        if latency_stats.get("count_outliers", 0) > 0:
            c_out = latency_stats["count_outliers"]
            max_tt = latency_stats.get("max_thought_time_threshold", 30.0)
            console.print(f"[dim]  ⊘ Note: {c_out} errand distraction outlier(s) (>{max_tt:.0f}s) were excluded from latency averages.[/dim]")
        console.print()

        # Hesitation Watchlist
        hesitant_words = latency_stats.get("hesitant_words", [])
        if hesitant_words:
            h_table = Table(
                box=ROUNDED,
                border_style="yellow",
                expand=True,
                title="[bold bright_white]─── ▲ Hesitation Watchlist (Slowest Retrieval Terms) ───[/bold bright_white]"
            )
            h_table.add_column("Term", style="bold bright_cyan", width=24)
            h_table.add_column("Deck", style="bold blue", width=20)
            h_table.add_column("Avg Thought Time", justify="right", style="bold red", width=18)
            h_table.add_column("Last Time", justify="right", style="yellow", width=14)
            h_table.add_column("Lapses", justify="right", style="white", width=10)

            for hw in hesitant_words:
                h_table.add_row(
                    hw.word,
                    hw.group_name or "",
                    f"{hw.avg_thought_time:.1f}s",
                    f"{hw.last_thought_time:.1f}s",
                    str(hw.lapses)
                )
            console.print(h_table)
            console.print("[dim italic]  Adaptive note: The SRS engine automatically scales back intervals and prioritizes review for hesitant words.[/dim italic]")
            console.print()

    # 5. Maturity Distribution Bar
    dist_table = Table(
        box=ROUNDED,
        border_style="bright_cyan",
        expand=True,
        title="[bold bright_white]─── Memory Maturity Distribution ───[/bold bright_white]"
    )
    dist_table.add_column("Stage", style="bold", width=22)
    dist_table.add_column("Count", justify="right", width=10)
    dist_table.add_column("Percentage", justify="right", width=12)
    dist_table.add_column("Visual Distribution", width=30)

    mastered_count = overall_stats.get("mastered_count", 0)
    stages = [
        ("● New Cards", new_count, "blue"),
        ("▲ Learning / Lapsed", learning_count, "bright_yellow"),
        ("◆ Young (<21 days)", young_count, "bright_cyan"),
        ("★ Mature (≥21 days)", mature_count, "bright_green"),
        ("🏆 Mastered (Retired)", mastered_count, "green"),
    ]

    for label, count, color in stages:
        pct = (count / total_words * 100.0) if total_words > 0 else 0.0
        bar = _generate_bar(pct / 100.0, width=24, fill_color=color)
        dist_table.add_row(f"[{color}]{label}[/{color}]", str(count), f"{pct:.1f}%", bar)

    console.print(dist_table)
    console.print()

    # 6. Upcoming Review Forecast
    if forecast:
        fc_table = Table(
            box=ROUNDED,
            border_style="bright_yellow",
            expand=True,
            title="[bold bright_white]─── 7-Day Upcoming Due Forecast ───[/bold bright_white]"
        )
        for day_label in forecast.keys():
            fc_table.add_column(day_label, justify="center", style="bold bright_yellow")

        row_counts = [f"[bold bright_white]{cnt}[/bold bright_white]" for cnt in forecast.values()]
        fc_table.add_row(*row_counts)
        console.print(fc_table)
        console.print()

    # 7. Group Comparison Table
    if groups:
        grp_table = Table(
            box=ROUNDED,
            border_style="bright_blue",
            expand=True,
            title="[bold bright_white]─── Vocabulary Decks Breakdown ───[/bold bright_white]"
        )
        grp_table.add_column("Deck Name", style="bold white")
        grp_table.add_column("Words", justify="right", style="cyan")
        grp_table.add_column("Due Now", justify="right", style="red")
        grp_table.add_column("Progress", width=25)

        for g in groups:
            due = g.due_count
            total = g.word_count
            ratio = ((total - due) / total) if total > 0 else 1.0
            bar = _generate_bar(ratio, width=18, fill_color=g.color or "green")
            grp_table.add_row(
                f"[{g.color or 'white'} bold]{g.name}[/{g.color or 'white'} bold]",
                str(total),
                f"[bold red]● {due}[/bold red]" if due > 0 else "[green]✓ 0[/green]",
                f"{bar} [dim]{int(ratio * 100)}%[/dim]"
            )
        console.print(grp_table)
        console.print()
