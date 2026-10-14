"""Helpers shared by the subcommands: config access through the Typer context and diagnostic output."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Sequence

import typer

from .. import ui
from ..config import Config, load_config
from ..parser import LEVEL_ERROR, LEVEL_INFO, LEVEL_WARNING, Card, Diagnostic
from ..ui import console, escape

INDENT = "  "
COURSE_OPTION = typer.Option(None, "--course", help="Only this course (folder name or tag; glob or substring).")
YES_OPTION = typer.Option(False, "-y", "--yes", help="Do not ask for confirmation.")


@dataclass
class GlobalOptions:
    config: Optional[Path] = None
    vault: Optional[Path] = None


def options(ctx: typer.Context) -> GlobalOptions:
    return ctx.obj or GlobalOptions()


def load(ctx: typer.Context) -> Config:
    opts = options(ctx)
    ui.trace("loading config")
    cfg = load_config(opts.config)
    if opts.vault:
        cfg.vault = opts.vault.expanduser()
    ui.trace(f"config {cfg.source}  vault {cfg.vault}")
    return cfg


def rel(path: Path, cfg: Config) -> str:
    try:
        return str(path.relative_to(cfg.vault))
    except ValueError:
        return str(path)


def short_tag(card: Card) -> str:
    """The tag without the base part, which is the same for every card."""
    return card.tag.split("::", 1)[-1]


def short_question(card: Card, width: int = 60) -> str:
    return card.first_question_line[:width]


def print_diagnostics(diagnostics: Sequence[Diagnostic], cfg: Config, indent: str = INDENT * 2) -> int:
    """Print diagnostics sorted by location; returns the number of errors."""
    errors = 0
    for d in sorted(diagnostics, key=lambda d: (str(d.file), d.line)):
        location = f"{rel(d.file, cfg)}:{d.line}" if d.line else rel(d.file, cfg)
        console.print(f"{indent}{ui.level(d.level)} [cyan]{escape(location)}[/]  {escape(d.message)}")
        errors += d.level == LEVEL_ERROR
    return errors


def summary_line(diagnostics: Sequence[Diagnostic]) -> str:
    errors = sum(d.level == LEVEL_ERROR for d in diagnostics)
    warnings = sum(d.level == LEVEL_WARNING for d in diagnostics)
    if not errors and not warnings:
        return "[green]✓ no problems[/]"
    parts = []
    if errors:
        parts.append(f"[red]{_count(errors, 'error')}[/]")
    if warnings:
        parts.append(f"[yellow]{_count(warnings, 'warning')}[/]")
    return "✗ " + ", ".join(parts)


def print_problems(diagnostics: Sequence[Diagnostic], cfg: Config, include_info: bool = False) -> int:
    """Summary line plus one line per diagnostic; returns the number of errors."""
    problems = [d for d in diagnostics if d.level != LEVEL_INFO]
    console.print(INDENT + summary_line(problems))
    errors = print_diagnostics(problems, cfg)
    if include_info:
        print_diagnostics([d for d in diagnostics if d.level == LEVEL_INFO], cfg)
    return errors


def print_card_table(cards: Sequence[Card], state: Callable[[Card], str], state_header: str = "state") -> None:
    rows = [[state(card), escape(f"{card.file.name}:{card.line}"), escape(short_tag(card)),
             escape(short_question(card))] for card in cards]
    console.print(ui.table([state_header, "where", "tag", "question"], rows))


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}{'s' if n != 1 else ''}"
