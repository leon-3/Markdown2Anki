"""Terminal output (Rich) and prompts (questionary).

Everything a command prints goes through ``console``; user-supplied text is passed through ``escape`` so
brackets in questions are never read as markup. Prompts are only shown on a terminal; ``interactive()``
tells the caller whether to ask or to fall back to defaults.
"""
from __future__ import annotations

import os
import sys
import time
from typing import List, Optional, Sequence

import questionary
from rich import box
from rich.console import Console
from rich.markup import escape
from rich.padding import Padding
from rich.table import Table

__all__ = ["console", "escape", "error", "trace", "enable_trace", "header", "kv", "level", "table", "interactive",
           "ask_text", "ask_path", "ask_checkbox", "ask_select", "ask_confirm", "confirm"]

console = Console(highlight=False, soft_wrap=True, width=None if sys.stdout.isatty() else 160)
stderr = Console(stderr=True, highlight=False, soft_wrap=True)

_trace_enabled = bool(os.environ.get("M2A_TRACE"))
_trace_start: Optional[float] = None


# --- output ---------------------------------------------------------------------------------------


def error(message: str, hint: Optional[str] = None) -> None:
    stderr.print(f"[red]error[/] {escape(message)}")
    if hint:
        stderr.print(f"[dim]hint[/]  {escape(hint)}")


def enable_trace() -> None:
    global _trace_enabled
    _trace_enabled = True


def trace(message: str) -> None:
    """Phase log on stderr with ``--trace`` or ``M2A_TRACE=1``, for finding where a run stalls."""
    global _trace_start
    if not _trace_enabled:
        return
    if _trace_start is None:
        _trace_start = time.monotonic()
    stderr.print(f"[m2a +{time.monotonic() - _trace_start:6.2f}s] {escape(message)}", markup=False)


def header(title: str, detail: str = "") -> None:
    console.print(f"[bold]{escape(title)}[/]" + (f"  [dim]{escape(detail)}[/]" if detail else ""))


def kv(pairs: Sequence[tuple]) -> str:
    """``notes 2 · cards 9`` with the values emphasised (markup)."""
    return "[dim] · [/]".join(f"[dim]{escape(str(k))}[/] [bold]{escape(str(v))}[/]" for k, v in pairs)


def level(name: str) -> str:
    """Coloured, fixed-width diagnostic level (markup)."""
    colour = {"error": "red", "warning": "yellow", "info": "dim"}.get(name)
    text = f"{name:7}"
    return f"[{colour}]{text}[/]" if colour else text


def table(headers: Sequence[str], rows: Sequence[Sequence[str]], align_right: Sequence[int] = ()) -> Padding:
    """Indented table; cells are markup strings, the last column is cut with an ellipsis when too long."""
    t = Table(box=box.SIMPLE_HEAD, show_edge=False, pad_edge=False, padding=(0, 2, 0, 0), header_style="bold")
    for i, name in enumerate(headers):
        last = i == len(headers) - 1
        t.add_column(name, justify="right" if i in align_right else "left", no_wrap=True,
                     overflow="ellipsis" if last else "fold")
    for row in rows:
        t.add_row(*row)
    return Padding(t, (0, 0, 0, 2), expand=False)


# --- prompts --------------------------------------------------------------------------------------


def interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _required(value: str):
    return bool(value.strip()) or "a value is required"


def ask_text(question: str, default: str = "", allow_empty: bool = False) -> str:
    return questionary.text(question, default=default,
                            validate=None if allow_empty else _required).unsafe_ask().strip()


def ask_path(question: str, default: str = "") -> str:
    return questionary.path(question, default=default, validate=_required).unsafe_ask().strip()


def ask_checkbox(question: str, choices: Sequence[str], checked: Sequence[str],
                 labels: Optional[Sequence[str]] = None) -> List[str]:
    """Multi-select; returns the chosen ``choices`` (``labels`` are what is displayed)."""
    items = [questionary.Choice(label, value=value, checked=value in checked)
             for value, label in zip(choices, labels or choices)]
    return questionary.checkbox(question, choices=items, validate=lambda picked: bool(picked) or "pick at least one",
                                instruction="(space selects, enter confirms)").unsafe_ask()


def ask_select(question: str, choices: Sequence[str], default: str) -> str:
    return questionary.select(question, choices=list(choices), default=default).unsafe_ask()


def ask_confirm(question: str, default: bool) -> bool:
    return questionary.confirm(question, default=default).unsafe_ask()


def confirm(question: str) -> bool:
    """Yes/no gate before a write; defaults to no and is False without a terminal."""
    if not interactive():
        return False
    console.print()
    return ask_confirm(question, default=False)
