"""Render the actual terminal components at narrow and wide widths."""
from io import StringIO
import pytest
from rich.console import Console
from vocab.ui import theme, menu, card_views, stats_views
from vocab.models import Group, Word


@pytest.mark.parametrize("width", [60, 80, 120])
def test_dashboard_and_cards_render_without_clipping_actions(monkeypatch, width):
    output = StringIO()
    console = Console(file=output, width=width, theme=theme.PALETTE, color_system=None)
    for module in (theme, menu, card_views, stats_views):
        monkeypatch.setattr(module, "console", console)
    group = Group(1, "Research [notes] 中文")
    menu.render_main_dashboard(group, {"due_count": 0, "total_recent_reviews": 2, "retention_rate": 0}, [group])
    rendered = output.getvalue()
    assert "Research [notes] 中文" in rendered
    assert "0%" in rendered  # Zero success must not look like missing data.
    assert all(label in rendered for label in ("Flashcards", "Typing practice", "Recognition quiz", "Browse & edit"))
    word = Word(1, 1, "evidence", "Information that supports a claim.", state="review", group_name=group.name)
    card_views.render_flashcard_front(word, 1, 5)
    card_views.render_flashcard_back(word, 1, 5)
    stats_views.render_stats_dashboard({}, [], {})
    assert "Effortless recall" in output.getvalue()


def test_dashboard_empty_state(monkeypatch):
    output = StringIO()
    console = Console(file=output, width=80, theme=theme.PALETTE, color_system=None)
    monkeypatch.setattr(theme, "console", console)
    monkeypatch.setattr(menu, "console", console)
    menu.render_main_dashboard(None, {}, [])
    assert "0 recall attempts" in output.getvalue()
    assert "—" in output.getvalue()


@pytest.mark.parametrize("width,height", [(30, 16), (40, 20), (60, 24), (80, 24), (80, 16), (120, 30), (160, 50)])
def test_home_fits_terminal_and_keeps_every_action(width, height):
    from rich.cells import cell_len
    output = StringIO()
    terminal = Console(file=output, width=width, height=height, theme=theme.PALETTE, color_system=None)
    group = Group(1, "Research [notes] 中文 " * 8)
    dashboard = menu.build_main_dashboard(group, {"due_count": 1200, "total_words": 5000}, [group], terminal)
    terminal.print(dashboard)
    lines = output.getvalue().splitlines()
    assert len(lines) <= height - 2
    assert all(cell_len(line) <= width for line in lines)
    for key, label, _ in [row for _, rows in menu.SECTIONS for row in rows]:
        assert label in output.getvalue()
    assert "q  Exit" in output.getvalue()


def test_resize_changes_detail_level():
    def render(height):
        stream = StringIO()
        terminal = Console(file=stream, width=120, height=height, theme=theme.PALETTE)
        terminal.print(menu.build_main_dashboard(None, {}, [], terminal))
        return stream.getvalue()
    assert "Today's practice" in render(50)
    assert "Today's practice" not in render(20)
    assert "Flashcards" in render(20)


def test_live_home_reflows_and_preserves_typed_command():
    import asyncio
    from prompt_toolkit.input import create_pipe_input
    from prompt_toolkit.output import DummyOutput
    from prompt_toolkit.data_structures import Size

    class ResizableOutput(DummyOutput):
        size = Size(rows=50, columns=120)
        def get_size(self):
            return self.size

    async def exercise():
        with create_pipe_input() as pipe:
            output = ResizableOutput()
            app = menu._create_dashboard_application(None, {}, [], input=pipe, output=output)
            rendered = asyncio.Event()
            app.after_render += lambda _: rendered.set()
            task = asyncio.create_task(app.run_async())
            await asyncio.wait_for(rendered.wait(), 3)
            pipe.send_text("7")
            # Observe a render containing the buffered command before resizing.
            for _ in range(10):
                rendered.clear()
                app.invalidate()
                await asyncio.wait_for(rendered.wait(), 3)
                if app.current_buffer.text == "7":
                    break
            assert app.current_buffer.text == "7"
            output.size = Size(rows=20, columns=40)
            rendered.clear()
            app._on_resize()
            await asyncio.wait_for(rendered.wait(), 3)
            assert app.current_buffer.text == "7"
            pipe.send_text("\r")
            assert await asyncio.wait_for(task, 3) == "7"

    asyncio.run(exercise())
