"""``m2a unflag``: remove ADDED flags so cards are exported again as new notes."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from .. import ui
from ..flags import clear_flags
from ..ui import console, escape
from ..vault import collect
from ._shared import COURSE_OPTION, YES_OPTION, load, rel, short_question


def run(
    ctx: typer.Context,
    course: Optional[str] = COURSE_OPTION,
    file: Optional[Path] = typer.Option(None, "--file", help="Only this note."),
    legacy: bool = typer.Option(False, "--legacy", help="Only old `ADDED: ` flags without an id."),
    yes: bool = YES_OPTION,
) -> int:
    cfg = load(ctx)
    collected = collect(cfg, course)
    chosen = collected.added
    if file:
        wanted = file.expanduser().resolve()
        chosen = [c for c in chosen if c.file.resolve() == wanted]
    if legacy:
        chosen = [c for c in chosen if c.card_id is None]

    ui.header("m2a unflag", str(cfg.vault))
    if not chosen:
        console.print("  [dim]no flagged cards match[/]")
        return 0
    rows = [[f"[dim]{c.card_id or 'legacy'}[/]", escape(f"{rel(c.file, cfg)}:{c.line}"), escape(short_question(c))]
            for c in chosen]
    console.print(ui.table(["id", "where", "question"], rows))
    console.print()
    console.print("  [yellow]note:[/] unflagged cards are exported again as [bold]new[/] notes; "
                  "delete the old ones in Anki yourself if they were imported.")
    if not yes and not ui.confirm(f"Remove the flag from {len(chosen)} card(s)?"):
        console.print("  [dim]nothing changed[/]")
        return 0
    cleared, problems = clear_flags(chosen)
    console.print(f"  [green]✓[/] unflagged [bold]{cleared}[/] card(s)")
    for problem in problems:
        console.print(f"    {ui.level('warning')} {escape(problem)}")
    return 0
