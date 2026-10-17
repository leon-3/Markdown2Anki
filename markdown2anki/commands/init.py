"""``m2a init``: interactive wizard that creates a commented m2a.toml."""
from __future__ import annotations

import shutil
from pathlib import Path

import typer

from .. import ui
from ..config import (
    CONFIG_FILE_NAME,
    Config,
    Target,
    TARGETS,
    config_from_env,
    render_toml,
    user_config_path,
)
from ..export.ankiconnect import AnkiConnect
from ..ui import console, escape
from ._shared import options

LEGACY_ENV = Path(".env")


def run(
    ctx: typer.Context,
    vault: Path | None = typer.Option(None, "--vault", help="Obsidian vault folder."),
    deck: str | None = typer.Option(None, "--deck", help="Anki deck name (use :: for subdecks)."),
    base_tag: str | None = typer.Option(None, "--base-tag", help="Tag prepended to every card."),
    target: Target | None = typer.Option(None, "--target", help="Default export target."),
    output_dir: Path | None = typer.Option(None, "--output-dir", help="Where .apkg files are written."),
    here: bool = typer.Option(False, "--here", help=f"Write ./{CONFIG_FILE_NAME} instead of the user config "
                                                     f"{user_config_path()}."),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing config (keeps a .bak copy)."),
    yes: bool = typer.Option(False, "-y", "--yes", help="No questions; use options, a legacy .env, and defaults."),
) -> int:
    interactive = ui.interactive() and not yes
    ui.header("m2a init")

    seed = _seed()
    target_path = _target_path(options(ctx).config, here)
    if target_path.exists() and not force:
        ui.error(f"a config already exists: {target_path}",
                 "edit it, or re-run with --force to replace it (a .bak copy is kept)")
        return 1

    vault = _ask_vault(vault or options(ctx).vault or (seed.vault if seed.source else None), interactive)
    if vault is None:
        return 2

    cfg = Config(
        vault=vault.resolve(),
        deck=deck or seed.deck,
        base_tag=seed.base_tag if base_tag is None else base_tag,
        output_dir=output_dir or _default_output_dir(here),
        target=target.value if target else seed.target,
        ignore=seed.ignore,
        deck_routing=dict(seed.deck_routing),
        tag_aliases=dict(seed.tag_aliases),
    )
    if interactive:
        _ask_anki(cfg)
    _check_ankiconnect(cfg)

    _write(cfg, target_path, force, migrated=seed.source is not None)
    return 0


# --- steps ----------------------------------------------------------------------------------------


def _seed() -> Config:
    if LEGACY_ENV.is_file():
        console.print(f"  [dim]migrating[/] {escape(str(LEGACY_ENV.resolve()))}")
        return config_from_env(LEGACY_ENV)
    return Config(vault=Path("."))


def _target_path(explicit: Path | None, here: bool) -> Path:
    if explicit:
        return explicit
    return Path(CONFIG_FILE_NAME) if here else user_config_path()


def _default_output_dir(here: bool) -> Path:
    return Path("output") if here else Path("~/Downloads/Markdown2Anki")


def _section(title: str, interactive: bool) -> None:
    if interactive:
        console.print()
        console.print(f"  [dim]{title}[/]")


def _ask_vault(preset: Path | None, interactive: bool) -> Path | None:
    _section("Vault", interactive)
    default = str(preset) if preset else ""
    while True:
        answer = ui.ask_path("Obsidian vault folder", default) if interactive else default
        if not answer:
            ui.error("tell me where the vault is: m2a init --vault ~/Documents/obsidian")
            return None
        vault = Path(answer).expanduser()
        if vault.is_dir():
            return vault
        ui.error(f"vault directory not found: {vault}")
        if not interactive:
            return None


def _ask_anki(cfg: Config) -> None:
    _section("Anki", True)
    cfg.deck = ui.ask_text("Deck (use :: for subdecks)", cfg.deck)
    cfg.package_name = cfg.deck.replace("::", "-")
    cfg.base_tag = ui.ask_text("Tag prepended to every card (empty for none)", cfg.base_tag, allow_empty=True)
    cfg.target = ui.ask_select("Export target: push into a running Anki (anki) or write a file (apkg)?",
                               TARGETS, cfg.target)
    cfg.cloze_notes = ui.ask_confirm("Export 'Cloze' cards with {{c1::...}} markers as real cloze notes?",
                                     cfg.cloze_notes)
    cfg.output_dir = Path(ui.ask_path("Folder for .apkg files and image-occlusion sources", str(cfg.output_dir)))


def _check_ankiconnect(cfg: Config) -> None:
    if cfg.target != Target.anki.value:
        return
    if AnkiConnect(cfg.anki_connect_url).reachable():
        console.print(f"  [green]✓[/] AnkiConnect reachable at {escape(cfg.anki_connect_url)}")
    else:
        console.print(f"  [yellow]![/] AnkiConnect not reachable at {escape(cfg.anki_connect_url)} - install the "
                      f"add-on (code 2055492159) and keep Anki open, or use `m2a sync --target apkg`")


def _write(cfg: Config, target_path: Path, force: bool, migrated: bool) -> None:
    if target_path.exists() and force:
        backup = target_path.with_suffix(".toml.bak")
        shutil.copy2(target_path, backup)
        console.print(f"  [dim]backup[/] {escape(str(backup))}")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(render_toml(cfg), encoding="utf-8")

    console.print()
    console.print(f"[green]✓[/] wrote [bold]{escape(str(target_path))}[/]"
                  + ("  [dim](migrated from .env)[/]" if migrated else ""))
    console.print(f"  [dim]vault[/]    {escape(str(cfg.vault))}")
    console.print(f"  [dim]deck[/]     {escape(cfg.deck)}")
    console.print(f"  [dim]target[/]   {cfg.target}")
    console.print()
    console.print("next:")
    console.print("  [cyan]m2a check[/]           see problems before exporting")
    console.print("  [cyan]m2a status[/]          counts per course")
    console.print("  [cyan]m2a sync --dry-run[/]  preview the first export")
