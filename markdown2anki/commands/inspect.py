"""``m2a config``, ``m2a check`` and ``m2a status``: read-only inspection and configuration commands."""
from __future__ import annotations

import sys
import typer
from rich import box
from rich.panel import Panel
from rich.syntax import Syntax

try:
    from typer._click import edit as click_edit
except ImportError:
    from click import edit as click_edit

from .. import ui
from ..build import build
from ..config import Config, Target, load_config
from ..export.ankiconnect import AnkiConnect
from ..ui import console, escape
from ..vault import collect
from ._shared import COURSE_OPTION, INDENT, load, print_card_table, print_problems, summary_line


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
) -> int:
    if sum((path, raw, edit)) > 1:
        ui.error("options --path, --raw, and --edit are mutually exclusive")
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

    if cfg.source and cfg.source.is_file():
        console.print()
        for line in cfg.source.read_text(encoding="utf-8").splitlines():
            console.print(f"[dim]{escape(line)}[/]" if line.strip().startswith("#") else escape(line))
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
