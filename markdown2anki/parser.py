"""Parse a markdown note into cards.

Format (see README): cards are separated by a line of ``---``; the first line after it is the question
(``EQL: `` lines continue it), everything else is the answer. Headings become tags. A question that is
exactly ``Cloze`` makes a cloze card, ``Image Cloze`` an image-occlusion export.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from .constants import CODE_KEYWORDS
from .ids import parse_added

HEADING_RE = re.compile(r"^(#+)\s+(.*)$")
CLOZE_MARKER_RE = re.compile(r"\{\{c\d+::")
FENCE_RE = re.compile(r"^\s*```")
EQL_PREFIX = "EQL: "

KIND_BASIC = "basic"
KIND_CLOZE = "cloze"
KIND_IMAGE_OCCLUSION = "image_occlusion"

LEVEL_ERROR = "error"
LEVEL_WARNING = "warning"
LEVEL_INFO = "info"


@dataclass
class Diagnostic:
    file: Path
    line: int  # 1-based; 0 when the whole file or folder is meant
    level: str  # LEVEL_ERROR | LEVEL_WARNING | LEVEL_INFO
    message: str


@dataclass
class Card:
    file: Path
    line: int  # 1-based line number of the question
    question: str  # raw markdown; EQL lines joined with "\n"
    answer: str  # raw markdown
    tag: str  # merged hierarchical tag, e.g. SUTD::50.054_Compiler::Lectures::W01_Intro::Parsing
    kind: str = KIND_BASIC
    added: bool = False
    card_id: Optional[str] = None
    has_code: bool = False
    has_cloze_markers: bool = False

    @property
    def pending(self) -> bool:
        return not self.added

    @property
    def updatable(self) -> bool:
        """Already exported with an id, so it can be pushed again as an update."""
        return self.added and self.card_id is not None

    @property
    def location(self) -> str:
        return f"{self.file}:{self.line}"

    @property
    def first_question_line(self) -> str:
        return self.question.split("\n", 1)[0]


def parse_file(path: Path, base_tag: str, diagnostics: List[Diagnostic]) -> List[Card]:
    text = path.read_text(encoding="utf-8")
    return parse_lines(text.split("\n"), path, base_tag, diagnostics=diagnostics)


def parse_lines(lines: List[str], file: Path, base_tag: str, file_tag: Optional[str] = None,
                diagnostics: Optional[List[Diagnostic]] = None) -> List[Card]:
    """Parse the lines of one note. ``base_tag`` is the tag hierarchy above the file (may be empty)."""
    diagnostics = diagnostics if diagnostics is not None else []
    tags: List[str] = [t for t in [base_tag, file_tag or file.stem] if t]
    fixed_levels = len(tags)  # tags that headings must never pop

    cards: List[Card] = []
    expecting_question = False
    in_code_block = False
    question_line = 0
    question: Optional[str] = None
    added = False
    card_id: Optional[str] = None
    answer_lines: List[str] = []
    orphan_lines: List[Tuple[int, str]] = []  # (line number, text) outside any card

    def flush() -> None:
        nonlocal question, answer_lines, orphan_lines, added, card_id
        if question is not None:
            cards.append(_make_card(file, question_line, question, "\n".join(answer_lines), merge_tags(tags),
                                    added, card_id, diagnostics))
        elif any(text.strip() for _, text in orphan_lines):
            first = next(number for number, text in orphan_lines if text.strip())
            diagnostics.append(Diagnostic(file, first, LEVEL_ERROR, "text outside a card (no question line after '---')"))
        question, answer_lines, orphan_lines, added, card_id = None, [], [], False, None

    for index, line in enumerate(lines, start=1):
        if FENCE_RE.match(line):
            in_code_block = not in_code_block

        heading = HEADING_RE.match(line) if not in_code_block else None
        if heading:
            flush()
            expecting_question = False
            depth, text = len(heading.group(1)), heading.group(2).strip()
            tags = tags_after_heading(depth, text, tags, fixed_levels)
        elif line.startswith("---") and not in_code_block:
            flush()
            expecting_question = True
        elif expecting_question:
            expecting_question = False
            if not line.strip():
                # A blank line right after --- is an empty template slot, not a card. Anything that
                # follows before the next separator is an answer without a question.
                orphan_lines.append((index, line))
                continue
            added, card_id, question = parse_added(line)
            question_line = index
        elif line.startswith(EQL_PREFIX) and question is not None:
            question += "\n" + line[len(EQL_PREFIX):]
        elif question is not None:
            answer_lines.append(line)
        else:
            orphan_lines.append((index, line))

    flush()
    return cards


def tags_after_heading(depth: int, text: str, tags: List[str], fixed_levels: int) -> List[str]:
    """A heading of ``depth`` (# = 1) replaces every heading tag at that depth or deeper."""
    keep = fixed_levels + depth - 1
    return [*tags[:keep], text]


def merge_tags(tags: List[str]) -> str:
    """Join tag parts with ``::``. Spaces become underscores and a leading single digit is zero-padded
    (``9 Foo`` -> ``09_Foo``) so tags sort naturally in Anki."""
    parts = []
    for tag in tags:
        if not tag:
            continue
        if tag[0].isdigit() and tag[0] != "0" and (len(tag) == 1 or not tag[1].isdigit()):
            tag = "0" + tag
        parts.append(tag.replace(". ", "_").replace(" ", "_"))
    return "::".join(parts)


def _make_card(file: Path, line: int, question: str, answer: str, tag: str, added: bool,
               card_id: Optional[str], diagnostics: List[Diagnostic]) -> Card:
    answer = _strip_trailing_blank_lines(answer)
    key = question.strip().lower()
    if key == "cloze":
        kind = KIND_CLOZE
    elif key in ("image cloze", "cloze image"):
        kind = KIND_IMAGE_OCCLUSION
    else:
        kind = KIND_BASIC

    has_code = any(kw in question or kw in answer for kw in CODE_KEYWORDS)
    has_markers = bool(CLOZE_MARKER_RE.search(answer))

    if kind == KIND_BASIC and has_markers:
        diagnostics.append(Diagnostic(file, line, LEVEL_WARNING,
                                      "cloze markers {{c1::...}} in a basic card; use 'Cloze' as the question"))
    if kind == KIND_IMAGE_OCCLUSION and "![[" not in answer:
        diagnostics.append(Diagnostic(file, line, LEVEL_ERROR, "image cloze without an image"))
    if kind == KIND_BASIC and not answer.strip():
        diagnostics.append(Diagnostic(file, line, LEVEL_WARNING, "card has an empty answer"))

    return Card(file=file, line=line, question=question, answer=answer, tag=tag, kind=kind, added=added,
                card_id=card_id, has_code=has_code, has_cloze_markers=has_markers)


def _strip_trailing_blank_lines(text: str) -> str:
    lines = text.split("\n")
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)
