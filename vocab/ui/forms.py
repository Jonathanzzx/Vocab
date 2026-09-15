"""
Forms and interactive prompts for adding/editing words, managing groups, and search.
"""
from __future__ import annotations
import time
from typing import Optional, List, Tuple, Dict, Any, Callable
from prompt_toolkit import prompt
from prompt_toolkit.shortcuts import radiolist_dialog, input_dialog, yes_no_dialog
from rich.table import Table
from rich.panel import Panel
from rich.box import ROUNDED
from rich.text import Text
from vocab.ui.theme import console, pause_prompt
from vocab.models import Group, Word
from vocab.db import Database
from vocab.dictionary import DictionaryService, BackgroundEnricher


def select_group_prompt(groups: List[Group], include_all: bool = True) -> Optional[int]:
    """
    Prompts user to select a group using a structured table.
    Returns group_id or None for 'All Groups', or -1 if canceled.
    """
    table = Table(box=ROUNDED, border_style="bright_blue", expand=True, title="[bold bright_white]─── Select Vocabulary Deck ───[/bold bright_white]")
    table.add_column("Key", width=6, justify="center", style="bold yellow")
    table.add_column("Deck Name", style="bold white", width=28)
    table.add_column("Due Status", width=18)
    table.add_column("Total Cards", justify="right", style="cyan", width=14)
    table.add_column("Description", style="dim")

    options = []
    if include_all:
        total_due = sum(g.due_count for g in groups)
        total_words = sum(g.word_count for g in groups)
        due_lbl = f"[bold bright_red]● {total_due} due[/bold bright_red]" if total_due > 0 else "[bold green]✓ caught up[/bold green]"
        table.add_row("[0]", "[bold bright_white]All Groups (Combined)[/bold bright_white]", due_lbl, f"{total_words} cards", "Study all decks combined")
        options.append(0)

    for idx, g in enumerate(groups, 1):
        due_str = f"[bold bright_red]● {g.due_count} due[/bold bright_red]" if g.due_count > 0 else "[green]✓ caught up[/green]"
        table.add_row(
            f"[{idx}]",
            f"[{g.color} bold]{g.name}[/{g.color} bold]",
            due_str,
            f"{g.word_count} cards",
            g.description or "—"
        )
        options.append(idx)

    console.print()
    console.print(table)
    console.print("  [bold yellow]\\[c][/bold yellow] [dim]Cancel selection[/dim]\n")

    while True:
        try:
            choice = input("Enter selection > ").strip().lower()
            if choice in ("c", "q", "cancel", ""):
                return -1
            choice_num = int(choice)
            if choice_num == 0 and include_all:
                return None
            if 1 <= choice_num <= len(groups):
                return groups[choice_num - 1].id
        except ValueError:
            pass
        console.print("[red]Invalid selection, please enter a valid deck number or 'c' to cancel.[/red]")


def review_unexpected_words(db: Database, unexpected_words: List[Dict[str, Any]]) -> None:
    """
    Presents unexpected words and potential typos at the end of a session,
    providing interactive options to apply suggestions, edit manually, keep, or delete.
    """
    if not unexpected_words:
        return

    console.print("\n[bold yellow]─── Unexpected Words & Typo Review ───[/bold yellow]")
    console.print("[dim]The following word(s) were not recognized in standard dictionaries and may contain typos:[/dim]\n")

    table = Table(box=ROUNDED, show_header=True, header_style="bold cyan")
    table.add_column("#", justify="center", width=4, style="bold cyan")
    table.add_column("Word Added", style="bold red", min_width=16)
    table.add_column("Suggested Correction", style="bold green", min_width=20)
    table.add_column("Status", style="dim", min_width=14)

    has_suggestions = False
    for idx, item in enumerate(unexpected_words, 1):
        sug = item.get("suggestion")
        if sug:
            has_suggestions = True
            sug_str = f"[bold green]{sug}[/bold green]"
            status_str = "[yellow]Likely Typo[/yellow]"
        else:
            sug_str = "[dim](No suggestion)[/dim]"
            status_str = "[dim red]Unrecognized[/dim red]"
        table.add_row(str(idx), item["word"], sug_str, status_str)

    console.print(table)
    console.print("")

    console.print("[bold yellow]Review Options:[/bold yellow]")
    if has_suggestions:
        console.print("  [bold green][A][/bold green] Apply all suggestions (auto-fix typos)")
    console.print("  [bold cyan][R][/bold cyan] Review and edit one by one")
    console.print("  [bold white][K][/bold white] Keep all as-is (e.g. valid jargon, names, or slang)")
    console.print("  [bold red][D][/bold red] Delete all unexpected words from deck")

    default_choice = "a" if has_suggestions else "k"
    prompt_str = f"Choose action [{default_choice.upper()}/r/k/d] (Enter for default): "

    try:
        choice = prompt(prompt_str).strip().lower()
    except (KeyboardInterrupt, EOFError):
        console.print("\n[dim]Skipped typo review.[/dim]\n")
        return

    if not choice:
        choice = default_choice

    if choice in ("a", "apply", "yes", "y") and has_suggestions:
        console.print("\n[bold green]Applying suggestions...[/bold green]")
        for item in unexpected_words:
            sug = item.get("suggestion")
            if not sug:
                continue
            word_obj = db.get_word_by_id(item["id"])
            if word_obj:
                old_text = word_obj.word
                word_obj.word = sug
                word_obj.definition = "[Fetching Chinese meaning...]"
                word_obj.phonetic = ""
                word_obj.pos = ""
                db.update_word(word_obj)
                BackgroundEnricher.enrich(
                    db=db,
                    word_id=word_obj.id,
                    word_text=sug,
                    needs_chinese=True
                )
                console.print(f"  [bold green]✓ Fixed:[/bold green] '{old_text}' -> [bold cyan]'{sug}'[/bold cyan]")
        console.print("")

    elif choice in ("d", "delete", "del"):
        console.print("\n[bold red]Deleting unexpected words...[/bold red]")
        for item in unexpected_words:
            db.delete_word(item["id"])
            console.print(f"  [red]✗ Deleted '{item['word']}'[/red]")
        console.print("")

    elif choice in ("r", "review", "edit", "e"):
        console.print("\n[bold cyan]Reviewing unexpected words:[/bold cyan]")
        for idx, item in enumerate(unexpected_words, 1):
            w_obj = db.get_word_by_id(item["id"])
            if not w_obj:
                continue
            sug = item.get("suggestion")
            console.print(f"\n[bold]#{idx}: '{w_obj.word}'[/bold]" + (f" (Suggestion: [bold green]{sug}[/bold green])" if sug else ""))
            options_text = []
            if sug:
                options_text.append(f"[1] Accept suggestion ('{sug}')")
            options_text.append("[2] Edit word manually")
            options_text.append("[3] Keep as-is")
            options_text.append("[4] Delete word")
            for opt in options_text:
                console.print(f"  {opt}")

            try:
                sub_choice = prompt("Select [1/2/3/4] (Enter=keep): ").strip()
            except (KeyboardInterrupt, EOFError):
                break

            if sub_choice == "1" and sug:
                w_obj.word = sug
                w_obj.definition = "[Fetching Chinese meaning...]"
                w_obj.phonetic = ""
                w_obj.pos = ""
                db.update_word(w_obj)
                BackgroundEnricher.enrich(db=db, word_id=w_obj.id, word_text=sug, needs_chinese=True)
                console.print(f"  [bold green]✓ Updated to '{sug}'[/bold green]")
            elif sub_choice == "2":
                try:
                    manual_word = prompt(f"Enter correct word [{w_obj.word}]: ").strip()
                except (KeyboardInterrupt, EOFError):
                    manual_word = ""
                if manual_word and manual_word != w_obj.word:
                    w_obj.word = manual_word
                    w_obj.definition = "[Fetching Chinese meaning...]"
                    w_obj.phonetic = ""
                    w_obj.pos = ""
                    db.update_word(w_obj)
                    BackgroundEnricher.enrich(db=db, word_id=w_obj.id, word_text=manual_word, needs_chinese=True)
                    console.print(f"  [bold green]✓ Updated to '{manual_word}'[/bold green]")
                else:
                    console.print("  [dim]Kept as-is.[/dim]")
            elif sub_choice == "4":
                db.delete_word(w_obj.id)
                console.print(f"  [red]✗ Deleted '{w_obj.word}'[/red]")
            else:
                console.print(f"  [dim]Kept '{w_obj.word}' as-is.[/dim]")
    else:
        console.print("[dim]Kept all unexpected words as-is.[/dim]\n")


