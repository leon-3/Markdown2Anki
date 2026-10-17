"""``m2a sync``: export pending cards (and, with ``--update``, already exported ones) and flag them."""
from __future__ import annotations

from pathlib import Path

import typer

from .. import ui
from ..build import BuildResult, build
from ..config import Config, Target
import re
from ..export.ankiconnect import AnkiConnect, AnkiConnectError, export_ankiconnect, resolve_model_names
from ..export.apkg import drop_unsupported_updates, export_apkg
from ..flags import write_deleted_flags, write_flags
from ..occlusions import export_occlusions
from ..parser import KIND_IMAGE_OCCLUSION, Card, Diagnostic
from ..ui import console, escape
from ..vault import collect
from ._shared import COURSE_OPTION, INDENT, load, print_card_table, print_diagnostics, print_problems

M2A_MARKER_RE = re.compile(r"<!--m2a:([0-9a-z]{4,12})-->")


def _find_missing_in_anki(cfg: Config, cards: list[Card]) -> list[Card]:
    cards_with_ids = [c for c in cards if c.card_id and not c.deleted]
    if not cards_with_ids:
        return []
    try:
        client = AnkiConnect(cfg.anki_connect_url)
        if not client.reachable():
            return []
        model_names = list(resolve_model_names(client, cfg).values())
        for io_name in ("Image Occlusion", "Image Occlusion Enhanced"):
            if io_name not in model_names:
                model_names.append(io_name)
        model_query = " or ".join([f'note:"{n}"' for n in model_names])
        note_ids = client.invoke("findNotes", query=model_query) or []
        if not note_ids:
            return cards_with_ids
        notes_info = client.notes_info(note_ids)
        anki_cids: set[str] = set()
        for info in notes_info:
            if not isinstance(info, dict) or not info.get("noteId"):
                continue
            for f in info.get("fields", {}).values():
                val = f.get("value", "") if isinstance(f, dict) else str(f)
                m = M2A_MARKER_RE.search(val)
                if m:
                    anki_cids.add(m.group(1))
                    break
        return [c for c in cards_with_ids if c.card_id not in anki_cids]
    except Exception:
        return []


Flags = list[tuple[Card, str]]


def run(
    ctx: typer.Context,
    course: str | None = COURSE_OPTION,
    target: Target | None = typer.Option(None, "--target", help="apkg: write a package file; anki: push via "
                                                                "AnkiConnect (default: 'target' in config)."),
    update: bool = typer.Option(False, "--update", help="Also re-export cards that were already added with an id "
                                                        "(updates them in Anki)."),
    mark_deleted: bool = typer.Option(False, "--mark-deleted", help="Mark cards missing in Anki as DELETED in markdown notes."),
    recreate_missing: bool = typer.Option(False, "--recreate-missing", help="Recreate cards in Anki that were deleted in Anki."),
    dry_run: bool = typer.Option(False, "-n", "--dry-run", help="Show what would be exported, write nothing."),
    no_flag: bool = typer.Option(False, "--no-flag", help="Export but do not write ADDED flags into the notes."),
    yes: bool = typer.Option(False, "-y", "--yes", help="Do not ask before writing ADDED flags."),
    output: Path | None = typer.Option(None, "-o", "--output", help="apkg path (default: "
                                                                    "<output_dir>/<package_name>.apkg)."),
    stage_occlusions: bool = typer.Option(False, "--stage-occlusions", help="Also re-stage already-flagged image occlusions during --update."),
) -> int:
    cfg = load(ctx)
    collected = collect(cfg, course, trace_fn=ui.trace)
    chosen_target = target.value if target else cfg.target
    effective_occ_mode = cfg.image_occlusion_mode if chosen_target != Target.apkg.value else "stage"
    should_stage_occ = stage_occlusions or cfg.re_stage_occlusions
    should_check_existing = update or mark_deleted or recreate_missing
    include_occ = (effective_occ_mode == "native") or should_stage_occ or mark_deleted or recreate_missing
    selected = [
        c for c in collected.cards
        if c.pending or (should_check_existing and c.updatable and (c.kind != KIND_IMAGE_OCCLUSION or include_occ))
    ]
    result = build(
        selected,
        collected.diagnostics,
        cfg.cloze_notes,
        vault_root=cfg.vault,
        hash_media=cfg.hash_media,
        image_occlusion_mode=effective_occ_mode,
    )
    if chosen_target == Target.apkg.value:
        drop_unsupported_updates(result, collected.diagnostics)

    ui.header("m2a sync", f"{cfg.vault}  →  {chosen_target}")
    if collected.problems:
        print_problems(collected.diagnostics, cfg)
    _print_counts(result)

    missing_warning: list[Card] = []
    if chosen_target == Target.anki.value and not should_check_existing:
        missing_warning = _find_missing_in_anki(cfg, collected.cards)

    if not result.notes and not result.occlusions:
        console.print("  [dim]nothing to export[/]")
        if missing_warning:
            console.print(f"  [yellow]warning:[/] {len(missing_warning)} card(s) were deleted in Anki (still active in vault) - run `m2a sync --mark-deleted` to mark them in vault, or `m2a orphans` to inspect")
        return 1 if collected.has_errors else 0

    if dry_run:
        console.print()
        cards = [n.card for n in result.notes] + [o.card for o in result.occlusions]
        cards.sort(key=lambda c: (str(c.file), c.line))
        print_card_table(cards,
                         lambda c: "[yellow]update[/]" if c.added else "[green]new[/]", state_header="")
        console.print()
        console.print("  [dim]dry run - nothing written[/]")
        if missing_warning:
            console.print(f"  [yellow]warning:[/] {len(missing_warning)} card(s) were deleted in Anki (still active in vault) - run `m2a sync --mark-deleted` to mark them in vault, or `m2a orphans` to inspect")
        return 0

    seen = len(collected.diagnostics)
    flags, missing = _export(chosen_target, result, cfg, output, collected.diagnostics, recreate_missing=recreate_missing)
    if flags is None:
        return 2
    print_diagnostics(collected.diagnostics[seen:], cfg)
    _flag(flags, no_flag, yes)

    if missing:
        if mark_deleted:
            flagged, problems = write_deleted_flags(missing)
            console.print(f"  [green]✓[/] marked [bold]{flagged}[/] card(s) as DELETED in {len({c.file for c in missing})} note(s)")
            for problem in problems:
                console.print(f"  [yellow]![/] {problem}")
        else:
            console.print(f"  [dim]({len(missing)} missing card(s) skipped in Anki; run `m2a sync --mark-deleted` to mark them in vault)[/]")
    elif missing_warning:
        console.print(f"  [yellow]warning:[/] {len(missing_warning)} card(s) were deleted in Anki (still active in vault) - run `m2a sync --mark-deleted` to mark them in vault, or `m2a orphans` to inspect")
    return 0


