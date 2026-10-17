"""Write ``ADDED[id]:`` prefixes back into notes after a successful export."""
from __future__ import annotations

from pathlib import Path

from .ids import flagged_deleted_line, flagged_line, parse_added, parse_card_prefix
from .parser import Card


def clear_flags(cards: list[Card]) -> tuple[int, list[str]]:
    """Remove the ADDED prefix from ``cards`` so they are exported again as new cards."""
    by_file: dict[Path, list[Card]] = {}
    for card in cards:
        by_file.setdefault(card.file, []).append(card)

    cleared = 0
    problems: list[str] = []
    for path, entries in by_file.items():
        with open(path, "r", encoding="utf-8", newline="") as f:
            text = f.read()
        newline = "\r\n" if "\r\n" in text else "\n"
        lines = text.split(newline)
        changed = False
        for card in entries:
            index = card.line - 1
            if index >= len(lines):
                problems.append(f"{card.location}: line no longer exists, not changed")
                continue
            is_added, is_deleted, _, question = parse_card_prefix(lines[index])
            if (not is_added and not is_deleted) or question != card.first_question_line:
                problems.append(f"{card.location}: line changed since parsing, not changed")
                continue
            lines[index] = question
            changed = True
            cleared += 1
        if changed:
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(newline.join(lines))
    return cleared, problems


def write_flags(cards: list[tuple[Card, str]]) -> tuple[int, list[str]]:
    """Mark ``cards`` (paired with their new id) as added, grouped per file.

    Each line is checked against the parsed question before it is touched, so a note edited between
    parsing and flagging is reported instead of corrupted. Returns (flagged, problems).
    """
    by_file: dict[Path, list[tuple[Card, str]]] = {}
    for card, card_id in cards:
        by_file.setdefault(card.file, []).append((card, card_id))

    flagged = 0
    problems: list[str] = []
    for path, entries in by_file.items():
        with open(path, "r", encoding="utf-8", newline="") as f:
            text = f.read()
        newline = "\r\n" if "\r\n" in text else "\n"
        lines = text.split(newline)
        changed = False
        for card, card_id in entries:
            index = card.line - 1
            if index >= len(lines):
                problems.append(f"{card.location}: line no longer exists, not flagged")
                continue
            is_added, is_deleted, existing_id, question = parse_card_prefix(lines[index])
            if question != card.first_question_line:
                problems.append(f"{card.location}: question changed since parsing, not flagged")
                continue
            if is_added and existing_id == card_id:
                continue
            lines[index] = flagged_line(question, card_id)
            changed = True
            flagged += 1
        if changed:
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(newline.join(lines))
    return flagged, problems


def write_deleted_flags(cards: list[Card]) -> tuple[int, list[str]]:
    """Mark cards as deleted by prefixing the question line with 'DELETED: ' and keeping their id.

    Returns (flagged_count, problems).
    """
    by_file: dict[Path, list[Card]] = {}
    for card in cards:
        by_file.setdefault(card.file, []).append(card)

    flagged = 0
    problems: list[str] = []
    for path, entries in by_file.items():
        with open(path, "r", encoding="utf-8", newline="") as f:
            text = f.read()
        newline = "\r\n" if "\r\n" in text else "\n"
        lines = text.split(newline)
        changed = False
        for card in entries:
            index = card.line - 1
            if index >= len(lines):
                problems.append(f"{card.location}: line no longer exists, not marked deleted")
                continue
            is_added, is_deleted, existing_id, question = parse_card_prefix(lines[index])
            if question != card.first_question_line:
                problems.append(f"{card.location}: question changed since parsing, not marked deleted")
                continue
            cid = existing_id or card.card_id or ""
            new_line = flagged_deleted_line(question, cid) if cid else f"DELETED: {question}"
            if lines[index] == new_line:
                continue
            lines[index] = new_line
            changed = True
            flagged += 1
        if changed:
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(newline.join(lines))
    return flagged, problems