def add_word_form(
    db: Database,
    current_group_id: Optional[int] = None,
    on_unexpected: Optional[Callable[[List[Dict[str, Any]]], None]] = None
) -> Optional[int]:
    """
    Streamlined interactive form to add new vocabulary words.
    Requests Word and Answer/Meaning (Enter to auto-lookup Chinese).
    Background lookups populate Chinese definition and phonetics asynchronously
    so the input flow is never interrupted.
    Checks word existence in the background and presents unexpected words at
    the end of the session for typo review and correction.
    """
    groups = db.get_groups()
    if not groups:
        console.print("[red]No groups found. Please create a group first![/red]")
        pause_prompt()
        return None

    # Group selection
    selected_gid = current_group_id
    if selected_gid is None:
        console.print("\n[bold cyan]─── Add New Vocabulary Word ───[/bold cyan]\n")
        console.print("[bold yellow]Select target deck:[/bold yellow]")
        res = select_group_prompt(groups, include_all=False)
        if res == -1 or res is None:
            return None
        selected_gid = res

    target_group = db.get_group_by_id(selected_gid)
    group_name = target_group.name if target_group else "Deck"
    group_color = target_group.color if target_group else "cyan"

    console.print(f"\n[bold cyan]─── Auto-Add Words to [{group_color}]{group_name}[/{group_color}] ───[/bold cyan]")
    console.print("[dim]Type a word and press Enter to auto-add (Chinese translation & phonetics fetch in background).[/dim]")
    console.print("[dim]Optional: type 'word: definition' or 'word = definition' for custom meaning.[/dim]")
    console.print("[bold yellow]Press Ctrl+C (or enter ':q') to quit.[/bold yellow]\n")

    added_count = 0
    last_word_id = None
    pending_validations: List[Tuple[int, str, Any]] = []
    unexpected_words: List[Dict[str, Any]] = []

    while True:
        try:
            line = prompt("Word > ").strip()
        except KeyboardInterrupt:
            console.print("\n[bold cyan]✓ Exiting word entry...[/bold cyan]")
            break
        except EOFError:
            break

        if not line:
            continue

        if line.lower() in (":q", "quit", "exit", ":quit", ":exit"):
            break

        # Parse word and optional custom definition
        if ":" in line:
            word_text, definition = line.split(":", 1)
            word_text = word_text.strip()
            definition = definition.strip()
        elif "=" in line:
            word_text, definition = line.split("=", 1)
            word_text = word_text.strip()
            definition = definition.strip()
        elif " - " in line:
            word_text, definition = line.split(" - ", 1)
            word_text = word_text.strip()
            definition = definition.strip()
        else:
            word_text = line.strip()
            definition = ""

        if not word_text:
            continue

        # Check for duplicate in the deck
        existing = db.get_words(group_id=selected_gid, search=word_text, limit=1)
        if existing and existing[0].word.lower() == word_text.lower():
            console.print(f"  [yellow]⚠ Note: '{word_text}' is already in this deck (skipped).[/yellow]")
            continue

        # Check cache for immediate definition & phonetic display
        from vocab.dictionary import _CHINESE_CACHE, _LOOKUP_CACHE
        cached_zh = _CHINESE_CACHE.get(word_text.lower())
        cached_entry = _LOOKUP_CACHE.get(word_text.lower())

        needs_chinese = False
        if not definition:
            if cached_zh:
                definition = cached_zh
            else:
                needs_chinese = True
                definition = "[Fetching Chinese meaning...]"

        phonetic = cached_entry.phonetic if cached_entry else ""
        pos = cached_entry.pos if cached_entry else ""

        # Instant DB save (<1ms, non-blocking)
        last_word_id = db.add_word(
            group_id=selected_gid,
            word=word_text,
            definition=definition,
            phonetic=phonetic,
            pos=pos,
            example="",
            mnemonic="",
            tags=""
        )

        # Dispatch background enrichment
        BackgroundEnricher.enrich(
            db=db,
            word_id=last_word_id,
            word_text=word_text,
            needs_chinese=needs_chinese
        )

        # Dispatch background existence lookup for typo detection
        fut = BackgroundEnricher._get_executor().submit(
            DictionaryService.check_word_exists, word_text, 3.5, db
        )
        pending_validations.append((last_word_id, word_text, fut))

        added_count += 1
        phonetic_str = f" [italic green]{phonetic}[/italic green]" if phonetic else ""
        pos_str = f" [italic white]({pos})[/italic white]" if pos else ""
        if definition and not definition.startswith("[Fetching"):
            console.print(f"  [bold green]✓ '{word_text}'[/bold green]{phonetic_str}{pos_str}: [bold white]{definition}[/bold white]")
        else:
            console.print(f"  [bold green]✓ '{word_text}' added![/bold green] [dim](auto-enriching Chinese & phonics in background)[/dim]")

    # Collect results from background validation checks
    for wid, wtext, fut in pending_validations:
        try:
            is_valid, suggestion = fut.result(timeout=2.5)
            if not is_valid:
                unexpected_words.append({
                    "id": wid,
                    "word": wtext,
                    "suggestion": suggestion,
                    "group_id": selected_gid
                })
        except Exception:
            pass

    # Store last session unexpected words on the function object for programmatic inspection
    add_word_form.last_unexpected_words = unexpected_words

    # Pass unexpected words to caller callback if provided
    if on_unexpected:
        try:
            on_unexpected(unexpected_words)
        except Exception:
            pass

    if added_count > 0:
        console.print(f"\n[bold green]✓ Done! Added {added_count} word(s) to '{group_name}'.[/bold green]")
        console.print("[dim]Lookups continue in the background so cards are ready immediately.[/dim]\n")
        time.sleep(0.5)
    else:
        console.print("\n[dim]No new words added.[/dim]\n")

    # Present unexpected words at the end of the session for typo review
    if unexpected_words:
        review_unexpected_words(db, unexpected_words)

    return last_word_id


