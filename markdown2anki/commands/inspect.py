"""``m2a config``, ``m2a check`` and ``m2a status``: read-only inspection and configuration commands."""
from __future__ import annotations

import os
from pathlib import Path
import shlex
import subprocess
import sys

from rich import box
from rich.panel import Panel
from rich.syntax import Syntax
import typer

def click_edit(filename: str, editor: str | None = None) -> None:
    """Open the file at filename in a text editor."""
    try:
        import click
        if hasattr(click, 'edit'):
            click.edit(filename=filename, editor=editor)
            return
    except Exception:
        pass

    editor_cmd = editor or os.environ.get('VISUAL') or os.environ.get('EDITOR')
    if not editor_cmd:
        if os.name == 'posix':
            editor_cmd = 'nano' if os.path.exists('/usr/bin/nano') or os.path.exists('/bin/nano') else 'vi'
        elif os.name == 'nt':
            editor_cmd = 'notepad'
        else:
            editor_cmd = 'vi'
    cmd = shlex.split(editor_cmd) + [filename]
    subprocess.run(cmd, check=True)

from .. import ui
from ..build import build
from ..config import Config, Target, load_config
from ..export.ankiconnect import AnkiConnect, resolve_completed_occlusions
from ..ui import console, escape
from ..vault import collect
from ._shared import (
    COURSE_OPTION,
    FILE_OPTION,
    INDENT,
    VERBOSE_OPTION,
    load,
    print_card_table,
    print_problems,
    rel,
    resolve_note_file,
    summary_line,
)


def _validate_config_semantics(cfg: Config) -> list[str]:
    errors: list[str] = []
    if not cfg.vault.is_dir():
        errors.append(f"vault directory does not exist: {cfg.vault}")
    if cfg.target not in (Target.anki.value, Target.apkg.value):
        errors.append(f"invalid target '{cfg.target}' (expected 'anki' or 'apkg')")
    if cfg.image_occlusion_mode not in ("stage", "native"):
        errors.append(f"invalid image_occlusion_mode '{cfg.image_occlusion_mode}' (expected 'stage' or 'native')")
    if not cfg.deck or not cfg.deck.strip() or cfg.deck.startswith("::") or cfg.deck.endswith("::"):
        errors.append(f"invalid deck name '{cfg.deck}'")
    if not cfg.anki_connect_url.startswith(("http://", "https://")):
        errors.append(f"invalid anki_connect_url '{cfg.anki_connect_url}' (must start with http:// or https://)")
    return errors


def config(
    ctx: typer.Context,
    path: bool = typer.Option(False, "--path", help="Print only the path to the active config file."),
    raw: bool = typer.Option(False, "--raw", help="Print the raw TOML config content without formatting."),
    edit: bool = typer.Option(False, "--edit", help="Open the active config file in $EDITOR and validate afterwards."),
    validate: bool = typer.Option(False, "--validate", help="Validate active configuration syntax, semantics, and AnkiConnect reachability."),
) -> int:
    if sum((path, raw, edit, validate)) > 1:
        ui.error("options --path, --raw, --edit, and --validate are mutually exclusive")
        return 2

    cfg = load(ctx)
    if path:
        if not cfg.source:
            ui.error("no configuration file in use (run `m2a init` first)")
            return 2
        sys.stdout.write(f"{cfg.source}\n")
        return 0

    if raw:
        if not cfg.source or not cfg.source.is_file():
            ui.error("no configuration file in use (run `m2a init` first)")
            return 2
        raw_text = cfg.source.read_text(encoding="utf-8")
        if sys.stdout.isatty():
            console.print(Syntax(raw_text, "toml", theme="ansi_dark", background_color="default"))
        else:
            sys.stdout.write(raw_text)
        return 0

    if validate:
        if not cfg.source or not cfg.source.is_file():
            ui.error("no configuration file in use (run `m2a init` first)")
            return 2
        console.print(f"Validating configuration at [bold]{escape(str(cfg.source))}[/]:")
        semantic_errors = _validate_config_semantics(cfg)

        anki_err = None
        if cfg.target == Target.anki.value:
            client = AnkiConnect(cfg.anki_connect_url)
            try:
                if not client.reachable():
                    anki_err = f"AnkiConnect not reachable at {cfg.anki_connect_url}"
            except Exception as exc:
                anki_err = f"AnkiConnect error: {exc}"

        if semantic_errors:
            for err in semantic_errors:
                console.print(f"  [red]✗[/] {escape(err)}")
        else:
            console.print("  [green]✓[/] Syntax and semantic configuration valid")
            console.print(f"  [green]✓[/] Vault directory exists: {escape(str(cfg.vault))}")
            console.print(f"  [green]✓[/] Target: {cfg.target} (deck: {escape(cfg.deck)})")

        if anki_err:
            console.print(f"  [yellow]![/] {escape(anki_err)}")
        elif cfg.target == Target.anki.value:
            console.print(f"  [green]✓[/] AnkiConnect online at {escape(cfg.anki_connect_url)}")

        return 1 if semantic_errors else 0

    if edit:
        if not cfg.source or not cfg.source.is_file():
            ui.error("no configuration file found to edit (run `m2a init` first)")
            return 2
        if not ui.interactive():
            ui.error("cannot run `m2a config --edit` in non-interactive mode (no TTY)")
            return 2
        try:
            click_edit(filename=str(cfg.source))
        except Exception as exc:
            ui.error(f"could not launch editor: {exc}")
            return 2
        try:
            reloaded = load_config(cfg.source)
        except (ValueError, OSError) as exc:
            ui.error(f"invalid config after edit: {exc}")
            return 2
        semantic_errors = _validate_config_semantics(reloaded)
        if semantic_errors:
            for err in semantic_errors:
                ui.error(err)
            return 2
        console.print(f"  [green]✓[/] Configuration at [bold]{escape(str(cfg.source))}[/] is valid.")
        return 0

    ui.header("m2a config", str(cfg.source or "defaults"))
    vault_ok = "[green]✓ exists[/]" if cfg.vault.is_dir() else "[red]✗ missing[/]"
    tpl_ok = "[green]✓[/]" if cfg.templates_dir.is_dir() else "[dim]built-in[/]"

    client = AnkiConnect(cfg.anki_connect_url)
    try:
        anki_online = client.reachable()
    except Exception:
        anki_online = False
    anki_status = (
        "[green]✓ online[/]"
        if anki_online
        else ("[dim]offline (target is apkg)[/]" if cfg.target == "apkg" else "[red]✗ offline[/]")
    )

    body_lines = [
        f"[dim]source[/]      {escape(str(cfg.source or 'defaults'))}",
        f"[dim]vault[/]       {escape(str(cfg.vault))}  {vault_ok}",
        f"[dim]target[/]      {escape(cfg.target)}  [dim](deck: {escape(cfg.deck)})[/]",
        f"[dim]ankiconnect[/] {escape(cfg.anki_connect_url)}  {anki_status}",
        f"[dim]templates[/]   {escape(str(cfg.templates_dir))}  {tpl_ok}",
    ]
    if cfg.base_tag:
        body_lines.append(f"[dim]base_tag[/]    {escape(cfg.base_tag)}")

    if sys.stdout.isatty():
        console.print(Panel("\n".join(body_lines), title="Configuration", box=box.ROUNDED, expand=False, padding=(0, 2)))
    else:
        for line in body_lines:
            console.print("  " + line)

    if cfg.deck_routing:
        console.print()
        console.print(ui.table(["folder prefix", "target deck"], [[escape(k), escape(v)] for k, v in sorted(cfg.deck_routing.items())]))

    if cfg.tag_aliases:
        console.print()
        console.print(ui.table(["folder", "tag alias"], [[escape(k), escape(v)] for k, v in sorted(cfg.tag_aliases.items())]))

    console.print()
    console.print(
        "  [dim]Quick options:[/] [cyan]--edit[/] [dim](edit in $EDITOR)[/]  [dim]·[/]  "
        "[cyan]--validate[/] [dim](verify config & connection)[/]  [dim]·[/]  "
        "[cyan]--raw[/] [dim](view TOML)[/]  [dim]·[/]  "
        "[cyan]--path[/] [dim](print file path)[/]"
    )
    return 0


