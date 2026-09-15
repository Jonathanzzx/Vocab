"""Render real UI components with sample data, without opening the user's database.

Run: .venv/Scripts/python.exe scripts/preview_ui.py
"""
from io import StringIO
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rich.console import Console
from vocab.models import Word, Group
from vocab.ui import theme, menu, card_views, stats_views


def main():
    group = Group(1, "Academic vocabulary", word_count=128, due_count=12)
    stats = dict(total_words=128, due_count=12, new_count=24, learning_count=8,
                 young_count=54, mature_count=42, streak_days=7,
                 total_recent_reviews=64, retention_rate=87.5)
    output = Path(__file__).resolve().parents[1] / "docs" / "preview.html"
    panels = []
    for label, width, height, kind in [
        ("Large terminal · 120 × 50", 120, 50, "home"),
        ("Standard terminal · 80 × 24", 80, 24, "home"),
        ("Narrow terminal · 40 × 20", 40, 20, "home"),
        ("Short terminal · 80 × 16", 80, 16, "home"),
        ("Flashcard", 112, 40, "card"), ("Statistics", 112, 50, "stats"),
    ]:
        console = Console(file=StringIO(), width=width, height=height, record=True, theme=theme.PALETTE)
        for module in (theme, menu, card_views, stats_views):
            module.console = console
        if kind == "home":
            menu.render_main_dashboard(group, stats, [group])
            console.print("[accent]Choose >[/accent] ")
        elif kind == "card":
            theme.render_header("Flashcards · Academic vocabulary")
            word = Word(1, 1, "empirical", "Based on observation or experiment, rather than theory alone.",
                        phonetic="/ɪmˈpɪrɪkəl/", pos="adjective", state="review", reps=3,
                        interval_days=15, group_name=group.name,
                        example="The hypothesis needs empirical evidence.",
                        mnemonic="Connect empirical with experience: knowledge from observation.")
            card_views.render_flashcard_back(word, 4, 12)
        else:
            theme.render_header("Study statistics")
            stats_views.render_stats_dashboard(stats, [group], {"Tomorrow": 6, "In 2 days": 9, "In 7 days": 18})
        svg = "\n".join(line.rstrip() for line in console.export_svg(title=label).splitlines())
        panels.append(f'<section><h2>{label}</h2>{svg}</section>')
    output.write_text('''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Vocab · Interface preview</title>
<style>body{background:#101720;color:#e2e8f0;font:16px system-ui;margin:40px auto;max-width:1280px;padding:0 24px}h1{font-weight:500}p{color:#94a3b8}section{margin:48px 0}h2{font-size:16px;font-weight:500;color:#7dd3cf}svg{max-width:100%;height:auto}</style>
<h1>Vocab / Interface preview</h1><p>Actual terminal components rendered with sample data. Your vocabulary database is not used.</p>
''' + "".join(panels) + "</html>", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
