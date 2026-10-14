"""``m2a templates``: compare the local card templates with the note types in Anki and push them."""
from __future__ import annotations

import typer

from .. import ui
from ..export.ankiconnect import AnkiConnect, AnkiConnectError, push_template, template_status
from ..ui import console, escape
from ._shared import YES_OPTION, load


def run(
    ctx: typer.Context,
    yes: bool = YES_OPTION,
    diff: bool = typer.Option(False, "--diff", help="Only show what differs, never push."),
) -> int:
    cfg = load(ctx)
    ui.header("m2a templates", f"{cfg.templates_dir}  →  {cfg.anki_connect_url}")
    client = AnkiConnect(cfg.anki_connect_url)
    try:
        statuses = template_status(client, cfg)
    except AnkiConnectError as exc:
        ui.error(str(exc), "open Anki with the AnkiConnect add-on and retry")
        return 2
    if not statuses:
        console.print("  [dim]no matching note types in Anki yet - they are created on the first sync[/]")
        return 0

    for status in statuses:
        state = "[green]up to date[/]" if status.up_to_date else f"[yellow]differs: {', '.join(status.changed)}[/]"
        console.print(f"  [bold]{escape(status.name):40}[/] [dim]{status.kind}[/]  {state}")
    stale = [s for s in statuses if not s.up_to_date]
    if not stale or diff:
        return 0

    console.print()
    console.print("  [yellow]note:[/] this replaces the card template and styling of the note type(s) above in Anki "
                  "with your local files. Cards and review history are untouched.")
    if not yes and not ui.confirm(f"Push templates for {len(stale)} note type(s)?"):
        console.print("  [dim]nothing changed[/]")
        return 0
    for status in stale:
        push_template(client, status)
        console.print(f"  [green]✓[/] {escape(status.name)}: pushed {', '.join(status.changed)}")
    return 0
