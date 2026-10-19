"""``m2a deleted``: inspect and resolve deleted cards and drift between vault notes and Anki."""
from __future__ import annotations

import fnmatch
from pathlib import Path
import re
import typer

from .. import ui
from ..build import build
from ..config import Config
from ..export.ankiconnect import AnkiConnect, AnkiConnectError, export_ankiconnect, resolve_model_names
from ..flags import write_deleted_flags, write_flags
from ..ids import is_anki_note_id, new_card_id
from ..occlusions import export_occlusions
from ..parser import Card
from ..ui import console, escape
from ..vault import collect
from ._shared import COURSE_OPTION, DRY_RUN_OPTION, YES_OPTION, load, print_diagnostics, rel, short_question

M2A_MARKER_RE = re.compile(r"<!--m2a:([0-9a-z]{4,12})-->")


def _course_tag_prefixes(cfg: Config, course: str, matched_cards: list[Card], matched_sources: list) -> set[str]:
    """Build case-insensitive Anki tag prefixes that belong to the filtered course."""
    prefixes: set[str] = set()
    for c in matched_cards:
        if c.tag:
            prefixes.add(c.tag.lower())
    for src in matched_sources:
        top_folder = src.group.split("/")[0].strip()
        subj = cfg.subject_tag(top_folder)
        if subj:
            full = f"{cfg.base_tag}::{subj}" if cfg.base_tag else subj
            prefixes.add(full.lower())
    subj_direct = cfg.subject_tag(course)
    if subj_direct:
        full = f"{cfg.base_tag}::{subj_direct}" if cfg.base_tag else subj_direct
        prefixes.add(full.lower())
    return prefixes


def _note_matches_course(info: dict, course: str, prefixes: set[str]) -> bool:
    tags = [str(t).lower() for t in (info.get("tags") or [])]
    q = course.lower().replace(" ", "_")
    q_raw = course.lower()
    for t in tags:
        if any(t == p or t.startswith(p + "::") for p in prefixes):
            return True
        if fnmatch.fnmatch(t, f"*{q}*") or q in t or fnmatch.fnmatch(t, f"*{q_raw}*") or q_raw in t:
            return True
    return False