def _print_counts(result: BuildResult) -> None:
    new = sum(not n.card.added for n in result.notes)
    updates = sum(n.card.added for n in result.notes)
    console.print(INDENT + ui.kv([("new", new), ("updates", updates), ("image occlusions", len(result.occlusions)),
                                  ("skipped", len(result.skipped))]))


def _print_sync_summary(added: int, text_cloze: int, image_cloze: int, basic: int, updated: int) -> None:
    parts: list[str] = []
    if added > 0:
        details: list[str] = []
        if text_cloze > 0:
            details.append(f"[bold]{text_cloze}[/] text cloze{'s' if text_cloze != 1 else ''}")
        if image_cloze > 0:
            details.append(f"[bold]{image_cloze}[/] image cloze{'s' if image_cloze != 1 else ''}")
        if basic > 0:
            details.append(f"[bold]{basic}[/] basic")
        detail_str = f" ({', '.join(details)})" if details else ""
        parts.append(f"[bold]{added}[/] added{detail_str}")
    else:
        parts.append("[dim]0 added[/]")

    if updated > 0:
        parts.append(f"[bold]{updated}[/] updated")
    else:
        parts.append("[dim]0 updated[/]")

    summary_str = " · ".join(parts)
    console.print(f"  [green]✓[/] [bold]Sync Summary:[/] {summary_str}")


def _print_staged_occlusions(staged: dict[str, list[str]]) -> None:
    for tag, filenames in staged.items():
        console.print()
        console.print(f"  [bold cyan]{escape(tag)}[/]")
        for fname in filenames:
            console.print(f"  - {escape(fname)}")


def _export(target: str, result: BuildResult, cfg: Config, output: Path | None,
            diagnostics: list[Diagnostic], recreate_missing: bool = False) -> tuple[Flags | None, list[Card]]:
    """Run the exporter and report; (None, []) when it failed."""
    if target == Target.anki.value:
        try:
            export = export_ankiconnect(result, cfg, diagnostics, recreate_missing=recreate_missing)
        except AnkiConnectError as exc:
            ui.error(str(exc), "open Anki (with the AnkiConnect add-on) and retry, or use `m2a sync --target apkg`")
            return None, []
        parts = [f"[bold]{export.added}[/] added", f"[bold]{export.updated}[/] updated"]
        if export.unchanged:
            parts.append(f"[dim]{export.unchanged} unchanged[/]")
        summary_str = ", ".join(parts)
        console.print(f"  [green]✓[/] AnkiConnect: {summary_str} "
                      f"in deck [bold]{escape(cfg.deck)}[/]  [dim]{export.media_count} media files[/]")
        if result.occlusions:
            base_dir = output.parent if output else cfg.output_dir
            occ_dir, occ_flags, staged = export_occlusions(result.occlusions, base_dir)
            export.flags.extend(occ_flags)
            console.print(f"  [green]✓[/] staged [bold]{len(result.occlusions)}[/] image occlusion(s) to "
                          f"[bold]{escape(str(occ_dir))}[/]")
            _print_staged_occlusions(staged)

        total_added = export.added + len(result.occlusions)
        total_img_cloze = export.added_image_cloze + len(result.occlusions)
        total_text_cloze = export.added_text_cloze
        total_basic = export.added_basic
        _print_sync_summary(total_added, total_text_cloze, total_img_cloze, total_basic, export.updated)

        return export.flags, export.missing_in_anki

    export = export_apkg(result, output or cfg.apkg_path, cfg=cfg)
    console.print(f"  [green]✓[/] wrote [bold]{escape(str(export.path))}[/]  "
                  f"[dim]deck {escape(cfg.deck)}, {export.note_count} notes, {export.media_count} media files[/]")
    if export.occlusion_dir and export.staged_occlusions:
        console.print(f"  [dim]image occlusion sources:[/] {escape(str(export.occlusion_dir))}")
        _print_staged_occlusions(export.staged_occlusions)

    from ..build import MODEL_BASIC, MODEL_CLOZE, MODEL_IMAGE_OCCLUSION
    text_cloze = sum(1 for n in result.notes if n.model == MODEL_CLOZE and not n.card.added)
    img_cloze = sum(1 for n in result.notes if n.model == MODEL_IMAGE_OCCLUSION and not n.card.added) + len(result.occlusions)
    basic = sum(1 for n in result.notes if n.model == MODEL_BASIC and not n.card.added)
    total_added = text_cloze + img_cloze + basic
    _print_sync_summary(total_added, text_cloze, img_cloze, basic, 0)

    return export.flags, []


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
