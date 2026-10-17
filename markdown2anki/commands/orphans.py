"""``m2a orphans``: inspect and manage cards in Anki whose source notes were removed from vault."""
from __future__ import annotations

import re
import typer

from .. import ui
from ..export.ankiconnect import AnkiConnect, AnkiConnectError, resolve_model_names
from ..ui import console, escape
from ..vault import collect
from ._shared import COURSE_OPTION, YES_OPTION, load

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

    # 2. Query Anki for notes under M2A models
    model_names = list(resolve_model_names(client, cfg).values())
    model_query = " or ".join([f'note:"{name}"' for name in model_names])
    note_ids = client.invoke("findNotes", query=model_query) or []
    if not note_ids:
        ui.header("m2a orphans", str(cfg.vault))
        console.print("  [dim]No notes found under M2A models in Anki.[/]")
        return 0

    notes_info = client.notes_info(note_ids)
    orphaned_notes: list[dict] = []

    for info in notes_info:
        nid = info["noteId"]
        cid = None
        for fval in info.get("fields", {}).values():
            val = fval.get("value", "") if isinstance(fval, dict) else str(fval)
            m = M2A_MARKER_RE.search(val)
            if m:
                cid = m.group(1)
                break
        if cid and cid not in vault_card_ids:
            preview = ""
            for fname in ("Front", "Text", "Header", "Comments"):
                if fname in info.get("fields", {}):
                    v = info["fields"][fname]
                    preview = (v.get("value", "") if isinstance(v, dict) else str(v)).strip()
                    if preview:
                        break
            orphaned_notes.append({
                "note_id": nid,
                "card_id": cid,
                "model": info.get("modelName", ""),
                "preview": preview,
                "cards": info.get("cards", []),
            })

    ui.header("m2a orphans", f"{len(orphaned_notes)} orphaned note(s) in Anki")

    if not orphaned_notes:
        console.print("  [green]✓[/] All Anki cards match notes in your vault. Zero orphaned cards.")
        return 0

    rows = []
    for o in orphaned_notes:
        clean_preview = re.sub(r"<[^>]+>", "", o["preview"]).replace("\n", " ").strip()
        if len(clean_preview) > 55:
            clean_preview = clean_preview[:52] + "..."
        rows.append([f"[dim]{o['card_id']}[/]", str(o["note_id"]), o["model"], escape(clean_preview)])

    console.print(ui.table(["id", "note id", "model", "question"], rows))
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

    console.print("  [dim]Run with `m2a orphans --suspend` to suspend them, or `m2a orphans --delete` to delete permanently.[/]")
    return 0
