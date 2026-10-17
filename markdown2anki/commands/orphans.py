"""``m2a orphans``: inspect and manage cards in Anki whose source notes were removed from vault."""
from __future__ import annotations

import re
import typer

from .. import ui
from ..export.ankiconnect import AnkiConnect, AnkiConnectError, resolve_model_names
from ..ui import console, escape
from ..vault import collect
from ._shared import COURSE_OPTION, YES_OPTION, load, rel, short_question

M2A_MARKER_RE = re.compile(r"<!--m2a:([0-9a-z]{4,12})-->")


def run(
    ctx: typer.Context,
    course: str | None = COURSE_OPTION,
    suspend: bool = typer.Option(False, "--suspend", help="Suspend all orphaned cards in Anki to preserve learning history without active reviews."),
    delete: bool = typer.Option(False, "--delete", help="Permanently delete orphaned notes from Anki database."),
    yes: bool = YES_OPTION,
) -> int:
    cfg = load(ctx)
    client = AnkiConnect(cfg.anki_connect_url)
    try:
        if not client.reachable():
            ui.error(f"cannot reach AnkiConnect at {cfg.anki_connect_url} - is Anki running?")
            return 2
    except AnkiConnectError as exc:
        ui.error(str(exc))
        return 2

    # 1. Collect all active card IDs currently present in vault (ignore cards marked as DELETED:)
    collected = collect(cfg, course, trace_fn=ui.trace)
    vault_card_ids: set[str] = {c.card_id for c in collected.cards if c.card_id and not c.deleted}

    # 2. Query Anki for notes under M2A models (including Image Occlusion)
    model_names = list(resolve_model_names(client, cfg).values())
    for io_name in ("Image Occlusion", "Image Occlusion Enhanced"):
        if io_name not in model_names:
            model_names.append(io_name)
    model_query = " or ".join([f'note:"{name}"' for name in model_names])
    note_ids = client.invoke("findNotes", query=model_query) or []
    if not note_ids:
        ui.header("m2a orphans", str(cfg.vault))
        console.print("  [dim]No notes found under M2A models in Anki.[/]")
        return 0

    notes_info = client.notes_info(note_ids)
    orphaned_notes: list[dict] = []
    anki_cids: set[str] = set()

    for info in notes_info:
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
        if cid and cid not in vault_card_ids:
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

    missing_in_anki = [c for c in collected.cards if c.card_id and not c.deleted and c.card_id not in anki_cids]

    summary_parts = []
    if orphaned_notes:
        summary_parts.append(f"{len(orphaned_notes)} orphaned in Anki")
    if missing_in_anki:
        summary_parts.append(f"{len(missing_in_anki)} deleted in Anki")
    summary_text = ", ".join(summary_parts) if summary_parts else "0 issues detected"

    ui.header("m2a orphans", summary_text)

    if not orphaned_notes and not missing_in_anki:
        console.print("  [green]✓[/] All cards in sync: zero orphaned in Anki, and zero deleted in vault.")
        return 0

    if orphaned_notes:
        console.print(f"  [bold]Section 1: Orphaned Cards in Anki (Deleted from Obsidian):[/] {len(orphaned_notes)} note(s)")
        rows = []
        for o in orphaned_notes:
            clean_preview = re.sub(r"<[^>]+>", "", o["preview"]).replace("\n", " ").strip()
            if not clean_preview:
                clean_preview = f"[{o['model']}]"
            elif len(clean_preview) > 55:
                clean_preview = clean_preview[:52] + "..."
            rows.append([f"[dim]{o['card_id']}[/]", str(o["note_id"]), o["model"], escape(clean_preview)])
        console.print(ui.table(["id", "note id", "model", "question"], rows))
        console.print()

    if missing_in_anki:
        console.print(f"  [bold]Section 2: Cards Deleted in Anki (Still Active in Obsidian):[/] {len(missing_in_anki)} card(s)")
        missing_rows = []
        for c in missing_in_anki:
            q_text = short_question(c)
            missing_rows.append([f"[dim]{c.card_id}[/]", escape(f"{rel(c.file, cfg)}:{c.line}"), escape(q_text)])
        console.print(ui.table(["id", "where", "question"], missing_rows))
        console.print()

    if suspend:
        card_ids_to_suspend = [cid for o in orphaned_notes for cid in o["cards"]]
        if card_ids_to_suspend:
            client.invoke("suspend", cards=card_ids_to_suspend)
            console.print(f"  [green]✓[/] Suspended [bold]{len(card_ids_to_suspend)}[/] card(s) belonging to [bold]{len(orphaned_notes)}[/] orphaned note(s).")
        return 0

    if delete:
        if not yes and not ui.confirm(f"Permanently delete {len(orphaned_notes)} orphaned note(s) from Anki?"):
            console.print("  [dim]aborted - nothing deleted[/]")
            return 0
        nids_to_delete = [o["note_id"] for o in orphaned_notes]
        client.invoke("deleteNotes", notes=nids_to_delete)
        console.print(f"  [green]✓[/] Permanently deleted [bold]{len(nids_to_delete)}[/] orphaned note(s) from Anki.")
        return 0

    hint_parts = []
    if orphaned_notes:
        hint_parts.append("`m2a orphans --suspend` or `m2a orphans --delete` for orphaned Anki cards")
    if missing_in_anki:
        hint_parts.append("`m2a sync --mark-deleted` (to mark DELETED in vault) or `m2a sync --update --recreate-missing` (to recreate in Anki)")
    if hint_parts:
        console.print("  [dim]Run " + " | ".join(hint_parts) + "[/]")
    return 0
