"""``m2a init``: an interactive walk through the configuration, written to m2a.toml.

Every answer is pre-filled from the command line options, from a pre-CLI ``.env`` in the current
directory (migration), or from what a scan of the vault suggests. With ``--yes`` or without a terminal
the pre-filled values are used as they are.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import typer

from .. import ui
from ..config import (CONFIG_FILE_NAME, TARGETS, Config, Target, config_from_env, render_toml, sanitize_tag,
                      user_config_path)
from ..export.ankiconnect import AnkiConnect
from ..ui import console, escape
from ._shared import options

LEGACY_ENV = Path(".env")
SUBDIR_PREFIX = "Anki - "


def run(
    ctx: typer.Context,
    vault: Optional[Path] = typer.Option(None, "--vault", help="Obsidian vault folder."),
    deck: Optional[str] = typer.Option(None, "--deck", help="Anki deck name (use :: for subdecks)."),
    base_tag: Optional[str] = typer.Option(None, "--base-tag", help="Tag prepended to every card."),
    target: Optional[Target] = typer.Option(None, "--target", help="Default export target."),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir", help="Where .apkg files are written."),
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
    courses = _course_folders(vault, seed.ignore)
    if not courses:
        ui.error(f"no course folders in {vault}", "expected <vault>/<course>/Anki - Lectures/*.md")
        return 2

    cfg = Config(vault=vault.resolve(), deck=deck or seed.deck, base_tag=seed.base_tag if base_tag is None else base_tag,
                 output_dir=output_dir or _default_output_dir(here), target=target.value if target else seed.target,
                 ignore=seed.ignore, subdirectories=seed.subdirectories)
    cfg.subjects = _ask_subjects(courses, seed.subjects, interactive)
    cfg.subdirectories = _ask_subdirectories(vault, cfg.subjects, seed.subdirectories, interactive)
    cfg.display = {tag: folder for folder, tag in cfg.subjects.items()}
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


def _target_path(explicit: Optional[Path], here: bool) -> Path:
    if explicit:
        return explicit
    return Path(CONFIG_FILE_NAME) if here else user_config_path()


def _default_output_dir(here: bool) -> Path:
    return Path("output") if here else Path("~/Downloads/Markdown2Anki")


def _section(title: str, interactive: bool) -> None:
    if interactive:
        console.print()
        console.print(f"  [dim]{title}[/]")


def _ask_vault(preset: Optional[Path], interactive: bool) -> Optional[Path]:
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


def _course_folders(vault: Path, ignore: Sequence[str]) -> List[str]:
    return sorted(p.name for p in vault.iterdir() if p.is_dir() and not p.name.startswith(".") and p.name not in ignore)


def _ask_subjects(courses: List[str], seed: Dict[str, str], interactive: bool) -> Dict[str, str]:
    """Which top-level folders are courses, and the tag each one gets."""
    _section("Courses (top-level folders of the vault)", interactive)
    chosen = [c for c in courses if c in seed] or courses
    if interactive:
        chosen = ui.ask_checkbox("Which folders are courses?", courses, checked=chosen)
    return {folder: _ask_tag(folder, seed.get(folder) or _suggest_course_tag(folder), interactive) for folder in chosen}


def _ask_subdirectories(vault: Path, subjects: Dict[str, str], seed: Dict[str, str],
                        interactive: bool) -> Dict[str, str]:
    """Which folders inside the courses hold notes, and the tag each one gets."""
    _section("Note folders (inside each course)", interactive)
    found: Dict[str, int] = {}
    for course in subjects:
        for sub in (vault / course).iterdir():
            if sub.is_dir() and not sub.name.startswith("."):
                found[sub.name] = found.get(sub.name, 0) + len(list(sub.glob("*.md")))
    names = sorted(found)
    if not names:
        console.print("  [dim]no subfolders found yet; keeping the defaults[/]")
        return dict(seed)

    chosen = [n for n in names if n in seed] or [n for n in names if found[n]] or names
    if interactive:
        labels = [f"{name}  ({found[name]} notes)" for name in names]
        chosen = ui.ask_checkbox("Which folders hold flashcard notes?", names, checked=chosen, labels=labels)
    return {name: _ask_tag(name, seed.get(name) or _suggest_subdirectory_tag(name), interactive) for name in chosen}


def _ask_tag(folder: str, suggestion: str, interactive: bool) -> str:
    return ui.ask_text(f"Tag for '{folder}'", suggestion) if interactive else suggestion


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
    console.print(f"  [dim]courses[/]  {escape(', '.join(cfg.subjects.values()))}")
    console.print(f"  [dim]deck[/]     {escape(cfg.deck)}")
    console.print(f"  [dim]target[/]   {cfg.target}")
    console.print()
    console.print("next:")
    console.print("  [cyan]m2a check[/]           see problems before exporting")
    console.print("  [cyan]m2a status[/]          counts per course")
    console.print("  [cyan]m2a sync --dry-run[/]  preview the first export")


# --- helpers --------------------------------------------------------------------------------------


def _suggest_course_tag(folder: str) -> str:
    """``50.054 Compiler Design and Program Analysis`` -> ``50.054_Compiler``: course code plus first word."""
    words = folder.split()
    if len(words) >= 2 and any(ch.isdigit() for ch in words[0]):
        return sanitize_tag(f"{words[0]} {words[1]}")
    return sanitize_tag(folder)


def _suggest_subdirectory_tag(name: str) -> str:
    """``Anki - Lectures`` -> ``Lectures``."""
    return sanitize_tag(name[len(SUBDIR_PREFIX):] if name.startswith(SUBDIR_PREFIX) else name)
