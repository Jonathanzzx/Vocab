"""
Main Application Coordinator for Vocab Memorization App.
"""
from __future__ import annotations
import os
import sys
import argparse
from typing import Optional
from prompt_toolkit import prompt
from rich.table import Table
from rich.box import ROUNDED
from vocab.db import Database
from vocab.models import Group
from vocab.seed_data import seed_database
from vocab.exporter import DataExporter
from vocab.ui.theme import console, render_header, pause_prompt
from vocab.ui.menu import read_dashboard_command
from vocab.ui.stats_views import render_stats_dashboard
from vocab.ui.forms import (
    select_group_prompt,
    add_word_form,
    manage_groups_menu,
    browse_words_view,
    show_words_list,
)
from vocab.sessions.flashcard_session import run_flashcard_session
from vocab.sessions.typing_session import run_typing_session
from vocab.sessions.quiz_session import run_quiz_session
from vocab.sessions.test_session import run_test_session
from vocab.dictionary import BackgroundEnricher


class VocabApp:
    def __init__(self, db_path: Optional[str] = None):
        self.db = Database(db_path)
        self.active_group_id: Optional[int] = None
        self._ensure_initial_data()
        # Preserve saved schedules; history replay is an explicit maintenance action.

    def _ensure_initial_data(self) -> None:
        """Seeds curated decks only on first run if database is brand new and empty."""
        seeded = self.db.get_setting("example_decks_initialized")
        if seeded:
            return
        groups = self.db.get_groups()
        if not groups:
            seed_database(self.db)
        self.db.set_setting("example_decks_initialized", "true")

    @property
    def active_group(self) -> Optional[Group]:
        if self.active_group_id is None:
            return None
        return self.db.get_group_by_id(self.active_group_id)

    def run_interactive(self) -> None:
        """Main interactive application loop."""
        while True:
            groups = self.db.get_groups()
            stats = self.db.get_stats_summary(self.active_group_id)
            active_grp = self.active_group

            try:
                cmd = read_dashboard_command(active_grp, stats, groups)
            except (KeyboardInterrupt, EOFError):
                break

            if cmd in ("q", "quit", "exit"):
                render_header("Goodbye!")
                console.print("[bold cyan]Happy learning! Come back tomorrow to keep your streak alive![/bold cyan]\n")
                break

            elif cmd in ("t", "test", "10"):
                # Vocabulary Proficiency Test & Benchmark
                run_test_session(self.db, self.active_group_id)

            elif cmd == "1":
                # Flashcard review
                limit = 25
                run_flashcard_session(
                    self.db,
                    self.active_group_id,
                    limit=limit,
                    force_all=False,
                    fill_placeholders=True
                )

            elif cmd == "2":
                # Active recall typing challenge
                limit = 15
                run_typing_session(
                    self.db,
                    self.active_group_id,
                    limit=limit,
                    force_all=False,
                    fill_placeholders=True
                )

            elif cmd == "3":
                # Speed Multiple-Choice Quiz
                limit = 15
                run_quiz_session(
                    self.db,
                    self.active_group_id,
                    limit=limit,
                    force_all=False,
                    fill_placeholders=True
                )

            elif cmd == "4":
                # Switch active focus group
                render_header("Select Study Focus")
                gid = select_group_prompt(groups, include_all=True)
                if gid != -1:
                    self.active_group_id = gid
                    new_group = self.active_group
                    name = new_group.name if new_group else "All Groups (Combined)"
                    console.print(f"\n[bold green]✓ Switched focus deck to: '{name}'[/bold green]")
                    pause_prompt()

            elif cmd == "5":
                # Add new word
                render_header("Add New Vocabulary Word")
                add_word_form(self.db, self.active_group_id)

            elif cmd == "6":
                # Browse & search with filtering and sorting
                show_words_list(self.db, group_id=self.active_group_id, interactive=True)

            elif cmd == "7":
                # Stats dashboard
                render_header("Memory & Cognitive Analytics")
                forecast = self.db.get_due_forecast(self.active_group_id, days_ahead=7)
                circadian = self.db.get_circadian_periods_summary(self.active_group_id)
                hourly = self.db.get_hourly_activity(self.active_group_id)
                latency = self.db.get_latency_analytics(self.active_group_id)

                render_stats_dashboard(
                    overall_stats=stats,
                    groups=groups,
                    forecast=forecast,
                    selected_group_name=active_grp.name if active_grp else "All Groups",
                    circadian_periods=circadian,
                    hourly_activity=hourly,
                    latency_stats=latency
                )
                pause_prompt()

            elif cmd == "8":
                # Manage groups
                manage_groups_menu(self.db)

            elif cmd == "9":
                # Import / Export
                self._import_export_menu()

    def _import_export_menu(self) -> None:
        """Submenu for importing, exporting, and resetting curated decks."""
        while True:
            render_header("Import, Export & Data Tools")

            table = Table(
                box=ROUNDED,
                border_style="bright_blue",
                expand=True,
                title="[bold bright_white]─── Import, Export & Data Management ───[/bold bright_white]"
            )
            table.add_column("Key", width=6, justify="center", style="bold yellow")
            table.add_column("Action", style="bold white", width=34)
            table.add_column("Format / Scope", style="cyan", width=18)
            table.add_column("Description", style="dim")

            table.add_row("[1]", "Export vocabulary to CSV", "CSV File", "Export all or focused deck words")
            table.add_row("[2]", "Export vocabulary to JSON", "JSON File", "Full export with SRS metadata")
            table.add_section()
            table.add_row("[3]", "Import vocabulary from CSV", "CSV File", "Import words and auto-assign to decks")
            table.add_row("[4]", "Import vocabulary from JSON", "JSON File", "Restore words and review states")
            table.add_section()
            table.add_row("[5]", "Reload Curated Starter Decks", "Built-in Decks", "Restore GRE, Idioms, Tech starter decks")
            table.add_row("[6]", "Synchronize Card States", "Database Sync", "Recalculate card states from review history")
            table.add_row("[7]", "Remove Thought Time Outliers", "Data Cleanup", "Remove errand distractions from review logs & words")

            console.print(table)
            console.print("  [bold yellow]\\[b][/bold yellow] [dim]Back to main menu[/dim]\n")

            choice = input("Choice > ").strip().lower()
            if choice in ("b", "back", "q", ""):
                break

            elif choice == "1":
                path = prompt("Enter target CSV file path [e.g. backup.csv]: ").strip() or "vocab_export.csv"
                try:
                    count = DataExporter.export_to_csv(self.db, path, self.active_group_id)
                    console.print(f"\n[bold green]✓ Exported {count} words to '{path}'.[/bold green]")
                except Exception as e:
                    console.print(f"[red]Export failed: {e}[/red]")
                pause_prompt()

            elif choice == "2":
                path = prompt("Enter target JSON file path [e.g. backup.json]: ").strip() or "vocab_export.json"
                try:
                    count = DataExporter.export_to_json(self.db, path, self.active_group_id)
                    console.print(f"\n[bold green]✓ Exported {count} words to '{path}'.[/bold green]")
                except Exception as e:
                    console.print(f"[red]Export failed: {e}[/red]")
                pause_prompt()

            elif choice == "3":
                path = prompt("Enter CSV file path to import: ").strip()
                if os.path.exists(path):
                    try:
                        g_cnt, w_cnt = DataExporter.import_from_csv(self.db, path)
                        console.print(f"\n[bold green]✓ Imported {w_cnt} words into {g_cnt} groups![/bold green]")
                    except Exception as e:
                        console.print(f"[red]Import failed: {e}[/red]")
                else:
                    console.print(f"[red]File not found: '{path}'[/red]")
                pause_prompt()

            elif choice == "4":
                path = prompt("Enter JSON file path to import: ").strip()
                if os.path.exists(path):
                    try:
                        g_cnt, w_cnt = DataExporter.import_from_json(self.db, path)
                        console.print(f"\n[bold green]✓ Imported {w_cnt} words into {g_cnt} groups![/bold green]")
                    except Exception as e:
                        console.print(f"[red]Import failed: {e}[/red]")
                else:
                    console.print(f"[red]File not found: '{path}'[/red]")
                pause_prompt()

            elif choice == "5":
                added = seed_database(self.db)
                console.print(f"\n[bold green]✓ Curated starter decks verified! ({added} new words added).[/bold green]")
                pause_prompt()

            elif choice == "6":
                synced = self.db.sync_all_word_states()
                console.print(f"\n[bold green]✓ Word memory states synchronized with review logs! ({synced} cards updated).[/bold green]")
                pause_prompt()

            elif choice == "7":
                res = self.db.cleanup_thought_time_outliers()
                cleaned_logs = res["cleaned_logs_count"]
                updated_words = res["updated_words_count"]
                console.print(f"\n[bold green]✓ Outlier cleanup complete! ({cleaned_logs} errand distraction logs cleared, {updated_words} word averages restored).[/bold green]")
                pause_prompt()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Vocab - Terminal Vocabulary Memorization App with Adaptive Recurrent SRS"
    )
    parser.add_argument(
        "action",
        nargs="?",
        choices=["interactive", "review", "typing", "quiz", "test", "stats", "add", "groups", "seed", "export", "import", "sync", "list", "words", "browse", "clean-outliers"],
        default="interactive",
        help="Action to perform (default: interactive menu)"
    )
    parser.add_argument("--group", "-g", type=str, default=None, help="Name or ID of group to target")
    parser.add_argument("--db", type=str, default=None, help="Path to SQLite database file")
    parser.add_argument("--file", "-f", type=str, default=None, help="File path for import/export")
    parser.add_argument("--limit", "-n", type=int, default=20, help="Max cards per session or list view")
    parser.add_argument("--all", "-a", action="store_true", help="Include non-due cards (cram mode)")
    parser.add_argument(
        "--shuffle", "-s",
        dest="shuffle",
        action="store_true",
        default=True,
        help="Enable category interleaving and stochastic queue shuffling (default: enabled)"
    )
    parser.add_argument(
        "--no-shuffle",
        dest="shuffle",
        action="store_false",
        help="Disable queue shuffling (maintain strict sequential order)"
    )
    parser.add_argument(
        "--auto-add-due",
        dest="auto_add_due",
        action="store_true",
        default=None,
        help="Automatically add cards to the session as they become due (default: on)"
    )
    parser.add_argument(
        "--no-auto-add-due",
        dest="auto_add_due",
        action="store_false",
        help="Do not add cards to session as they become due"
    )
    parser.add_argument(
        "--placeholders",
        dest="fill_placeholders",
        action="store_true",
        default=True,
        help="Backfill short sessions with non-due placeholder cards (default: enabled)"
    )
    parser.add_argument(
        "--no-placeholders",
        dest="fill_placeholders",
        action="store_false",
        help="Do not backfill short sessions with placeholder cards"
    )
    parser.add_argument(
        "--sort",
        type=str,
        default="id",
        help="Field to sort words by (word, due, state, ease, interval, reps, lapses, created, pos, deck)"
    )
    parser.add_argument(
        "--order",
        type=str,
        choices=["asc", "desc"],
        default="desc",
        help="Sort direction for word list (asc, desc)"
    )
    parser.add_argument(
        "--state",
        type=str,
        default=None,
        choices=["new", "learning", "review", "relearning"],
        help="Filter word list by card state"
    )
    parser.add_argument(
        "--due-only",
        action="store_true",
        default=False,
        help="Filter word list to only currently due cards"
    )
    parser.add_argument(
        "--pos",
        type=str,
        default=None,
        help="Filter word list by part of speech"
    )
    parser.add_argument(
        "--tag",
        type=str,
        default=None,
        help="Filter word list by tag"
    )
    parser.add_argument(
        "--search", "-q",
        type=str,
        default=None,
        help="Search query keyword for filtering words"
    )
    parser.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Pagination offset when listing words"
    )
    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        default=False,
        help="Launch interactive mode for word browser"
    )

    args = parser.parse_args()
    app = VocabApp(db_path=args.db)

    # Resolve group if specified
    if args.group:
        if args.group.isdigit():
            app.active_group_id = int(args.group)
        else:
            grp = app.db.get_group_by_name(args.group)
            if grp:
                app.active_group_id = grp.id
            else:
                console.print(f"[yellow]Group '{args.group}' not found. Defaulting to all groups.[/yellow]")

    try:
        if args.action == "interactive":
            app.run_interactive()
        elif args.action == "review":
            run_flashcard_session(
                app.db,
                app.active_group_id,
                limit=args.limit,
                force_all=args.all,
                shuffle=args.shuffle,
                auto_add_due=args.auto_add_due,
                fill_placeholders=args.fill_placeholders
            )
        elif args.action == "typing":
            run_typing_session(
                app.db,
                app.active_group_id,
                limit=args.limit,
                force_all=args.all,
                shuffle=args.shuffle,
                auto_add_due=args.auto_add_due,
                fill_placeholders=args.fill_placeholders
            )
        elif args.action == "quiz":
            run_quiz_session(
                app.db,
                app.active_group_id,
                limit=args.limit,
                force_all=args.all,
                shuffle=args.shuffle,
                auto_add_due=args.auto_add_due,
                fill_placeholders=args.fill_placeholders
            )
        elif args.action == "test":
            run_test_session(app.db, app.active_group_id)
        elif args.action == "stats":
            stats = app.db.get_stats_summary(app.active_group_id)
            groups = app.db.get_groups()
            forecast = app.db.get_due_forecast(app.active_group_id, days_ahead=7)
            circadian = app.db.get_circadian_periods_summary(app.active_group_id)
            hourly = app.db.get_hourly_activity(app.active_group_id)
            latency = app.db.get_latency_analytics(app.active_group_id)
            active_name = app.active_group.name if app.active_group else "All Groups"
            render_stats_dashboard(
                stats, groups, forecast,
                selected_group_name=active_name,
                circadian_periods=circadian,
                hourly_activity=hourly,
                latency_stats=latency
            )
        elif args.action == "add":
            add_word_form(app.db, app.active_group_id)
        elif args.action == "groups":
            manage_groups_menu(app.db)
        elif args.action == "seed":
            count = seed_database(app.db)
            console.print(f"[bold green]✓ Added {count} curated cards.[/bold green]")
        elif args.action == "export":
            filepath = args.file or "vocab_export.csv"
            if filepath.endswith(".json"):
                count = DataExporter.export_to_json(app.db, filepath, app.active_group_id)
            else:
                count = DataExporter.export_to_csv(app.db, filepath, app.active_group_id)
            console.print(f"[bold green]✓ Exported {count} words to {filepath}.[/bold green]")
        elif args.action == "import":
            if not args.file or not os.path.exists(args.file):
                console.print("[red]Please specify a valid file to import with --file <path>.[/red]")
                sys.exit(1)
            if args.file.endswith(".json"):
                g, w = DataExporter.import_from_json(app.db, args.file)
            else:
                g, w = DataExporter.import_from_csv(app.db, args.file)
            console.print(f"[bold green]✓ Imported {w} words into {g} groups from {args.file}.[/bold green]")
        elif args.action == "sync":
            cnt = app.db.sync_all_word_states()
            console.print(f"[bold green]✓ Successfully synchronized memory states for all words ({cnt} updated).[/bold green]")
        elif args.action == "clean-outliers":
            res = app.db.cleanup_thought_time_outliers()
            console.print(f"[bold green]✓ Thought time outliers removed! ({res['cleaned_logs_count']} errand logs cleared, {res['updated_words_count']} words restored).[/bold green]")
        elif args.action in ("list", "words", "browse"):
            show_words_list(
                app.db,
                group_id=app.active_group_id,
                search=args.search,
                state=args.state,
                pos=args.pos,
                tag=args.tag,
                due_only=args.due_only,
                sort_by=args.sort,
                sort_order=args.order,
                limit=args.limit,
                offset=args.offset,
                interactive=args.interactive
            )
    finally:
        BackgroundEnricher.shutdown(wait=False)


if __name__ == "__main__":
    main()
