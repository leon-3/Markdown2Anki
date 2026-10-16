"""Turn parsed cards into rendered notes ready for an exporter."""
from __future__ import annotations

import filecmp
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from .constants import CLOZE_TAG, CODE_KEYWORDS, CODE_TAG
from .parser import KIND_CLOZE, KIND_IMAGE_OCCLUSION, LEVEL_ERROR, LEVEL_WARNING, Card, Diagnostic
from .render import render_markdown, strip_keyword_lines

IMAGE_RE = re.compile(r"!\[\[([^\]|]+)(?:\|([^\]]*))?\]\]")
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
    fields: list[str]
    tags: list[str]
    media: list[Path] = field(default_factory=list)
    deck: str | None = None


@dataclass
class ImageOcclusion:
    card: Card
    images: list[Path]
    tag: str


@dataclass
class BuildResult:
    notes: list[RenderedNote] = field(default_factory=list)
    occlusions: list[ImageOcclusion] = field(default_factory=list)
    skipped: list[Card] = field(default_factory=list)
    media_names: dict[Path, str] = field(default_factory=dict)

    @property
    def media(self) -> list[Path]:
        seen: list[Path] = []
        for note in self.notes:
            seen.extend(p for p in note.media if p not in seen)
        return seen


def deterministic_image_name(path: Path, registry: dict[str, bytes] | None = None) -> str:
    """Generate a deterministic 8-hex lowercase filename with counter for an image file."""
    content = path.read_bytes()
    prefix = hashlib.sha256(content).hexdigest()[:8].lower()
    ext = path.suffix.lower() or ".png"
    if registry is None:
        return f"{prefix}_01{ext}"
    counter = 1
    while True:
        candidate = f"{prefix}_{counter:02d}{ext}"
        existing = registry.get(candidate)
        if existing is None or existing == content:
            registry[candidate] = content
            return candidate
        counter += 1


def resolve_image_path(card: Card, filename: str, vault_root: Path | None = None) -> Path | None:
    """Search for the image in the note directory, common subfolders, and vault attachments."""
    clean_name = Path(filename).name
    candidates = [
        card.file.parent / filename,
        card.file.parent / clean_name,
        card.file.parent / "attachments" / clean_name,
        card.file.parent / "assets" / clean_name,
        card.file.parent / "media" / clean_name,
    ]
    if vault_root and vault_root.is_dir():
        candidates.extend([
            vault_root / filename,
            vault_root / clean_name,
            vault_root / "attachments" / clean_name,
            vault_root / "assets" / clean_name,
            vault_root / "_resources" / clean_name,
        ])
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return None


def build(
    cards: list[Card],
    diagnostics: list[Diagnostic] | None = None,
    cloze_notes: bool = False,
    vault_root: Path | None = None,
    hash_media: bool = False,
) -> BuildResult:
    """``cloze_notes``: export 'Cloze' cards with {{c1::}} markers as real cloze notes (default: basic note).
    ``hash_media``: rename embedded images to deterministic 8-hex lowercase hashes (e.g. 472d6b17_01.png)."""
    diag_list = diagnostics if diagnostics is not None else []
    result = BuildResult()
    media_names_checker = _MediaNames()
    media_registry: dict[str, bytes] = {}
    for card in cards:
        try:
            if card.kind == KIND_IMAGE_OCCLUSION:
                result.occlusions.append(_occlusion(card, vault_root))
            else:
                note = _note(card, cloze_notes, vault_root, hash_media, result.media_names, media_registry)
                media_names_checker.check(note, result.media_names)
                _check_html(note, diag_list)
                result.notes.append(note)
        except _Skip as skip:
            diag_list.extend(skip.diagnostics)
            result.skipped.append(card)
    return result


class _Skip(Exception):
    def __init__(self, *diagnostics: Diagnostic) -> None:
        super().__init__()
        self.diagnostics = list(diagnostics)


def _occlusion(card: Card, vault_root: Path | None = None) -> ImageOcclusion:
    raw_names = [m.group(1).strip() for m in IMAGE_RE.finditer(card.answer)]
    paths: list[Path] = []
    missing: list[Diagnostic] = []
    for name in raw_names:
        resolved = resolve_image_path(card, name, vault_root)
        if resolved is not None:
            paths.append(resolved)
        else:
            missing.append(Diagnostic(card.file, card.line, LEVEL_ERROR, f"image not found: {name}"))
    if missing or not paths:
        raise _Skip(*missing)
    return ImageOcclusion(card, paths, card.tag)


