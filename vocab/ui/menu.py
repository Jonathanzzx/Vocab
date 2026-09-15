"""Home screen layouts selected using the terminal's available rows and columns."""
from io import StringIO
from rich.console import Console, Group as RenderGroup
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.rule import Rule
from vocab.ui.theme import console, clear_screen, metric_panel, metric_grid, PALETTE


SECTIONS = [
    ("STUDY", [
        ("1", "Flashcards", "Recall a meaning, reveal, then rate your answer"),
        ("2", "Typing practice", "Retrieve words from definitions and context"),
        ("3", "Recognition quiz", "Multiple choice practice; keeps recall schedules"),
        ("t", "Vocabulary check", "Practice scores by item level; informal assessment"),
    ]),
    ("LIBRARY", [
        ("4", "Choose deck", "Focus on one deck or study them together"),
        ("5", "Add vocabulary", "Enter words with automatic dictionary enrichment"),
        ("6", "Browse & edit", "Search words, revise definitions, inspect progress"),
        ("8", "Manage decks", "Create, rename and organize vocabulary groups"),
        ("9", "Import & export", "Move vocabulary using CSV or JSON"),
    ]),
    ("INSIGHTS", [("7", "Study statistics", "Review activity, response times and upcoming work")]),
]


def _line(value, style=""):
    return Text(str(value), style=style, no_wrap=True, overflow="ellipsis")


def _actions(width, descriptions=False, sections=True, columns=False):
    rows = [(key, label, detail) for _, items in SECTIONS for key, label, detail in items]
    if columns:
        table = Table.grid(expand=True, padding=(0, 2))
        table.add_column(ratio=1)
        table.add_column(ratio=1)
        half = (len(rows) + 1) // 2
        for left, right in zip(rows[:half], rows[half:]):
            table.add_row(_action_text(*left[:2]), _action_text(*right[:2]))
        return [table]
    parts = []
    for title, items in (SECTIONS if sections else [("", rows)]):
        if title:
            parts.append(_line(title, "muted"))
        table = Table.grid(expand=True, padding=(0, 1))
        table.add_column(width=2, no_wrap=True, style="accent")
        table.add_column(ratio=2)
        if descriptions:
            table.add_column(ratio=3)
        for key, label, detail in items:
            cells = [_line(key), _line(label)]
            if descriptions:
                cells.append(_line(detail, "muted"))
            table.add_row(*cells)
        parts.append(table)
    return parts


def _action_text(key, label):
    text = _line("")
    text.append(key + "  ", style="accent")
    text.append(label)
    return text


def build_main_dashboard(active_group, stats, groups, target):
    """Choose the richest complete layout that leaves two rows for input.

    Measure actual Rich output, including wrapped metric panels. No essential
    action is removed to make space; decorative panels and descriptions go first.
    """
    width, height = target.size
    focus = active_group.name if active_group else "All decks"
    due, total = stats.get("due_count", 0), stats.get("total_words", 0)
    attempts = stats.get("total_recent_reviews", 0)
    recall = f"{stats.get('retention_rate', 0):.0f}%" if attempts else "—"
    streak = stats.get("streak_days", 0)
    heading = _line("V O C A B  /  Study overview", "heading")
    deck = _line(focus, "heading")
    footer = _action_text("q", "Exit")
    ready = "Start a review to work through your due cards." if due else "You're up to date. Add vocabulary or choose a practice mode."
    panels = metric_grid([
        metric_panel(due, "Ready to study", "Due + new words"),
        metric_panel(total, "Library", "Selected decks"),
        metric_panel(recall, "Recall · 7 days", f"{attempts} recall attempts"),
        metric_panel(f"{streak} days", "Study streak", "Active days"),
    ], width)
    summary = _line(f"{due} ready · {total} words · Recall {recall} · Streak {streak}d", "accent")
    samples = _line(f"{attempts} recall attempts · 7 days", "muted")
    overview = [heading, deck, summary, samples]
    candidates = []
    if width >= 60:
        candidates.append(RenderGroup(
            heading, _line("Spaced review · Active recall · Personal library", "muted"),
            Rule(style="border"), deck,
            _line(f"{len(groups)} {'deck' if len(groups) == 1 else 'decks'} in your library", "muted"),
            Text(""), panels, Text(""),
            Panel(Text(ready), title="Today's practice", title_align="left", border_style="accent"),
            Text(""), *_actions(width, descriptions=width >= 90), Text(""), footer,
        ))
    candidates.append(RenderGroup(
        *overview, Text(""), *_actions(width, descriptions=width >= 90), Text(""), footer,
    ))
    if width >= 72:
        candidates.append(RenderGroup(*overview, Text(""), *_actions(width, columns=True), footer))
    candidates.append(RenderGroup(*overview, *_actions(width, sections=False), footer))
    options = target.options.update(width=width, height=None)
    budget = max(1, height - 2)
    for candidate in candidates:
        if len(target.render_lines(candidate, options, pad=False)) <= budget:
            return candidate
    # Tiny terminals: keep all command keys accessible in a compact legend.
    return RenderGroup(heading, *_actions(width, sections=False), footer)


def render_main_dashboard(active_group, stats, groups, auto_add_due=True):
    clear_screen()
    console.print(build_main_dashboard(active_group, stats, groups, console))


def _create_dashboard_application(active_group, stats, groups, *, input=None, output=None):
    """Reflow on resize while preserving the command being typed."""
    from prompt_toolkit.application import Application
    from prompt_toolkit.buffer import Buffer
    from prompt_toolkit.formatted_text import ANSI, to_formatted_text
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import Layout, HSplit, Window
    from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
    from prompt_toolkit.layout.processors import BeforeInput

    def accept(buffer):
        application.exit(result=buffer.text.strip().lower())
        return True

    command = Buffer(accept_handler=accept, multiline=False)
    command_control = BufferControl(buffer=command, input_processors=[BeforeInput("Choose > ")])

    def content():
        size = application.output.get_size()
        stream = StringIO()
        target = Console(file=stream, width=size.columns, height=size.rows,
                         theme=PALETTE, force_terminal=True, color_system="truecolor")
        target.print(build_main_dashboard(active_group, stats, groups, target))
        return to_formatted_text(ANSI(stream.getvalue().rstrip("\n")))

    keys = KeyBindings()
    @keys.add("c-c")
    @keys.add("c-d")
    def leave(event):
        event.app.exit(result="q")

    application = Application(
        layout=Layout(HSplit([
            Window(FormattedTextControl(content), wrap_lines=False),
            Window(command_control, height=1),
        ]), focused_element=command_control),
        key_bindings=keys, full_screen=True, mouse_support=False,
        input=input, output=output,
    )
    return application


def read_dashboard_command(active_group, stats, groups):
    if not console.is_terminal:
        render_main_dashboard(active_group, stats, groups)
        return input("Choose > ").strip().lower()
    return _create_dashboard_application(active_group, stats, groups).run()
