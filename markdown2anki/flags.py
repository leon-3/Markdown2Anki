"""Write ``ADDED[id]:`` prefixes back into notes after a successful export."""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple

from .ids import flagged_line, parse_added
from .parser import Card


def clear_flags(cards: List[Card]) -> Tuple[int, List[str]]:
    """Remove the ADDED prefix from ``cards`` so they are exported again as new cards."""
    by_file: Dict[Path, List[Card]] = {}
    for card in cards:
        by_file.setdefault(card.file, []).append(card)

    cleared = 0
    problems: List[str] = []
    for path, entries in by_file.items():
        lines = path.read_text(encoding="utf-8").split("\n")
        changed = False
        for card in entries:
            index = card.line - 1
            if index >= len(lines):
                problems.append(f"{card.location}: line no longer exists, not changed")
                continue
            added, _, question = parse_added(lines[index])
            if not added or question != card.first_question_line:
                problems.append(f"{card.location}: line changed since parsing, not changed")
                continue
            lines[index] = question
            changed = True
            cleared += 1
        if changed:
            path.write_text("\n".join(lines), encoding="utf-8")
    return cleared, problems


def write_flags(cards: List[Tuple[Card, str]]) -> Tuple[int, List[str]]:
    """Mark ``cards`` (paired with their new id) as added, grouped per file.

    Each line is checked against the parsed question before it is touched, so a note edited between
    parsing and flagging is reported instead of corrupted. Returns (flagged, problems).
    """
    by_file: Dict[Path, List[Tuple[Card, str]]] = {}
    for card, card_id in cards:
        by_file.setdefault(card.file, []).append((card, card_id))

    flagged = 0
    problems: List[str] = []
    for path, entries in by_file.items():
        text = path.read_text(encoding="utf-8")
        lines = text.split("\n")
        changed = False
        for card, card_id in entries:
            index = card.line - 1
            if index >= len(lines):
                problems.append(f"{card.location}: line no longer exists, not flagged")
                continue
            _, existing_id, question = parse_added(lines[index])
            if question != card.first_question_line:
                problems.append(f"{card.location}: question changed since parsing, not flagged")
                continue
            if existing_id == card_id:
                continue
            lines[index] = flagged_line(question, card_id)
            changed = True
            flagged += 1
        if changed:
            path.write_text("\n".join(lines), encoding="utf-8")
    return flagged, problems
