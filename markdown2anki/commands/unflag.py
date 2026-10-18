"""``m2a unflag``: remove ADDED/DELETED flags so cards are exported again as new notes."""
from __future__ import annotations

from pathlib import Path

import typer

from .. import ui
from ..flags import clear_flags
from ..ui import console, escape
from ..vault import collect
from ._shared import COURSE_OPTION, DRY_RUN_OPTION, FILE_OPTION, YES_OPTION, load, rel, resolve_note_file, short_question


def run(
    ctx: typer.Context,
    course: str | None = COURSE_OPTION,
    file: Path | None = FILE_OPTION,
    legacy: bool = typer.Option(False, "--legacy", help="Only target legacy 'ADDED: ' flags without a card ID."),
    dry_run: bool = DRY_RUN_OPTION,
    yes: bool = YES_OPTION,
) -> int:
    cfg = load(ctx)
    target_file = resolve_note_file(file, cfg.vault) if file else None
    if target_file and not target_file.is_file():
        ui.error(f"file not found: {file}")
        return 2

    collected = collect(cfg, course, trace_fn=ui.trace)
    chosen = [c for c in collected.cards if c.added or c.deleted]
    if target_file:
        chosen = [c for c in chosen if c.file.resolve() == target_file]
    if legacy:
        chosen = [c for c in chosen if c.card_id is None]

    header_src = rel(target_file, cfg) if target_file else str(cfg.vault)
    ui.header("m2a unflag", header_src)
    if not chosen:
        console.print("  [dim]no flagged cards match[/]")
        return 0

    rows = [
        [
            "[red]deleted[/]" if c.deleted else "[dim]added[/]",
            f"[dim]{escape(c.card_id or 'legacy')}[/]",
            escape(f"{rel(c.file, cfg)}:{c.line}"),
            escape(short_question(c)),
        ]
        for c in chosen
    ]
    console.print(ui.table(["state", "id", "where", "question"], rows))
    console.print()

    if dry_run:
        console.print("  [dim]dry run - nothing written[/]")
        return 0

    added_count = sum(1 for c in chosen if c.added)
    if added_count:
        console.print(
            f"  [yellow]warning:[/] [bold]{added_count}[/] card(s) are currently marked [bold]ADDED[/].\n"
            "  Removing their flags causes the next `m2a sync` to export them as brand-new notes,\n"
            "  creating duplicates in Anki unless the existing Anki notes are deleted via `m2a orphans`."
        )
    if not yes and not ui.confirm(f"Remove the flag from {len(chosen)} card(s)?"):
        console.print("  [dim]nothing changed[/]")
        return 0

    try:
        cleared, problems = clear_flags(chosen)
    except OSError as exc:
        ui.error(f"failed to clear flags: {exc}")
        return 1
    console.print(f"  [green]✓[/] unflagged [bold]{cleared}[/] card(s)")
    if problems:
        for problem in problems:
            console.print(f"    {ui.level('warning')} {escape(problem)}")
        return 1
    return 0