def run(
    ctx: typer.Context,
    course: str | None = COURSE_OPTION,
    suspend: bool = typer.Option(
        False, "--suspend",
        help="Suspend orphaned cards in Anki to preserve review history (cards removed from vault).",
    ),
    delete: bool = typer.Option(
        False, "--delete",
        help="Permanently delete orphaned notes from Anki (cards removed from vault).",
    ),
    mark_deleted: bool = typer.Option(
        False, "--mark-deleted",
        help="Mark cards missing in Anki as DELETED in vault notes.",
    ),
    recreate: bool = typer.Option(
        False, "--recreate",
        help="Re-export cards missing in Anki back into Anki, keeping vault card IDs.",
    ),
    dry_run: bool = DRY_RUN_OPTION,
    yes: bool = YES_OPTION,
) -> int:
    if suspend and delete:
        ui.error("cannot combine --suspend and --delete")
        return 2
    if mark_deleted and recreate:
        ui.error("cannot combine --mark-deleted and --recreate")
        return 2

    cfg = load(ctx)
    client = AnkiConnect(cfg.anki_connect_url)
    try:
        if not client.reachable():
            ui.error(f"cannot reach AnkiConnect at {cfg.anki_connect_url} - is Anki running?")
            return 2

        # Always collect all vault cards first so cards from other courses are never treated as orphans
        all_collected = collect(cfg, None, trace_fn=ui.trace)
        all_vault_cids: set[str] = {c.card_id for c in all_collected.cards if c.card_id and not c.deleted}

        collected = collect(cfg, course, trace_fn=ui.trace) if course else all_collected
        course_prefixes = _course_tag_prefixes(cfg, course, collected.cards, collected.sources) if course else set()

        model_names = list(resolve_model_names(client, cfg).values())
        for io_name in ("Image Occlusion", "Image Occlusion Enhanced"):
            if io_name not in model_names:
                model_names.append(io_name)
        model_query = " or ".join([f'note:"{name}"' for name in model_names])
        note_ids = client.invoke("findNotes", query=model_query) or []
        notes_info = client.notes_info(note_ids) if note_ids else []
    except AnkiConnectError as exc:
        ui.error(str(exc))
        return 2

    orphaned_notes: list[dict] = []
    anki_cids: set[str] = set()

    for info in notes_info:
        if not isinstance(info, dict):
            continue
        nid = info.get("noteId")
        if not nid:
            continue
        cid = None
        for fval in info.get("fields", {}).values():
            val = fval.get("value", "") if isinstance(fval, dict) else str(fval)
            m = M2A_MARKER_RE.search(val)
            if m:
                cid = m.group(1)
                anki_cids.add(cid)
                break
        if cid and cid not in all_vault_cids:
            if course and not _note_matches_course(info, course, course_prefixes):
                continue
            preview = ""
            for fname in ("Front", "Text", "Header", "Image", "Occlusion", "Comments"):
                if fname in info.get("fields", {}):
                    v = info["fields"][fname]
                    raw_val = (v.get("value", "") if isinstance(v, dict) else str(v)).strip()
                    cleaned = M2A_MARKER_RE.sub("", raw_val).strip()
                    if cleaned:
                        preview = cleaned
                        break
            if not preview:
                preview = f"[{info.get('modelName', 'Card')}]"
            orphaned_notes.append({
                "note_id": nid,
                "card_id": cid,
                "model": info.get("modelName", ""),
                "preview": preview,
                "cards": info.get("cards", []),
            })

    suspended_card_ids: set[int] = set()
    if orphaned_notes:
        try:
            res = client.invoke("findCards", query="is:suspended")
            if isinstance(res, list):
                suspended_card_ids = {int(c) for c in res}
        except Exception:
            suspended_card_ids = set()

    for o in orphaned_notes:
        card_ids = o.get("cards", [])
        o["is_suspended"] = bool(card_ids and any(int(c) in suspended_card_ids for c in card_ids))

    suspended_orphans_count = sum(1 for o in orphaned_notes if o.get("is_suspended"))

    missing_in_anki = [c for c in collected.cards if c.card_id and not c.deleted and c.card_id not in anki_cids]

    summary_parts = []
    if orphaned_notes:
        if suspended_orphans_count > 0:
            summary_parts.append(f"{len(orphaned_notes)} orphaned in Anki ({suspended_orphans_count} suspended)")
        else:
            summary_parts.append(f"{len(orphaned_notes)} orphaned in Anki")
    if missing_in_anki:
        summary_parts.append(f"{len(missing_in_anki)} missing in Anki")
    summary_text = ", ".join(summary_parts) if summary_parts else "0 issues detected"

    ui.header("m2a deleted", summary_text)

    if not orphaned_notes and not missing_in_anki:
        console.print("  [green]✓[/] All cards in sync: 0 orphaned in Anki, 0 missing in Anki.")
        return 0

    if orphaned_notes:
        console.print(f"  [bold]Section 1: Orphaned Cards in Anki (Deleted from Vault):[/] {len(orphaned_notes)} note(s)")
        rows = []
        for o in orphaned_notes:
            clean_preview = re.sub(r"<[^>]+>", "", o["preview"]).replace("\n", " ").strip()
            if not clean_preview:
                clean_preview = f"[{o['model']}]"
            elif len(clean_preview) > 55:
                clean_preview = clean_preview[:52] + "..."
            status_str = "[yellow]suspended[/]" if o.get("is_suspended") else "[dim]active[/]"
            rows.append([
                f"[dim]{escape(o['card_id'])}[/]",
                str(o["note_id"]),
                escape(o["model"]),
                status_str,
                escape(clean_preview),
            ])
        console.print(ui.table(["id", "note id", "model", "status", "question"], rows))
        console.print()

    if missing_in_anki:
        console.print(f"  [bold]Section 2: Cards Deleted in Anki (Still Active in Vault):[/] {len(missing_in_anki)} card(s)")
        missing_rows = [
            [f"[dim]{escape(c.card_id or '')}[/]", escape(f"{rel(c.file, cfg)}:{c.line}"), escape(short_question(c))]
            for c in missing_in_anki
        ]
        console.print(ui.table(["id", "where", "question"], missing_rows))
        console.print()

    if dry_run:
        if suspend and orphaned_notes:
            card_ids_to_suspend = [cid for o in orphaned_notes for cid in o["cards"]]
            console.print(f"  [dim]dry run - would suspend {len(card_ids_to_suspend)} card(s)[/]")
        if delete and orphaned_notes:
            if suspended_orphans_count > 0:
                console.print(
                    f"  [dim]dry run - would delete {len(orphaned_notes)} orphaned note(s) in Anki "
                    f"({suspended_orphans_count} suspended)[/]"
                )
            else:
                console.print(f"  [dim]dry run - would delete {len(orphaned_notes)} orphaned note(s) in Anki[/]")
        if mark_deleted and missing_in_anki:
            files = {c.file for c in missing_in_anki}
            console.print(f"  [dim]dry run - would mark {len(missing_in_anki)} card(s) as DELETED in {len(files)} note(s)[/]")
        if recreate and missing_in_anki:
            console.print(f"  [dim]dry run - would recreate {len(missing_in_anki)} card(s) in Anki[/]")
        if not any((suspend, delete, mark_deleted, recreate)):\
            console.print("  [dim]dry run - nothing modified[/]")
        return 0

    acted = False

    # Section 1 Actions
    if suspend:
        acted = True
        card_ids_to_suspend = [cid for o in orphaned_notes for cid in o["cards"]]
        if card_ids_to_suspend:
            try:
                client.invoke("suspend", cards=card_ids_to_suspend)
            except AnkiConnectError as exc:
                ui.error(str(exc))
                return 2
            console.print(f"  [green]✓[/] Suspended [bold]{len(card_ids_to_suspend)}[/] card(s) belonging to [bold]{len(orphaned_notes)}[/] orphaned note(s).")

    elif delete:
        acted = True
        if orphaned_notes:
            if suspended_orphans_count > 0:
                console.print(
                    f"  [bold yellow]warning:[/] {suspended_orphans_count} of {len(orphaned_notes)} "
                    "orphaned note(s) contain suspended cards in Anki."
                )
                console.print(
                    "  [dim]These cards may have been suspended to preserve review history and intervals.[/]"
                )

            delete_prompt = (
                f"Permanently delete all {len(orphaned_notes)} orphaned note(s) "
                f"(including {suspended_orphans_count} suspended) from Anki?"
                if suspended_orphans_count > 0
                else f"Permanently delete {len(orphaned_notes)} orphaned note(s) from Anki?"
            )
            if not yes and not ui.confirm(delete_prompt):
                console.print("  [dim]aborted - nothing deleted in Anki[/]")
            else:
                nids_to_delete = [o["note_id"] for o in orphaned_notes]
                try:
                    client.invoke("deleteNotes", notes=nids_to_delete)
                except AnkiConnectError as exc:
                    ui.error(str(exc))
                    return 2
                console.print(f"  [green]✓[/] Permanently deleted [bold]{len(nids_to_delete)}[/] orphaned note(s) from Anki.")

    # Section 2 Actions
    if mark_deleted:
        acted = True
        if missing_in_anki:
            files = {c.file for c in missing_in_anki}
            if not yes and not ui.confirm(f"Mark {len(missing_in_anki)} missing card(s) in {len(files)} note(s) as DELETED?"):
                console.print("  [dim]aborted - nothing marked in vault[/]")
            else:
                try:
                    flagged, problems = write_deleted_flags(missing_in_anki)
                except OSError as exc:
                    ui.error(f"failed to mark cards as deleted: {exc}")
                    return 1
                console.print(f"  [green]✓[/] Marked [bold]{flagged}[/] card(s) as DELETED in {len(files)} note(s).")
                if problems:
                    for problem in problems:
                        console.print(f"  [yellow]![/] {escape(problem)}")
                    return 1

    elif recreate:
        acted = True
        if missing_in_anki:
            if not yes and not ui.confirm(f"Re-export {len(missing_in_anki)} missing card(s) to Anki?"):
                console.print("  [dim]aborted - nothing recreated[/]")
            else:
                # Normalize legacy numeric Anki IDs so export_ankiconnect treats them as recreatable
                for c in missing_in_anki:
                    if is_anki_note_id(c.card_id):
                        c.card_id = new_card_id()
                seen = len(collected.diagnostics)
                res = build(
                    missing_in_anki,
                    collected.diagnostics,
                    cfg.cloze_notes,
                    vault_root=cfg.vault,
                    hash_media=cfg.hash_media,
                    image_occlusion_mode=cfg.image_occlusion_mode,
                )
                try:
                    export = export_ankiconnect(res, cfg, collected.diagnostics, recreate_missing=True)
                except AnkiConnectError as exc:
                    ui.error(str(exc))
                    return 2
                if res.occlusions:
                    occ_dir, occ_flags, _ = export_occlusions(res.occlusions, cfg.output_dir)
                    export.flags.extend(occ_flags)
                    console.print(f"  [green]✓[/] Staged [bold]{len(res.occlusions)}[/] image occlusion(s) to [bold]{escape(str(occ_dir))}[/].")
                print_diagnostics(collected.diagnostics[seen:], cfg)
                # Only write flags if any card ID actually changed (e.g. migrated legacy ID)
                changed_flags = [(card, cid) for card, cid in export.flags if card.card_id != cid]
                if changed_flags:
                    try:
                        _, problems = write_flags(changed_flags)
                    except OSError as exc:
                        ui.error(f"failed to update flags in vault: {exc}")
                        return 1
                    if problems:
                        for problem in problems:
                            console.print(f"  [yellow]![/] {escape(problem)}")
                        return 1
                console.print(f"  [green]✓[/] Recreated [bold]{export.added}[/] card(s) in deck [bold]{escape(cfg.deck)}[/].")

    if not acted:
        console.print("  [bold]To resolve:[/]")
        if orphaned_notes and not (delete or suspend):
            console.print("    • Orphaned cards in Anki:  [cyan]m2a deleted --delete[/]  (or [cyan]--suspend[/])")
        if missing_in_anki and not (mark_deleted or recreate):
            console.print("    • Cards deleted in Anki:   [cyan]m2a deleted --mark-deleted[/]  (or [cyan]--recreate[/])")
    return 0