def _note(
    card: Card,
    cloze_notes: bool,
    vault_root: Path | None = None,
    hash_media: bool = False,
    media_names: dict[Path, str] | None = None,
    media_registry: dict[str, bytes] | None = None,
) -> RenderedNote:
    tags = [card.tag] if card.tag else []
    question, answer = card.question, card.answer
    if card.has_code and CODE_TAG not in tags:
        tags.append(CODE_TAG)
        question = strip_keyword_lines(question, CODE_KEYWORDS)
        answer = strip_keyword_lines(answer, CODE_KEYWORDS)

    if card.kind == KIND_CLOZE:
        text, media = _images(answer, card, vault_root, hash_media, media_names, media_registry)
        if cloze_notes and card.has_cloze_markers:
            return RenderedNote(card, MODEL_CLOZE, [render_markdown(text), ""], tags, media, deck=card.deck)
        tags.append(CLOZE_TAG)
        return RenderedNote(card, MODEL_BASIC, [render_markdown(text), ""], tags, media, deck=card.deck)

    q_text, q_media = _images(question, card, vault_root, hash_media, media_names, media_registry)
    a_text, a_media = _images(answer, card, vault_root, hash_media, media_names, media_registry)
    media = q_media + [m for m in a_media if m not in q_media]
    return RenderedNote(card, MODEL_BASIC, [render_markdown(q_text), render_markdown(a_text)], tags, media, deck=card.deck)


def _images(
    text: str,
    card: Card,
    vault_root: Path | None = None,
    hash_media: bool = False,
    media_names: dict[Path, str] | None = None,
    media_registry: dict[str, bytes] | None = None,
) -> tuple[str, list[Path]]:
    """Replace ``![[name.png]]`` with <img> tags; images are resolved from the note directory, attachments, or vault."""
    media: list[Path] = []
    missing: list[Diagnostic] = []

    def repl(match: re.Match[str]) -> str:
        name = match.group(1).strip()
        path = resolve_image_path(card, name, vault_root)
        if path is None:
            missing.append(Diagnostic(card.file, card.line, LEVEL_ERROR, f"image not found next to the note: {name}"))
            img_src = Path(name).name
        else:
            if path not in media:
                media.append(path)
            if hash_media:
                img_src = deterministic_image_name(path, media_registry)
            else:
                img_src = path.name
            if media_names is not None:
                media_names[path] = img_src

        attrs = f'src="{img_src}"'
        if match.group(2):
            parts = [p.strip() for p in match.group(2).split("|") if p.strip()]
            for part in parts:
                dim_match = re.match(r"^(\d+)(?:x(\d+))?$", part, re.IGNORECASE)
                if dim_match:
                    width = dim_match.group(1)
                    height = dim_match.group(2)
                    if height:
                        attrs += f' width="{width}" height="{height}"'
                    else:
                        attrs += f' width="{width}"'
                    break
        return f"<img {attrs}>"

    text = IMAGE_RE.sub(repl, text)
    if missing:
        raise _Skip(*missing)
    return text, media


class _MediaNames:
    """Anki stores media by bare file name, so two different files with the same name would overwrite
    each other. The second one is reported and its card skipped."""

    def __init__(self) -> None:
        self.by_name: dict[str, Path] = {}

    def check(self, note: RenderedNote, media_names: dict[Path, str] | None = None) -> None:
        names = media_names or {}
        for path in note.media:
            target_name = names.get(path, path.name)
            first = self.by_name.setdefault(target_name, path)
            if first != path and not filecmp.cmp(first, path, shallow=False):
                raise _Skip(Diagnostic(note.card.file, note.card.line, LEVEL_ERROR,
                                       f"media name clash: {path.name} differs from the file of the same name "
                                       f"in {first.parent.name}; rename one of them"))


def _check_html(note: RenderedNote, diagnostics: list[Diagnostic]) -> None:
    """Warn about text a browser would swallow as a tag, e.g. ``<actual_type>`` written outside backticks."""
    for text in note.fields:
        unknown = sorted({m.group(1) for m in HTML_TAG_RE.finditer(text) if m.group(1).lower() not in KNOWN_HTML_TAGS})
        if unknown:
            diagnostics.append(Diagnostic(note.card.file, note.card.line, LEVEL_WARNING,
                                          "looks like an HTML tag and will not display: "
                                          + ", ".join(f"<{t}>" for t in unknown[:3]) + " - wrap it in backticks"))
            return
