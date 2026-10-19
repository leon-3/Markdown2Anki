"""Fast line-based parser that extracts cards from Markdown files.

No Markdown AST is built here; that happens in render.py on the extracted cards.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .diagnostics import Diagnostic, DiagnosticCategory, DiagnosticLevel
from .ids import MARKER_RE, parse_added, parse_card_prefix

LEVEL_INFO = DiagnosticLevel.INFO
LEVEL_WARNING = DiagnosticLevel.WARNING
LEVEL_ERROR = DiagnosticLevel.ERROR

KIND_BASIC = "basic"
KIND_CLOZE = "cloze"
KIND_IMAGE_OCCLUSION = "image_occlusion"

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
CLOZE_MARKER_RE = re.compile(r"\{\{c\d+::")
OPEN_FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})([^\n`]*)$")
FENCED_CODE_BLOCK_RE = re.compile(r"(?:`{3,}|~{3,})[^\n]*\n[\s\S]*?(?:`{3,}|~{3,})")
CODE_LINE_RE = re.compile(r"^\s*(?:def\s+\\w+|class\s+\\w+|import\s+\\w+|from\s+\\w+\\s+import|public\s+\\w+|function\s+\\w+)", re.MULTILINE)
EXPLICIT_CODE_RE = re.compile(r"(?:^|\s)(?:\\?#CODE#|PCL)(?:\s|$)", re.MULTILINE)
CODE_KEYWORDS = ("def ", "class ", "import ", "return ", "public ", "void ", "function ")
EQL_PREFIX = "EQL: "


@dataclass
class Card:
    file: Path
    line: int  # 1-based line number of the question
    question: str  # raw markdown; EQL lines joined with "\n"
    answer: str  # raw markdown
    tag: str  # merged hierarchical tag, e.g. TopicA::SubtopicB::Grammars
    kind: str = KIND_BASIC
    added: bool = False
    deleted: bool = False
    card_id: str | None = None
    has_code: bool = False
    has_cloze_markers: bool = False
    deck: str | None = None

    @property
    def pending(self) -> bool:
        return not self.added and not self.deleted

    @property
    def updatable(self) -> bool:
        """Already exported with an id, so it can be pushed again as an update."""
        return self.added and not self.deleted and self.card_id is not None

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
    pad_single_digits: bool = True,
) -> list[Card]:
    try:
        with open(path, "r", encoding="utf-8", newline="") as f:
            text = f.read()
    except UnicodeDecodeError as exc:
        if diagnostics is not None:
            diagnostics.append(
                Diagnostic(
                    file=path,
                    line=None,
                    level=DiagnosticLevel.ERROR,
                    category=DiagnosticCategory.SYSTEM,
                    message=f"File encoding is not valid UTF-8: {exc}",
                    suggestion="Re-save or convert the markdown file with UTF-8 encoding.",
                )
            )
        return []
    except PermissionError as exc:
        if diagnostics is not None:
            diagnostics.append(
                Diagnostic(
                    file=path,
                    line=None,
                    level=DiagnosticLevel.ERROR,
                    category=DiagnosticCategory.SYSTEM,
                    message=f"Permission denied reading file: {exc}",
                    suggestion="Check file permissions or unlock the file in your cloud storage client.",
                )
            )
        return []
    except OSError as exc:
        if diagnostics is not None:
            diagnostics.append(
                Diagnostic(
                    file=path,
                    line=None,
                    level=DiagnosticLevel.ERROR,
                    category=DiagnosticCategory.SYSTEM,
                    message=f"I/O error reading file: {exc}",
                    suggestion="Verify the file is accessible and not locked by another process.",
                )
            )
        return []

    return parse_lines(
        text.splitlines(),
        path,
        base_tag,
        file_tag=file_tag,
        diagnostics=diagnostics,
        deck=deck,
        pad_single_digits=pad_single_digits,
    )


def parse_lines(
    lines: list[str],
    file: Path,
    base_tag: str,
    file_tag: str | None = None,
    diagnostics: list[Diagnostic] | None = None,
    deck: str | None = None,
    pad_single_digits: bool = True,
) -> list[Card]:
    """Parse the lines of one note. ``base_tag`` is the tag hierarchy above the file (may be empty)."""
    diagnostics = diagnostics if diagnostics is not None else []
    note_stem_tag = format_tag_segment(file_tag or file.stem, pad_single_digits=pad_single_digits)
    tags: list[str] = [t for t in [base_tag, note_stem_tag] if t]
    fixed_levels = len(tags)  # tags that headings must never pop

    cards: list[Card] = []
    expecting_question = False
    active_fence: str | None = None
    fence_start_line = 0
    question_line = 0
    question: str | None = None
    added = False
    deleted = False
    card_id: str | None = None
    answer_lines: list[str] = []
    orphan_lines: list[tuple[int, str]] = []  # (line number, text) outside any card

    def flush() -> None:
        nonlocal question, answer_lines, orphan_lines, added, deleted, card_id
        if question is not None:
            cards.append(
                _make_card(
                    file,
                    question_line,
                    question,
                    "\n".join(answer_lines),
                    merge_tags(tags, pad_single_digits=pad_single_digits),
                    added,
                    card_id,
                    diagnostics,
                    deck=deck,
                    deleted=deleted,
                )
            )
        elif any(text.strip() for _, text in orphan_lines):
            first = next(number for number, text in orphan_lines if text.strip())
            diagnostics.append(
                Diagnostic(
                    file=file,
                    line=first,
                    level=DiagnosticLevel.ERROR,
                    category=DiagnosticCategory.SYNTAX,
                    message="text outside a card (no question line after '---')",
                    suggestion="Start a new card with a question line or remove the separator '---'.",
                )
            )
        question, answer_lines, orphan_lines, added, deleted, card_id = None, [], [], False, False, None

    for index, line in enumerate(lines, start=1):
        m_fence = OPEN_FENCE_RE.match(line)
        if m_fence:
            delim, info = m_fence.group(1), m_fence.group(2).strip()
            if active_fence is None:
                active_fence = delim
                fence_start_line = index
            elif delim[0] == active_fence[0] and len(delim) >= len(active_fence) and not info:
                active_fence = None

        in_code_block = active_fence is not None

        heading = HEADING_RE.match(line) if not in_code_block else None
        if heading:
            flush()
            expecting_question = False
            depth, text = len(heading.group(1)), heading.group(2).strip()
            formatted_heading = format_tag_segment(text, pad_single_digits=pad_single_digits)
            tags = tags_after_heading(depth, formatted_heading, tags, fixed_levels)
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
            added, deleted, card_id, question = parse_card_prefix(line)
            question_line = index
        elif line.startswith(EQL_PREFIX) and question is not None and not answer_lines:
            question += "\n" + line[len(EQL_PREFIX):]
        elif question is not None:
            answer_lines.append(line)
        else:
            orphan_lines.append((index, line))

    if active_fence is not None:
        diagnostics.append(
            Diagnostic(
                file=file,
                line=fence_start_line,
                level=DiagnosticLevel.WARNING,
                category=DiagnosticCategory.SYNTAX,
                message="unclosed code fence",
                suggestion="Close the code block with '```' on its own line.",
            )
        )

    flush()
    return cards


# --- internal helpers -----------------------------------------------------------------------------


def tags_after_heading(depth: int, heading: str, tags: list[str], fixed_levels: int) -> list[str]:
    """Heading at depth ``d`` keeps fixed tags plus ``d - 1`` ancestors, then appends the heading."""
    return tags[:fixed_levels + depth - 1] + [heading]


def format_tag_segment(raw: str, pad_single_digits: bool = True) -> str:
    """Format an unaliased tag segment, optionally padding single-digit numbers.

    Restricts single-digit padding to numbers that are isolated or immediately
    followed by a delimiter (., _, -, or whitespace), preventing false positives
    on alphanumeric terms like '2D Geometry', '3D Printing', '1st Law'.
    Preserves inner dots (e.g. '50.054') while converting numbering dot-spaces
    ('. ') into underscores.
    """
    if not raw:
        return ""
    seg = raw.strip()
    if pad_single_digits:
        seg = re.sub(r"^([1-9])(?=$|[._\-\s]\s*)", r"0\1", seg)
    seg = seg.replace(". ", "_").replace(" ", "_")
    return re.sub(r"_+", "_", seg).strip("_")


def merge_tags(tags: list[str], pad_single_digits: bool = True) -> str:
    """Merge tag parts into an Anki tag hierarchy separated by '::'.

    Note: tags[0] can be a pre-resolved base_tag whose segments are authoritative
    and exempt from re-padding single digits combustion.
    """
    parts: list[str] = []
    for idx, tag in enumerate(tags):
        if not tag:
            continue
        for sub in tag.split("::"):
            sub = sub.strip()
            if not sub:
                continue
            if idx == 0:
                # Pre-resolved base_tag segments: preserve exact alias casing/digits,
                # only normalising inner spaces and numbering dot-spaces to underscores.
                cleaned = sub.replace(". ", "_").replace(" ", "_")
                cleaned = re.sub(r"_+", "_", cleaned).strip("_")
                if cleaned:
                    parts.append(cleaned)
            else:
                formatted = format_tag_segment(sub, pad_single_digits=pad_single_digits)
                if formatted:
                    parts.append(formatted)
    return "::".join(parts)


def _make_card(
    file: Path,
    line: int,
    question: str,
    answer: str,
    tag: str,
    added: bool,
    card_id: str | None,
    diagnostics: list[Diagnostic],
    deck: str | None = None,
    deleted: bool = False,
) -> Card:
    answer = _strip_trailing_blank_lines(answer)
    first_line = question.strip().splitlines()[0].strip().lower() if question.strip() else ""
    first_line_clean = first_line.rstrip(":")
    if first_line == "cloze" or first_line_clean == "cloze":
        kind = KIND_CLOZE
    elif (
        first_line in ("image cloze", "cloze image")
        or first_line_clean in ("image cloze", "cloze image")
        or first_line.startswith(("image cloze:", "image cloze -", "cloze image:", "cloze image -"))
    ):
        kind = KIND_IMAGE_OCCLUSION
    else:
        kind = KIND_BASIC

    has_code_block = bool(FENCED_CODE_BLOCK_RE.search(question) or FENCED_CODE_BLOCK_RE.search(answer))
    has_explicit = bool(EXPLICIT_CODE_RE.search(question) or EXPLICIT_CODE_RE.search(answer))
    has_code_statement = bool(CODE_LINE_RE.search(question) or CODE_LINE_RE.search(answer))
    has_code = has_code_block or has_explicit or has_code_statement
    has_markers = bool(CLOZE_MARKER_RE.search(answer))

    if kind == KIND_BASIC and has_markers:
        diagnostics.append(
            Diagnostic(
                file=file,
                line=line,
                level=DiagnosticLevel.WARNING,
                category=DiagnosticCategory.CLOZE,
                message="cloze markers {{c1::...}} in a basic card; use 'Cloze' as the question",
                suggestion="Change the card question to 'Cloze' or remove the cloze markers.",
            )
        )
    has_image = "![[" in answer or ("![" in answer and "](" in answer)
    if kind == KIND_IMAGE_OCCLUSION and not has_image:
        diagnostics.append(
            Diagnostic(
                file=file,
                line=line,
                level=DiagnosticLevel.ERROR,
                category=DiagnosticCategory.CLOZE,
                message="image cloze without an image",
                suggestion="Embed an image using ![[image.png]] or ![](image.png) in the card body.",
            )
        )
    if kind == KIND_BASIC and not answer.strip():
        diagnostics.append(
            Diagnostic(
                file=file,
                line=line,
                level=DiagnosticLevel.WARNING,
                category=DiagnosticCategory.SYNTAX,
                message="card has an empty answer",
                suggestion="Provide answer content below the question line or remove the card.",
            )
        )

    return Card(
        file=file,
        line=line,
        question=question,
        answer=answer,
        tag=tag,
        kind=kind,
        added=added,
        deleted=deleted,
        card_id=card_id,
        has_code=has_code,
        has_cloze_markers=has_markers,
        deck=deck,
    )


def _strip_trailing_blank_lines(text: str) -> str:
    lines = text.split("\n")
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)
