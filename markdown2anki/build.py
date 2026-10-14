"""Turn parsed cards into rendered notes ready for an exporter."""
from __future__ import annotations

import filecmp
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple

from .constants import CLOZE_TAG, CODE_KEYWORDS, CODE_TAG
from .parser import KIND_CLOZE, KIND_IMAGE_OCCLUSION, LEVEL_ERROR, LEVEL_WARNING, Card, Diagnostic
from .render import render_markdown, strip_keyword_lines

IMAGE_RE = re.compile(r"!\[\[([^\]|]+)(?:\|[^\]]*)?\]\]")
HTML_TAG_RE = re.compile(r"</?([A-Za-z][\w-]*)[^<>]*>")
KNOWN_HTML_TAGS = {
    "a", "abbr", "audio", "b", "blockquote", "br", "code", "col", "colgroup", "dd", "del", "div", "dl", "dt",
    "em", "h1", "h2", "h3", "h4", "h5", "h6", "hr", "i", "img", "ins", "kbd", "li", "mark", "ol", "p", "pre",
    "s", "small", "span", "strong", "sub", "sup", "table", "tbody", "td", "tfoot", "th", "thead", "tr", "u",
    "ul", "video",
}

MODEL_BASIC = "basic"
MODEL_CLOZE = "cloze"


@dataclass
class RenderedNote:
    card: Card
    model: str
    fields: List[str]
    tags: List[str]
    media: List[Path] = field(default_factory=list)


@dataclass
class ImageOcclusion:
    card: Card
    images: List[Path]
    tag: str


@dataclass
class BuildResult:
    notes: List[RenderedNote] = field(default_factory=list)
    occlusions: List[ImageOcclusion] = field(default_factory=list)
    skipped: List[Card] = field(default_factory=list)

    @property
    def media(self) -> List[Path]:
        seen: List[Path] = []
        for note in self.notes:
            seen.extend(p for p in note.media if p not in seen)
        return seen


def build(cards: List[Card], diagnostics: List[Diagnostic], cloze_notes: bool = False) -> BuildResult:
    """``cloze_notes``: export 'Cloze' cards with {{c1::}} markers as real cloze notes (default: basic note)."""
    result = BuildResult()
    media_names = _MediaNames()
    for card in cards:
        try:
            if card.kind == KIND_IMAGE_OCCLUSION:
                result.occlusions.append(_occlusion(card))
            else:
                note = _note(card, cloze_notes)
                media_names.check(note)
                _check_html(note, diagnostics)
                result.notes.append(note)
        except _Skip as skip:
            diagnostics.extend(skip.diagnostics)
            result.skipped.append(card)
    return result


class _Skip(Exception):
    def __init__(self, *diagnostics: Diagnostic) -> None:
        super().__init__()
        self.diagnostics = list(diagnostics)


def _occlusion(card: Card) -> ImageOcclusion:
    paths = [card.file.parent / name.strip() for name in IMAGE_RE.findall(card.answer)]
    missing = [Diagnostic(card.file, card.line, LEVEL_ERROR, f"image not found: {p.name}")
               for p in paths if not p.is_file()]
    if missing or not paths:
        raise _Skip(*missing)
    return ImageOcclusion(card, paths, card.tag)


def _note(card: Card, cloze_notes: bool) -> RenderedNote:
    tags = [card.tag] if card.tag else []
    question, answer = card.question, card.answer
    if card.has_code:
        tags.append(CODE_TAG)
        question = strip_keyword_lines(question, CODE_KEYWORDS)
        answer = strip_keyword_lines(answer, CODE_KEYWORDS)

    if card.kind == KIND_CLOZE:
        text, media = _images(answer, card)
        if cloze_notes and card.has_cloze_markers:
            return RenderedNote(card, MODEL_CLOZE, [render_markdown(text), ""], tags, media)
        tags.append(CLOZE_TAG)
        return RenderedNote(card, MODEL_BASIC, [render_markdown(text), ""], tags, media)

    q_text, q_media = _images(question, card)
    a_text, a_media = _images(answer, card)
    media = q_media + [m for m in a_media if m not in q_media]
    return RenderedNote(card, MODEL_BASIC, [render_markdown(q_text), render_markdown(a_text)], tags, media)


def _images(text: str, card: Card) -> Tuple[str, List[Path]]:
    """Replace ``![[name.png]]`` with <img> tags; the images must exist next to the note."""
    media: List[Path] = []
    missing: List[Diagnostic] = []

    def repl(match: "re.Match[str]") -> str:
        name = match.group(1).strip()
        path = card.file.parent / name
        if not path.is_file():
            missing.append(Diagnostic(card.file, card.line, LEVEL_ERROR, f"image not found next to the note: {name}"))
        elif path not in media:
            media.append(path)
        return f'<img src="{name}">'

    text = IMAGE_RE.sub(repl, text)
    if missing:
        raise _Skip(*missing)
    return text, media


class _MediaNames:
    """Anki stores media by bare file name, so two different files with the same name would overwrite
    each other. The second one is reported and its card skipped."""

    def __init__(self) -> None:
        self.by_name: Dict[str, Path] = {}

    def check(self, note: RenderedNote) -> None:
        for path in note.media:
            first = self.by_name.setdefault(path.name, path)
            if first != path and not filecmp.cmp(first, path, shallow=False):
                raise _Skip(Diagnostic(note.card.file, note.card.line, LEVEL_ERROR,
                                       f"media name clash: {path.name} differs from the file of the same name "
                                       f"in {first.parent.name}; rename one of them"))


def _check_html(note: RenderedNote, diagnostics: List[Diagnostic]) -> None:
    """Warn about text a browser would swallow as a tag, e.g. ``<actual_type>`` written outside backticks."""
    for text in note.fields:
        unknown = sorted({m.group(1) for m in HTML_TAG_RE.finditer(text) if m.group(1).lower() not in KNOWN_HTML_TAGS})
        if unknown:
            diagnostics.append(Diagnostic(note.card.file, note.card.line, LEVEL_WARNING,
                                          "looks like an HTML tag and will not display: "
                                          + ", ".join(f"<{t}>" for t in unknown[:3]) + " - wrap it in backticks"))
            return
