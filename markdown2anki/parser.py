"""Markdown note parser.

Format (see README): cards are separated by a line of ``---``; the first line after it is the question
(``EQL: `` lines continue it), everything else is the answer. Headings become tags. A question that is
exactly ``Cloze`` makes a cloze card, ``Image Cloze`` an image-occlusion export.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .constants import CODE_KEYWORDS
from .ids import parse_added

KIND_BASIC = "basic"
KIND_CLOZE = "cloze"
KIND_IMAGE_OCCLUSION = "image_occlusion"

LEVEL_INFO = "info"
LEVEL_WARNING = "warning"
LEVEL_ERROR = "error"

EQL_PREFIX = "EQL: "
HEADING_RE = re.compile(r"^(#+)\s*(.*?)\s*$")
FENCE_RE = re.compile(r"^\s*```")
FENCED_CODE_BLOCK_RE = re.compile(r"^[ \t]*```[^\n]*\n.*?^[ \t]*```[ \t]*$", re.MULTILINE | re.DOTALL)
CLOZE_MARKER_RE = re.compile(r"\{\{c\d+::")
YAML_LINE_RE = re.compile(r"^([a-zA-Z0-9_-]+\s*:|\s*-\s+|\s+[^\n]*|\s*#|\s*$)")


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
    card_id: str | None = None
    has_code: bool = False
    has_cloze_markers: bool = False
    deck: str | None = None

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


def parse_file(
    path: Path,
    base_tag: str = "",
    diagnostics: list[Diagnostic] | None = None,
    file_tag: str | None = None,
    deck: str | None = None,
) -> list[Card]:
    with open(path, "r", encoding="utf-8", newline="") as f:
        text = f.read()
    newline = "\r\n" if "\r\n" in text else "\n"
    return parse_lines(text.split(newline), path, base_tag, file_tag=file_tag, diagnostics=diagnostics, deck=deck)


def _find_frontmatter_end(lines: list[str]) -> int:
    """Return the 1-based line number of the closing '---' of YAML frontmatter, or 0 if none."""
    if not lines or lines[0].strip() != "---":
        return 0
    has_key_value = False
    for i in range(1, len(lines)):
        line = lines[i]
        if line.strip() in ("---", "..."):
            return i + 1 if has_key_value else 0
        if not YAML_LINE_RE.match(line):
            return 0
        if re.match(r"^[a-zA-Z0-9_-]+\s*:", line):
            has_key_value = True
    return 0


def parse_lines(lines: list[str], file: Path, base_tag: str, file_tag: str | None = None,
                diagnostics: list[Diagnostic] | None = None, deck: str | None = None) -> list[Card]:
    """Parse the lines of one note. ``base_tag`` is the tag hierarchy above the file (may be empty)."""
    diagnostics = diagnostics if diagnostics is not None else []
    tags: list[str] = [t for t in [base_tag, file_tag or file.stem] if t]
    fixed_levels = len(tags)  # tags that headings must never pop

    cards: list[Card] = []
    expecting_question = False
    in_code_block = False
    question_line = 0
    question: str | None = None
    added = False
    card_id: str | None = None
    answer_lines: list[str] = []
    orphan_lines: list[tuple[int, str]] = []  # (line number, text) outside any card

    def flush() -> None:
        nonlocal question, answer_lines, orphan_lines, added, card_id
        if question is not None:
            cards.append(_make_card(file, question_line, question, "\n".join(answer_lines), merge_tags(tags),
                                    added, card_id, diagnostics, deck=deck))
        elif any(text.strip() for _, text in orphan_lines):
            first = next(number for number, text in orphan_lines if text.strip())
            diagnostics.append(Diagnostic(file, first, LEVEL_ERROR, "text outside a card (no question line after '---')"))
        question, answer_lines, orphan_lines, added, card_id = None, [], [], False, None

    frontmatter_end = _find_frontmatter_end(lines)

    for index, line in enumerate(lines, start=1):
        if index <= frontmatter_end:
            continue

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


# --- internal helpers -----------------------------------------------------------------------------


def tags_after_heading(depth: int, heading: str, tags: list[str], fixed_levels: int) -> list[str]:
    """Heading at depth ``d`` keeps fixed tags plus ``d - 1`` ancestors, then appends the heading."""
    return tags[:fixed_levels + depth - 1] + [heading]


def merge_tags(tags: list[str]) -> str:
    """``["SUTD", "50.054", "W01"]`` -> ``SUTD::50.054::W01``, zero-padding single-digit chapter numbers."""
    parts = []
    for tag in tags:
        if not tag:
            continue
        if tag[0].isdigit() and tag[0] != "0" and (len(tag) == 1 or not tag[1].isdigit()):
            tag = "0" + tag
        parts.append(tag.replace(". ", "_").replace(" ", "_"))
    return "::".join(parts)


def _make_card(file: Path, line: int, question: str, answer: str, tag: str, added: bool,
               card_id: str | None, diagnostics: list[Diagnostic], deck: str | None = None) -> Card:
    answer = _strip_trailing_blank_lines(answer)
    key = question.strip().lower()
    if key == "cloze":
        kind = KIND_CLOZE
    elif key in ("image cloze", "cloze image"):
        kind = KIND_IMAGE_OCCLUSION
    else:
        kind = KIND_BASIC

    has_code_block = bool(FENCED_CODE_BLOCK_RE.search(question) or FENCED_CODE_BLOCK_RE.search(answer))
    has_code = has_code_block or any(kw in question or kw in answer for kw in CODE_KEYWORDS)
    has_markers = bool(CLOZE_MARKER_RE.search(answer))

    if kind == KIND_BASIC and has_markers:
        diagnostics.append(Diagnostic(file, line, LEVEL_WARNING,
                                      "cloze markers {{c1::...}} in a basic card; use 'Cloze' as the question"))
    if kind == KIND_IMAGE_OCCLUSION and "![[" not in answer:
        diagnostics.append(Diagnostic(file, line, LEVEL_ERROR, "image cloze without an image"))
    if kind == KIND_BASIC and not answer.strip():
        diagnostics.append(Diagnostic(file, line, LEVEL_WARNING, "card has an empty answer"))

    return Card(file=file, line=line, question=question, answer=answer, tag=tag, kind=kind, added=added,
                card_id=card_id, has_code=has_code, has_cloze_markers=has_markers, deck=deck)


def _strip_trailing_blank_lines(text: str) -> str:
    lines = text.split("\n")
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)