add_word_form.last_unexpected_words = []


def edit_word_form(db: Database, word: Word) -> bool:
    """Form to edit an existing word."""
    console.print(f"\n[bold cyan]─── Edit Word: {word.word} ───[/bold cyan]\n")
    console.print("[dim]Press Enter to keep current value. Type ':lookup' for phonics, ':zh' for Chinese.[/dim]\n")

    new_word = prompt(f"Word [{word.word}]: ").strip() or word.word
    new_phonetic = prompt(f"Phonetic [{word.phonetic or 'none'}] (Enter to keep, ':lookup' for API): ").strip()
    if new_phonetic.lower() in (":lookup", ":api", "lookup"):
        entry = DictionaryService.lookup(new_word)
        new_phonetic = entry.phonetic or word.phonetic
        if entry.phonetic:
            console.print(f"  [bold green]✓ Fetched phonics:[/bold green] [italic green]{new_phonetic}[/italic green]")
    elif not new_phonetic:
        new_phonetic = word.phonetic

    new_pos = prompt(f"Part of Speech [{word.pos}]: ").strip() or word.pos

    new_definition = prompt(f"Answer / Definition [{word.definition}] (':zh' for auto Chinese): ").strip()
    if new_definition.lower() in (":zh", ":lookup", ":auto", "zh", "lookup"):
        console.print(f"  [dim cyan]◎ Fetching Chinese definition for '{new_word}'...[/dim cyan]", end="")
        zh = DictionaryService.lookup_chinese(new_word)
        if zh:
            new_definition = zh
            console.print(f"\r  [bold green]✓ Chinese Meaning:[/bold green] {new_definition}")
        else:
            console.print(f"\r  [yellow]No Chinese definition found; keeping current value.[/yellow]")
            new_definition = word.definition
    elif not new_definition:
        new_definition = word.definition

    new_example = prompt(f"Example [{word.example}]: ").strip() or word.example
    new_mnemonic = prompt(f"Mnemonic [{word.mnemonic}]: ").strip() or word.mnemonic
    new_tags = prompt(f"Tags [{word.tags}]: ").strip() or word.tags

    word.word = new_word
    word.phonetic = new_phonetic
    word.pos = new_pos
    word.definition = new_definition
    word.example = new_example
    word.mnemonic = new_mnemonic
    word.tags = new_tags

    success = db.update_word(word)
    if success:
        console.print(f"\n[bold green]✓ Word '{word.word}' updated successfully![/bold green]")
    else:
        console.print(f"\n[red]Failed to update word.[/red]")
    pause_prompt()
    return success


