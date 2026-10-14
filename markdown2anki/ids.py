"""Card identity: how an exported card is marked in the note, and how it is found again in Anki.

A flagged question line looks like

    ADDED: What is a token? %%k3f9qz%%

``ADDED: `` is the human-readable part (and what older versions wrote); the trailing ``%%id%%`` is an
Obsidian comment - hidden in reading view, dimmed in live preview - holding a short id. The id becomes the
Anki GUID for .apkg exports and is embedded in the note's back field as ``<!--m2a:id-->`` so AnkiConnect can
find the note again for updates.

Older forms are still understood: ``ADDED[7f3a9c2e]: q`` (hex id) and ``ADDED[n1694…]: q`` (Anki note id).
"""
from __future__ import annotations

import re
import secrets
import string
from typing import Optional, Tuple

_ALPHABET = string.digits + string.ascii_lowercase
ID_LENGTH = 6

ADDED_PREFIX_RE = re.compile(r"^ADDED(?:\[(?P<bracket_id>[0-9a-f]{8}|n\d+)\])?: ")
TRAILING_ID_RE = re.compile(r"\s*%%(?P<id>[0-9a-z]{4,12})%%\s*$")
MARKER_RE = re.compile(r"\s*<!--m2a:[0-9a-z]+-->")


def parse_added(line: str) -> Tuple[bool, Optional[str], str]:
    """Return (is_added, card_id, question_text_without_markers)."""
    match = ADDED_PREFIX_RE.match(line)
    if not match:
        return False, None, line
    rest = line[match.end():]
    card_id = match.group("bracket_id")
    trailing = TRAILING_ID_RE.search(rest)
    if trailing:
        card_id = trailing.group("id")
        rest = rest[:trailing.start()]
    return True, card_id, rest


def new_card_id() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(ID_LENGTH))


def flagged_line(question: str, card_id: str) -> str:
    return f"ADDED: {question} %%{card_id}%%"


def is_anki_note_id(card_id: Optional[str]) -> bool:
    return bool(card_id) and card_id.startswith("n") and card_id[1:].isdigit()


def anki_note_id(card_id: str) -> int:
    return int(card_id[1:])


def marker(card_id: str) -> str:
    """Invisible HTML comment embedded in the Anki note so it can be found by id."""
    return f"<!--m2a:{card_id}-->"


def with_marker(field_html: str, card_id: str) -> str:
    return MARKER_RE.sub("", field_html) + marker(card_id)


def search_query(field: str, card_id: str) -> str:
    """Anki search that finds the note carrying ``marker(card_id)`` in ``field``."""
    return f'"{field.lower()}:*m2a:{card_id}-->*"'