def status(
    ctx: typer.Context,
    course: str | None = COURSE_OPTION,
    file: Path | None = FILE_OPTION,
    verbose: bool = VERBOSE_OPTION,
) -> int:
    cfg = load(ctx)
    target_file = resolve_note_file(file, cfg.vault) if file else None
    if target_file and not target_file.is_file():
        ui.error(f"file not found: {file}")
        return 2

    collected = collect(cfg, course, trace_fn=ui.trace)
    if target_file:
        collected.sources = [s for s in collected.sources if s.path.resolve() == target_file]
        collected.cards = [c for c in collected.cards if c.file.resolve() == target_file]
        collected.diagnostics = [d for d in collected.diagnostics if d.file and d.file.resolve() == target_file]
        if not collected.sources and not collected.cards:
            ui.error(f"note file is not part of vault or ignored by configuration: {file}")
            return 2

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

    header_target = rel(target_file, cfg) if target_file else str(cfg.vault)
    ui.header("m2a status", header_target)
    kv_items: list[tuple[str, int]] = [\
        ("notes", len(collected.sources)),\
        ("cards", len(active_cards)),\
        ("pending", len(collected.pending)),\
        ("added", len(collected.added)),\
    ]
    if deleted_cards:
        kv_items.append(("deleted", len(deleted_cards)))
    console.print(INDENT + ui.kv(kv_items))
    console.print()

    rows = [\
        [escape(group), str(total), str(added), f"[green]{pending}[/]" if pending else "[dim]0[/]"]\
        for group, (total, added, pending) in sorted(counts.items())\
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
    updatable_cards = [c for c in active_cards if c.updatable]
    if updatable_cards:
        console.print(
            f"  [dim][INFO] {len(updatable_cards)} already-synced card(s) found in vault. "
            "Run 'm2a sync -u' to push updates if any were modified.[/]"
        )
    if cfg.target == Target.anki.value:
        try:
            client = AnkiConnect(cfg.anki_connect_url)
            if client.reachable():
                res = resolve_completed_occlusions(client, dry_run=True)
                if res.total_checked > 0:
                    if res.completed_notes_count > 0:
                        console.print(
                            f"  [dim][INFO] Image Occlusions in Anki: {res.total_checked} total "
                            f"({res.awaiting_masks_count} awaiting masks, [green]{res.completed_notes_count} ready to unflag[/] with 'm2a sync --unflag-occlusions-only').[/]"
                        )
                    else:
                        console.print(
                            f"  [dim][INFO] Image Occlusions in Anki: {res.total_checked} awaiting masks.[/]"
                        )
        except Exception:
            pass

    return 1 if errors else 0


def check(
    ctx: typer.Context,
    course: str | None = COURSE_OPTION,
    file: Path | None = FILE_OPTION,
    verbose: bool = VERBOSE_OPTION,
) -> int:
    return status(ctx=ctx, course=course, file=file, verbose=verbose)