def manage_groups_menu(db: Database) -> None:
    """Menu to list, create, rename, and delete groups."""
    while True:
        groups = db.get_groups()
        console.print("\n[bold cyan]─── Manage Vocabulary Decks ───[/bold cyan]\n")

        table = Table(box=ROUNDED, border_style="bright_blue", expand=True, title="[bold bright_white]─── Vocabulary Decks ───[/bold bright_white]")
        table.add_column("#", width=4, justify="center", style="bold yellow")
        table.add_column("Deck Name", style="bold white", width=26)
        table.add_column("Description", style="dim")
        table.add_column("Total Cards", justify="right", style="cyan", width=14)
        table.add_column("Due Cards", justify="right", width=14)

        for idx, g in enumerate(groups, 1):
            due_cell = f"[bold bright_red]● {g.due_count}[/bold bright_red]" if g.due_count > 0 else "[green]✓ 0[/green]"
            table.add_row(
                str(idx),
                f"[{g.color} bold]{g.name}[/{g.color} bold]",
                g.description or "—",
                f"{g.word_count} cards",
                due_cell
            )

        console.print(table)
        console.print("\n[bold yellow]Actions:[/bold yellow]")
        console.print("  [bold yellow]\\[a][/bold yellow] [white]Add new deck[/white]      [bold yellow]\\[r][/bold yellow] [white]Rename / Edit deck[/white]      [bold yellow]\\[d][/bold yellow] [white]Delete deck[/white]      [bold yellow]\\[b][/bold yellow] [white]Back to main menu[/white]\n")

        cmd = input("Action > ").strip().lower()

        if cmd in ("b", "back", "q", "exit", ""):
            break

        elif cmd == "a":
            name = prompt("New Group Name: ").strip()
            if not name:
                continue
            desc = prompt("Description (optional): ").strip()
            color = prompt("Color [cyan/green/magenta/yellow/blue]: ").strip().lower() or "cyan"
            try:
                db.create_group(name=name, description=desc, color=color)
                console.print(f"[bold green]✓ Group '{name}' created![/bold green]")
            except Exception as e:
                console.print(f"[red]Error creating group: {e}[/red]")
            pause_prompt()

        elif cmd == "r":
            try:
                num = int(prompt("Select group # to edit: ").strip())
                if 1 <= num <= len(groups):
                    target = groups[num - 1]
                    new_name = prompt(f"Name [{target.name}]: ").strip() or target.name
                    new_desc = prompt(f"Description [{target.description}]: ").strip() or target.description
                    new_color = prompt(f"Color [{target.color}]: ").strip() or target.color
                    db.update_group(target.id, new_name, new_desc, new_color)
                    console.print("[bold green]✓ Group updated![/bold green]")
                    pause_prompt()
            except Exception as e:
                console.print(f"[red]Invalid selection or error: {e}[/red]")
                pause_prompt()

        elif cmd == "d":
            try:
                num = int(prompt("Select group # to delete: ").strip())
                if 1 <= num <= len(groups):
                    target = groups[num - 1]
                    confirm = prompt(f"Are you sure you want to delete '{target.name}' and its {target.word_count} words? [y/N]: ").strip().lower()
                    if confirm == "y":
                        db.delete_group(target.id)
                        console.print(f"[bold green]✓ Group '{target.name}' deleted.[/bold green]")
                        pause_prompt()
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")
                pause_prompt()


SORT_DESCRIPTIONS: Dict[Tuple[str, str], str] = {
    ("id", "desc"): "Date Added (Newest first)",
    ("id", "asc"): "Date Added (Oldest first)",
    ("word", "asc"): "Word (A-Z)",
    ("word", "desc"): "Word (Z-A)",
    ("alphabetical", "asc"): "Word (A-Z)",
    ("alphabetical", "desc"): "Word (Z-A)",
    ("due", "asc"): "Due Date (Soonest / overdue first)",
    ("due", "desc"): "Due Date (Furthest first)",
    ("due_date", "asc"): "Due Date (Soonest / overdue first)",
    ("due_date", "desc"): "Due Date (Furthest first)",
    ("ease", "asc"): "Ease Factor (Hardest first)",
    ("ease", "desc"): "Ease Factor (Easiest first)",
    ("ease_factor", "asc"): "Ease Factor (Hardest first)",
    ("ease_factor", "desc"): "Ease Factor (Easiest first)",
    ("interval", "asc"): "Interval (Shortest first)",
    ("interval", "desc"): "Interval (Longest first)",
    ("interval_days", "asc"): "Interval (Shortest first)",
    ("interval_days", "desc"): "Interval (Longest first)",
    ("reps", "desc"): "Review Reps (Most first)",
    ("reps", "asc"): "Review Reps (Least first)",
    ("lapses", "desc"): "Lapses (Most first)",
    ("lapses", "asc"): "Lapses (Least first)",
    ("state", "asc"): "State (A-Z)",
    ("pos", "asc"): "Part of Speech (A-Z)",
    ("deck", "asc"): "Deck Name (A-Z)",
}


def get_sort_label(sort_by: str, sort_order: str) -> str:
    """Returns a friendly label for the active sort field and order."""
    key = (sort_by.lower().strip(), sort_order.lower().strip())
    if key in SORT_DESCRIPTIONS:
        return SORT_DESCRIPTIONS[key]
    return f"{sort_by.capitalize()} ({sort_order.upper()})"


