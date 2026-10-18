"""``m2a config``, ``m2a check`` and ``m2a status``: read-only inspection commands."""
from __future__ import annotations

import typer

from .. import ui
from ..build import build
from ..ui import console, escape
from ..vault import collect
from ._shared import COURSE_OPTION, INDENT, load, print_card_table, print_problems, summary_line


def config(ctx: typer.Context) -> int:
    cfg = load(ctx)
    ui.header("m2a config", str(cfg.source))
    console.print(f"  [dim]vault[/]      {escape(str(cfg.vault))}")
    console.print(f"  [dim]templates[/]  {escape(str(cfg.templates_dir))}")
    console.print()
    if cfg.source and cfg.source.is_file():
        for line in cfg.source.read_text(encoding="utf-8").splitlines():
            console.print(f"[dim]{escape(line)}[/]" if line.startswith("#") else escape(line))
    return 0


def status(
    ctx: typer.Context,
    course: str | None = COURSE_OPTION,
    verbose: bool = typer.Option(False, "-v", "--verbose", help="Also list every card and info-level diagnostics."),
) -> int:
    cfg = load(ctx)
    collected = collect(cfg, course, trace_fn=ui.trace)
    active_cards = [c for c in collected.cards if not c.deleted]
    deleted_cards = [c for c in collected.cards if c.deleted]

    result = build(
        active_cards,
        collected.diagnostics,
        cfg.cloze_notes,
        vault_root=cfg.vault,
        hash_media=cfg.hash_media,
        image_occlusion_mode=cfg.image_occlusion_mode,
    )

    counts: dict[str, list[int]] = {source.group: [0, 0, 0] for source in collected.sources}
    group_of = {source.path: source.group for source in collected.sources}
    for card in active_cards:
        row = counts[group_of[card.file]]
        row[0] += 1
        row[1 if card.added else 2] += 1

    ui.header("m2a status", str(cfg.vault))
    kv_items: list[tuple[str, int]] = [
        ("notes", len(collected.sources)),
        ("cards", len(active_cards)),
        ("pending", len(collected.pending)),
        ("added", len(collected.added)),
    ]
    if deleted_cards:
        kv_items.append(("deleted", len(deleted_cards)))
    console.print(INDENT + ui.kv(kv_items))
    console.print()

    rows = [
        [escape(group), str(total), str(added), f"[green]{pending}[/]" if pending else "[dim]0[/]"]
        for group, (total, added, pending) in sorted(counts.items())
    ]
    if rows:
        console.print(ui.table(["group", "cards", "added", "new"], rows, align_right=(1, 2, 3)))
    else:
        console.print("  [dim]no courses or notes found[/]")

    if verbose and collected.cards:
        console.print()
        print_card_table(
            collected.cards,
            lambda c: "[red]deleted[/]" if c.deleted else ("[dim]added[/]" if c.added else "[green]new[/]"),
        )

    console.print()
    errors = print_problems(collected.diagnostics, cfg, include_info=verbose, skipped_count=len(result.skipped))
    return 1 if errors else 0


def check(
    ctx: typer.Context,
    course: str | None = COURSE_OPTION,
    verbose: bool = typer.Option(False, "-v", "--verbose", help="Also list every card and info-level diagnostics."),
) -> int:
    return status(ctx=ctx, course=course, verbose=verbose)
