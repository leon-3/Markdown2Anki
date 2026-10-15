"""``m2a sync``: export pending cards (and, with ``--update``, already exported ones) and flag them."""
from __future__ import annotations

from pathlib import Path

import typer

from .. import ui
from ..build import BuildResult, build
from ..config import Config, Target
from ..export.ankiconnect import AnkiConnectError, export_ankiconnect
from ..export.apkg import drop_unsupported_updates, export_apkg, export_occlusions
from ..flags import write_flags
from ..parser import Card, Diagnostic
from ..ui import console, escape
from ..vault import collect
from ._shared import COURSE_OPTION, INDENT, load, print_card_table, print_diagnostics, print_problems

Flags = list[tuple[Card, str]]


def run(
    ctx: typer.Context,
    course: str | None = COURSE_OPTION,
    target: Target | None = typer.Option(None, "--target", help="apkg: write a package file; anki: push via "
                                                                "AnkiConnect (default: 'target' in config)."),
    update: bool = typer.Option(False, "--update", help="Also re-export cards that were already added with an id "
                                                        "(updates them in Anki)."),
    dry_run: bool = typer.Option(False, "-n", "--dry-run", help="Show what would be exported, write nothing."),
    no_flag: bool = typer.Option(False, "--no-flag", help="Export but do not write ADDED flags into the notes."),
    yes: bool = typer.Option(False, "-y", "--yes", help="Do not ask before writing ADDED flags."),
    output: Path | None = typer.Option(None, "-o", "--output", help="apkg path (default: "
                                                                    "<output_dir>/<package_name>.apkg)."),
) -> int:
    cfg = load(ctx)
    collected = collect(cfg, course)
    selected = [c for c in collected.cards if c.pending or (update and c.updatable)]
    result = build(selected, collected.diagnostics, cfg.cloze_notes, vault_root=cfg.vault)
    chosen_target = target.value if target else cfg.target
    if chosen_target == Target.apkg.value:
        drop_unsupported_updates(result, collected.diagnostics)

    ui.header("m2a sync", f"{cfg.vault}  →  {chosen_target}")
    if collected.problems:
        print_problems(collected.diagnostics, cfg)
    _print_counts(result)
    if not result.notes and not result.occlusions:
        console.print("  [dim]nothing to export[/]")
        return 1 if collected.has_errors else 0

    if dry_run:
        console.print()
        cards = [n.card for n in result.notes] + [o.card for o in result.occlusions]
        cards.sort(key=lambda c: (str(c.file), c.line))
        print_card_table(cards,
                         lambda c: "[yellow]update[/]" if c.added else "[green]new[/]", state_header="")
        console.print()
        console.print("  [dim]dry run - nothing written[/]")
        return 0

    seen = len(collected.diagnostics)
    flags = _export(chosen_target, result, cfg, output, collected.diagnostics)
    if flags is None:
        return 2
    print_diagnostics(collected.diagnostics[seen:], cfg)
    _flag(flags, no_flag, yes)
    return 0


def _print_counts(result: BuildResult) -> None:
    new = sum(not n.card.added for n in result.notes)
    updates = sum(n.card.added for n in result.notes)
    console.print(INDENT + ui.kv([("new", new), ("updates", updates), ("image occlusions", len(result.occlusions)),
                                  ("skipped", len(result.skipped))]))


def _print_staged_occlusions(staged: dict[str, list[str]]) -> None:
    for tag, filenames in staged.items():
        console.print()
        console.print(f"  [bold cyan]{escape(tag)}[/]")
        for fname in filenames:
            console.print(f"  - {escape(fname)}")


def _export(target: str, result: BuildResult, cfg: Config, output: Path | None,
            diagnostics: list[Diagnostic]) -> Flags | None:
    """Run the exporter and report; None when it failed."""
    if target == Target.anki.value:
        try:
            export = export_ankiconnect(result, cfg, diagnostics)
        except AnkiConnectError as exc:
            ui.error(str(exc), "open Anki (with the AnkiConnect add-on) and retry, or use `m2a sync --target apkg`")
            return None
        console.print(f"  [green]✓[/] AnkiConnect: [bold]{export.added}[/] added, [bold]{export.updated}[/] updated "
                      f"in deck [bold]{escape(cfg.deck)}[/]  [dim]{export.media_count} media files[/]")
        if result.occlusions:
            base_dir = output.parent if output else cfg.output_dir
            occ_dir, occ_flags, staged = export_occlusions(result.occlusions, base_dir)
            export.flags.extend(occ_flags)
            console.print(f"  [green]✓[/] staged [bold]{len(result.occlusions)}[/] image occlusion(s) to "
                          f"[bold]{escape(str(occ_dir))}[/]")
            _print_staged_occlusions(staged)
        return export.flags

    export = export_apkg(result, output or cfg.apkg_path, cfg=cfg)
    console.print(f"  [green]✓[/] wrote [bold]{escape(str(export.path))}[/]  "
                  f"[dim]deck {escape(cfg.deck)}, {export.note_count} notes, {export.media_count} media files[/]")
    if export.occlusion_dir and export.staged_occlusions:
        console.print(f"  [dim]image occlusion sources:[/] {escape(str(export.occlusion_dir))}")
        _print_staged_occlusions(export.staged_occlusions)
    return export.flags


def _flag(flags: Flags, no_flag: bool, yes: bool) -> None:
    if no_flag:
        console.print("  [dim]ADDED flags not written (--no-flag)[/]")
        return
    new_flags = [(card, card_id) for card, card_id in flags if card.card_id != card_id]
    if not new_flags:
        return
    files = {card.file for card, _ in new_flags}
    if not yes and not ui.confirm(f"Mark {len(new_flags)} card(s) in {len(files)} note(s) as ADDED?"):
        console.print("  [yellow]flags not written[/] - the same cards will be exported again next time; "
                      "re-run with --update if they were imported")
        return
    flagged, problems = write_flags(new_flags)
    console.print(f"  [green]✓[/] flagged [bold]{flagged}[/] card(s) in {len(files)} note(s)")
    for problem in problems:
        console.print(f"  [yellow]![/] {problem}")