def render_words_table(
    words: List[Word],
    total_count: int,
    offset: int,
    limit: int,
    group_name: Optional[str] = None,
    search: Optional[str] = None,
    state: Optional[str] = None,
    pos: Optional[str] = None,
    tag: Optional[str] = None,
    due_only: bool = False,
    sort_by: str = "id",
    sort_order: str = "desc",
    console_width: Optional[int] = None,
) -> Table:
    """Builds a formatted Rich Table representing the current slice of words."""
    page = (offset // limit) + 1 if limit > 0 else 1
    total_pages = max(1, (total_count + limit - 1) // limit) if limit > 0 else 1
    start_item = offset + 1 if total_count > 0 and len(words) > 0 else 0
    end_item = min(offset + len(words), total_count)

    subtitle_str = f"Showing words {start_item}-{end_item} of {total_count} (Page {page} of {total_pages})"
    c_width = console_width or console.width
    show_extended = c_width >= 100

    table = Table(
        box=ROUNDED,
        border_style="bright_blue",
        expand=True,
        pad_edge=False,
        padding=(0, 1),
        title="[bold bright_white]─── Words Library & Manager ───[/bold bright_white]",
        caption=f"[dim]{subtitle_str}[/dim]"
    )
    table.add_column("#", justify="center", style="bold yellow", width=3)
    table.add_column("Word", style="bold bright_cyan", max_width=16, no_wrap=True)
    table.add_column("POS", style="italic yellow", width=4, no_wrap=True)
    table.add_column("Definition", style="white")
    table.add_column("Deck", style="bold blue", max_width=14, no_wrap=True)
    table.add_column("State", width=12, no_wrap=True)
    table.add_column("Due In", justify="right", style="yellow", width=8, no_wrap=True)
    if show_extended:
        table.add_column("Ease / Int", justify="right", style="dim cyan", width=10, no_wrap=True)

    for idx, w in enumerate(words, 1):
        if w.state == "mastered":
            state_cell = "[bold bright_green]🏆 mastered[/bold bright_green]"
        elif w.state == "new":
            state_cell = "[bold green]● new[/bold green]"
        elif "relearn" in w.state:
            state_cell = "[bold red]! relearn[/bold red]"
        elif "learn" in w.state:
            state_cell = "[bold magenta]▲ learn[/bold magenta]"
        else:
            state_cell = "[bold cyan]✓ review[/bold cyan]"

        def_text = (w.definition[:50] + "...") if len(w.definition) > 53 else w.definition
        deck_raw = w.group_name or "Default"
        deck_disp = (deck_raw[:12] + "..") if len(deck_raw) > 14 else deck_raw
        ease_int = f"{w.ease_factor:.2f} / {w.interval_days:.1f}d"

        row_cells = [
            str(idx),
            w.word,
            w.pos or "",
            def_text,
            deck_disp,
            state_cell,
            w.format_due_time(),
        ]
        if show_extended:
            row_cells.append(ease_int)

        table.add_row(*row_cells)

    return table


def prompt_sort_options(current_sort: str = "id", current_order: str = "desc") -> Optional[Tuple[str, str]]:
    """Interactive selector for sorting field and direction."""
    table = Table(box=ROUNDED, border_style="bright_blue", expand=True, title="[bold bright_white]─── Choose Sort Order ───[/bold bright_white]")
    table.add_column("Key", width=6, justify="center", style="bold yellow")
    table.add_column("Sort Order", style="bold white", width=34)
    table.add_column("Description", style="dim")

    sort_choices = [
        ("1", "word", "asc", "Word (A-Z)", "Alphabetical ascending"),
        ("2", "word", "desc", "Word (Z-A)", "Alphabetical descending"),
        ("3", "due", "asc", "Due Date (Soonest first)", "Overdue and upcoming cards first"),
        ("4", "due", "desc", "Due Date (Furthest first)", "Cards due furthest in future first"),
        ("5", "ease", "asc", "Ease Factor (Hardest first)", "Lowest ease / most difficult cards"),
        ("6", "ease", "desc", "Ease Factor (Easiest first)", "Highest ease / easiest cards"),
        ("7", "interval", "asc", "Interval (Shortest first)", "Shortest spaced repetition interval"),
        ("8", "interval", "desc", "Interval (Longest first)", "Longest interval / mature cards"),
        ("9", "id", "desc", "Date Added (Newest first)", "Most recently added words"),
        ("10", "id", "asc", "Date Added (Oldest first)", "Earliest added words"),
        ("11", "reps", "desc", "Review Reps (Most first)", "Most practiced cards"),
        ("12", "lapses", "desc", "Review Lapses (Most first)", "Cards with highest memory lapses"),
        ("13", "pos", "asc", "Part of Speech (A-Z)", "Grouped alphabetically by part of speech"),
    ]

    for key, s_by, s_ord, title, desc in sort_choices:
        active_mark = " [bold green]✓ active[/bold green]" if s_by == current_sort and s_ord == current_order else ""
        table.add_row(f"[{key}]", f"{title}{active_mark}", desc)

    console.print()
    console.print(table)
    console.print("  [bold yellow]\\[c][/bold yellow] [dim]Cancel[/dim]\n")
    try:
        val = input("Select sort option [1-13, c] > ").strip().lower()
        if val in ("c", "q", "cancel", ""):
            return None
        for key, s_by, s_ord, _, _ in sort_choices:
            if val == key:
                return s_by, s_ord
    except (KeyboardInterrupt, EOFError):
        return None
    return None


def prompt_state_filter(current_state: Optional[str] = None) -> Any:
    """Interactive selector for card state filter."""
    table = Table(box=ROUNDED, border_style="bright_blue", expand=True, title="[bold bright_white]─── Filter by Card State ───[/bold bright_white]")
    table.add_column("Key", width=6, justify="center", style="bold yellow")
    table.add_column("State", style="bold white", width=26)
    table.add_column("Description", style="dim")

    state_choices = [
        ("0", None, "All States (Clear filter)", "Show all words regardless of memory state"),
        ("1", "new", "● New", "Unreviewed cards ready for initial learning"),
        ("2", "learning", "▲ Learning", "Cards in active intra-day acquisition"),
        ("3", "review", "✓ Review", "Graduated cards in regular spaced repetition"),
        ("4", "relearning", "! Relearning", "Cards with recent lapses undergoing recovery"),
        ("5", "mastered", "🏆 Mastered", "Retired cards that have achieved permanent mastery"),
    ]

    for key, st, label, desc in state_choices:
        active_mark = " [bold green]✓ active[/bold green]" if st == current_state else ""
        table.add_row(f"[{key}]", f"{label}{active_mark}", desc)

    console.print()
    console.print(table)
    console.print("  [bold yellow]\\[c][/bold yellow] [dim]Cancel[/dim]\n")
    try:
        val = input("Select state filter [0-5, c] > ").strip().lower()
        if val in ("c", "q", "cancel", ""):
            return "NO_CHANGE"
        for key, st, _, _ in state_choices:
            if val == key:
                return st
    except (KeyboardInterrupt, EOFError):
        return "NO_CHANGE"
    return "NO_CHANGE"


def show_words_list(
    db: Database,
    group_id: Optional[int] = None,
    search: Optional[str] = None,
    state: Optional[str] = None,
    pos: Optional[str] = None,
    tag: Optional[str] = None,
    due_only: bool = False,
    sort_by: str = "id",
    sort_order: str = "desc",
    limit: int = 15,
    offset: int = 0,
    interactive: bool = False,
    console_out: Optional[Any] = None,
) -> List[Word]:
    """
    Shows words in the library with flexible filtering and sorting.
    Supports both non-interactive display (CLI / API) and interactive browsing.

    Args:
        db: Database instance.
        group_id: Filter by group/deck ID.
        search: Filter by search keyword (in word, definition, tags, example).
        state: Filter by card state ('new', 'learning', 'review', 'relearning').
        pos: Filter by part of speech.
        tag: Filter by tag.
        due_only: Filter to only currently due cards.
        sort_by: Sort field ('id', 'word', 'due', 'ease', 'interval', 'reps', 'lapses', 'created', 'state', 'pos').
        sort_order: Sort direction ('asc', 'desc').
        limit: Max items per page/output.
        offset: Offset for pagination.
        interactive: When True, enters an interactive command loop.
        console_out: Optional rich Console instance for output (defaults to global console).

    Returns:
        List of Word objects retrieved.
    """
    out = console_out or console

    # Non-interactive rendering
    if not interactive:
        total_count = db.count_words(
            group_id=group_id,
            search=search,
            state=state,
            pos=pos,
            tag=tag,
            due_only=due_only
        )
        words = db.get_words(
            group_id=group_id,
            search=search,
            state=state,
            pos=pos,
            tag=tag,
            due_only=due_only,
            sort_by=sort_by,
            sort_order=sort_order,
            limit=limit,
            offset=offset
        )
        grp = db.get_group_by_id(group_id) if group_id else None
        grp_name = grp.name if grp else None

        # Print active filters banner
        filter_badges = []
        if grp_name:
            filter_badges.append(f"Deck: '[bold cyan]{grp_name}[/bold cyan]'")
        if search:
            filter_badges.append(f"Search: '[bold yellow]{search}[/bold yellow]'")
        if state:
            filter_badges.append(f"State: '[bold magenta]{state}[/bold magenta]'")
        if pos:
            filter_badges.append(f"POS: '[italic yellow]{pos}[/italic yellow]'")
        if tag:
            filter_badges.append(f"Tag: '[bold blue]{tag}[/bold blue]'")
        if due_only:
            filter_badges.append("[bold red]Due cards only[/bold red]")

        filter_str = "  •  ".join(filter_badges) if filter_badges else "[dim](none)[/dim]"
        sort_str = f"[bold green]{get_sort_label(sort_by, sort_order)}[/bold green]"

        out.print(f"\n[dim]Active Filters: {filter_str}  |  Sort: {sort_str}[/dim]")

        if not words:
            out.print("\n[yellow]No words found matching the specified filters.[/yellow]\n")
            return []

        table = render_words_table(
            words=words,
            total_count=total_count,
            offset=offset,
            limit=limit,
            group_name=grp_name,
            search=search,
            state=state,
            pos=pos,
            tag=tag,
            due_only=due_only,
            sort_by=sort_by,
            sort_order=sort_order,
            console_width=out.width,
        )
        out.print(table)
        out.print()
        return words

    # Interactive browsing loop
    cur_group_id = group_id
    cur_search = search
    cur_state = state
    cur_pos = pos
    cur_tag = tag
    cur_due_only = due_only
    cur_sort_by = sort_by
    cur_sort_order = sort_order
    cur_offset = offset
    cur_limit = limit

    while True:
        total_count = db.count_words(
            group_id=cur_group_id,
            search=cur_search,
            state=cur_state,
            pos=cur_pos,
            tag=cur_tag,
            due_only=cur_due_only
        )
        words = db.get_words(
            group_id=cur_group_id,
            search=cur_search,
            state=cur_state,
            pos=cur_pos,
            tag=cur_tag,
            due_only=cur_due_only,
            sort_by=cur_sort_by,
            sort_order=cur_sort_order,
            limit=cur_limit,
            offset=cur_offset
        )

        grp = db.get_group_by_id(cur_group_id) if cur_group_id else None
        grp_name = grp.name if grp else None

        out.print(f"\n[bold cyan]─── Manage, Browse & Search Words ───[/bold cyan]")

        filter_badges = []
        if grp_name:
            filter_badges.append(f"Deck: '[bold cyan]{grp_name}[/bold cyan]'")
        if cur_search:
            filter_badges.append(f"Search: '[bold yellow]{cur_search}[/bold yellow]'")
        if cur_state:
            filter_badges.append(f"State: '[bold magenta]{cur_state}[/bold magenta]'")
        if cur_pos:
            filter_badges.append(f"POS: '[italic yellow]{cur_pos}[/italic yellow]'")
        if cur_tag:
            filter_badges.append(f"Tag: '[bold blue]{cur_tag}[/bold blue]'")
        if cur_due_only:
            filter_badges.append("[bold red]Due cards only[/bold red]")

        filter_str = "  •  ".join(filter_badges) if filter_badges else "[dim](none)[/dim]"
        sort_str = f"[bold green]{get_sort_label(cur_sort_by, cur_sort_order)}[/bold green]"

        out.print(f"[dim]Filters: {filter_str}  |  Sort: {sort_str}[/dim]")

        table = render_words_table(
            words=words,
            total_count=total_count,
            offset=cur_offset,
            limit=cur_limit,
            group_name=grp_name,
            search=cur_search,
            state=cur_state,
            pos=cur_pos,
            tag=cur_tag,
            due_only=cur_due_only,
            sort_by=cur_sort_by,
            sort_order=cur_sort_order,
            console_width=out.width,
        )
        out.print(table)

        if not words:
            out.print("\n[yellow]No words match current filters.[/yellow]")

        out.print("\n[bold yellow]Actions:[/bold yellow]")
        out.print("  [bold yellow]\\[s][/bold yellow] [white]Search[/white]          [bold yellow]\\[g][/bold yellow] [white]Filter deck[/white]      [bold yellow]\\[f][/bold yellow] [white]Filter state[/white]     [bold yellow]\\[u][/bold yellow] [white]Toggle due-only[/white]")
        out.print("  [bold yellow]\\[o][/bold yellow] [white]Sort order[/white]      [bold yellow]\\[c][/bold yellow] [white]Clear filters[/white]    [bold yellow]\\[n][/bold yellow] [white]Next page[/white]        [bold yellow]\\[p][/bold yellow] [white]Prev page[/white]")
        out.print("  [bold yellow]\\[e #][/bold yellow] [white]Edit word[/white]      [bold yellow]\\[d #][/bold yellow] [white]Delete word[/white]      [bold yellow]\\[#][/bold yellow] [white]Inspect word[/white]     [bold yellow]\\[b][/bold yellow] [white]Back to menu[/white]\n")

        try:
            cmd = input("Command > ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            break

        cmd_parts = cmd.split()
        op = cmd_parts[0] if cmd_parts else ""
        arg = cmd_parts[1] if len(cmd_parts) > 1 else ""

        if op in ("b", "back", "q", "exit"):
            break
        elif op in ("s", "search"):
            try:
                new_q = prompt("Search query (leave empty to clear): ").strip()
                cur_search = new_q if new_q else None
                cur_offset = 0
            except (KeyboardInterrupt, EOFError):
                pass
        elif op in ("g", "group", "deck"):
            groups = db.get_groups()
            res = select_group_prompt(groups, include_all=True)
            if res != -1:
                cur_group_id = res
                cur_offset = 0
        elif op in ("f", "filter", "state"):
            if arg and arg in ("new", "learning", "review", "relearning", "mastered"):
                cur_state = arg
                cur_offset = 0
            else:
                chosen = prompt_state_filter(cur_state)
                if chosen != "NO_CHANGE":
                    cur_state = chosen
                    cur_offset = 0
        elif op in ("u", "due"):
            cur_due_only = not cur_due_only
            cur_offset = 0
            state_desc = "[bold green]ON (Due cards only)[/bold green]" if cur_due_only else "[bold yellow]OFF (All cards)[/bold yellow]"
            out.print(f"\n[bold]Due filter is now: {state_desc}[/bold]")
            time.sleep(0.4)
        elif op in ("o", "sort", "order"):
            if arg:
                cur_sort_by = arg
                if len(cmd_parts) > 2 and cmd_parts[2] in ("asc", "desc"):
                    cur_sort_order = cmd_parts[2]
                elif cur_sort_by in ("word", "alphabetical", "pos", "deck", "state"):
                    cur_sort_order = "asc"
                else:
                    cur_sort_order = "desc" if cur_sort_by in ("id", "created", "reps", "lapses") else "asc"
                cur_offset = 0
            else:
                chosen = prompt_sort_options(cur_sort_by, cur_sort_order)
                if chosen:
                    cur_sort_by, cur_sort_order = chosen
                    cur_offset = 0
        elif op in ("c", "clear", "reset"):
            cur_search = None
            cur_group_id = None
            cur_state = None
            cur_pos = None
            cur_tag = None
            cur_due_only = False
            cur_sort_by = "id"
            cur_sort_order = "desc"
            cur_offset = 0
            out.print("\n[bold green]✓ All filters and sorting reset to default.[/bold green]")
            time.sleep(0.4)
        elif op in ("n", "next"):
            if cur_offset + cur_limit < total_count:
                cur_offset += cur_limit
            else:
                out.print("[yellow]Already at the last page.[/yellow]")
                time.sleep(0.3)
        elif op in ("p", "prev", "previous"):
            if cur_offset > 0:
                cur_offset = max(0, cur_offset - cur_limit)
            else:
                out.print("[yellow]Already at the first page.[/yellow]")
                time.sleep(0.3)
        elif op in ("e", "edit", "m", "modify"):
            target_idx = None
            if arg and arg.isdigit():
                target_idx = int(arg)
            else:
                try:
                    num_str = prompt("Enter word # to edit: ").strip()
                    if num_str.isdigit():
                        target_idx = int(num_str)
                except (KeyboardInterrupt, EOFError):
                    pass
            if target_idx and 1 <= target_idx <= len(words):
                target_word = words[target_idx - 1]
                edit_word_form(db, target_word)
            elif target_idx is not None:
                out.print("[red]Invalid word number.[/red]")
                pause_prompt()
        elif op in ("d", "del", "delete"):
            target_idx = None
            if arg and arg.isdigit():
                target_idx = int(arg)
            else:
                try:
                    num_str = prompt("Enter word # to delete: ").strip()
                    if num_str.isdigit():
                        target_idx = int(num_str)
                except (KeyboardInterrupt, EOFError):
                    pass
            if target_idx and 1 <= target_idx <= len(words):
                target_word = words[target_idx - 1]
                confirm = prompt(f"Delete '{target_word.word}' permanently? [y/N]: ").strip().lower()
                if confirm == "y":
                    db.delete_word(target_word.id)
                    out.print(f"[bold green]✓ Word '{target_word.word}' deleted.[/bold green]")
                    pause_prompt()
            elif target_idx is not None:
                out.print("[red]Invalid word number.[/red]")
                pause_prompt()
        elif op.isdigit():
            idx = int(op)
            if 1 <= idx <= len(words):
                target_word = words[idx - 1]
                _inspect_word_dialog(db, target_word)

    return words


def browse_words_view(db: Database, group_id: Optional[int] = None) -> None:
    """Browse, search, edit, and delete words with filtering and sorting."""
    show_words_list(db, group_id=group_id, interactive=True)


show_words = show_words_list
list_words_view = show_words_list


def _inspect_word_dialog(db: Database, word: Word) -> None:
    """Detailed inspection and edit/delete actions for a single word."""
    while True:
        info = Table.grid(padding=(0, 2))
        info.add_column("Field", style="bold cyan", width=16)
        info.add_column("Value", style="white")

        info.add_row("Word:", f"[bold bright_cyan]{word.word}[/bold bright_cyan]")
        if word.phonetic:
            info.add_row("Phonetic:", f"[italic bright_green]{word.phonetic}[/italic bright_green]")
        if word.pos:
            info.add_row("POS:", f"[italic yellow]{word.pos}[/italic yellow]")
        info.add_row("Deck:", f"[bold blue]{word.group_name or 'Default'}[/bold blue]")
        info.add_row("Meaning:", f"[bold bright_white]{word.definition}[/bold bright_white]")
        if word.example:
            info.add_row("Example:", f"[italic white]{word.example}[/italic white]")
        if word.mnemonic:
            info.add_row("Mnemonic:", f"[bold yellow]★ {word.mnemonic}[/bold yellow]")
        if word.tags:
            info.add_row("Tags:", f"[dim cyan]{word.tags}[/dim cyan]")

        if word.state == "mastered":
            st_val = "[bold bright_green]🏆 MASTERED (Retired)[/bold bright_green]"
        elif word.state == "new":
            st_val = "[bold green]● NEW[/bold green]"
        elif "learn" in word.state:
            st_val = "[bold magenta]▲ LEARNING[/bold magenta]"
        else:
            st_val = "[bold cyan]✓ REVIEW[/bold cyan]"

        info.add_row("Card State:", st_val)
        info.add_row("Reps / Lapses:", f"[white]{word.reps}[/white] / [yellow]{word.lapses}[/yellow]")
        info.add_row("Ease Factor:", f"[magenta]{word.ease_factor:.2f}[/magenta]")
        info.add_row("Interval:", f"[green]{word.interval_days:.2f} days[/green]")
        info.add_row("Due Status:", f"[yellow]{word.format_due_time()}[/yellow]")

        console.print()
        console.print(Panel(info, box=ROUNDED, border_style="bright_cyan", title=f"[bold bright_white]─── Word Card: {word.word} ───[/bold bright_white]"))

        retire_action = "[bold yellow]\\[r][/bold yellow] [white]Reactivate for review[/white]" if word.state == "mastered" else "[bold yellow]\\[m][/bold yellow] [white]Mark as Mastered[/white]"
        console.print("\n[bold yellow]Actions:[/bold yellow]")
        console.print(f"  [bold yellow]\\[e][/bold yellow] [white]Edit word[/white]       [bold yellow]\\[d][/bold yellow] [white]Delete word[/white]     {retire_action}     [bold yellow]\\[l][/bold yellow] [white]Auto-enrich (Phonics/Chinese)[/white]     [bold yellow]\\[b][/bold yellow] [white]Back[/white]\n")

        action = input("Action > ").strip().lower()
        if action == "e":
            edit_word_form(db, word)
            refreshed = db.get_word_by_id(word.id)
            if refreshed:
                word = refreshed
        elif action == "d":
            confirm = prompt(f"Delete '{word.word}' permanently? [y/N]: ").strip().lower()
            if confirm == "y":
                db.delete_word(word.id)
                console.print(f"[bold green]✓ Word deleted.[/bold green]")
                pause_prompt()
                break
        elif action == "m":
            db.set_word_mastery(word.id, True)
            refreshed = db.get_word_by_id(word.id)
            if refreshed:
                word = refreshed
            console.print(f"[bold bright_green]🏆 Word '{word.word}' marked as Mastered and retired from review sessions.[/bold bright_green]")
            time.sleep(0.8)
        elif action == "r":
            db.set_word_mastery(word.id, False)
            refreshed = db.get_word_by_id(word.id)
            if refreshed:
                word = refreshed
            console.print(f"[bold cyan]✓ Word '{word.word}' reactivated for active review.[/bold cyan]")
            time.sleep(0.8)
        elif action == "l":
            console.print(f"\n  [dim cyan]◎ Fetching phonetics & Chinese definition for '{word.word}'...[/dim cyan]", end="")
            zh = DictionaryService.lookup_chinese(word.word)
            entry = DictionaryService.lookup(word.word)
            changed = False
            if zh:
                word.definition = zh
                changed = True
            if entry.phonetic:
                word.phonetic = entry.phonetic
                changed = True
            if entry.pos and not word.pos:
                word.pos = entry.pos
                changed = True
            if entry.example and not word.example:
                word.example = entry.example
                changed = True
            if changed:
                db.update_word(word)
                console.print(f"\r  [bold green]✓ Enriched '{word.word}' with phonetics and Chinese definition![/bold green]")
            else:
                console.print(f"\r  [yellow]No online updates found for '{word.word}'.[/yellow]")
            pause_prompt()
        elif action in ("b", "back", "q", ""):
            break
