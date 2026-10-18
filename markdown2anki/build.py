"""Turn parsed cards into rendered notes ready for an exporter."""
from __future__ import annotations

import filecmp
import hashlib
import html
import re
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path

from .constants import CLOZE_TAG, CODE_KEYWORDS, CODE_TAG, OCCLUSION_TAG
from .diagnostics import Diagnostic, DiagnosticCategory, DiagnosticLevel
from .parser import KIND_CLOZE, KIND_IMAGE_OCCLUSION, LEVEL_ERROR, LEVEL_WARNING, Card
from .render import render_markdown, strip_keyword_lines

OBSIDIAN_IMAGE_RE = re.compile(r"!\[\[([^\]|]+)(?:\|([^\]]*))?\]\]")
MARKDOWN_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+[\"'][^\"']*[\"'])?\)")
IMAGE_RE = OBSIDIAN_IMAGE_RE

_CODE_BLOCK_RE = re.compile(
    r"(?:^[ \t]*(`{3,}|~{3,})[^\n]*\n.*?^[ \t]*\1[ \t]*$)|(?:`[^`\n]+`)",
    re.MULTILINE | re.DOTALL,
)

HTML_TAG_RE = re.compile(r"</?([A-Za-z][\w-]*)[^<>]*>")
KNOWN_HTML_TAGS = {
    "a", "abbr", "audio", "b", "blockquote", "br", "code", "col", "colgroup", "dd", "del", "div", "dl", "dt",
    "em", "h1", "h2", "h3", "h4", "h5", "h6", "hr", "i", "img", "ins", "kbd", "li", "mark", "ol", "p", "pre",
    "s", "small", "span", "strong", "sub", "sup", "table", "tbody", "td", "tfoot", "th", "thead", "tr", "u",
    "ul", "video",
}

MODEL_BASIC = "basic"
MODEL_CLOZE = "cloze"
MODEL_IMAGE_OCCLUSION = "image_occlusion"


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
        return list(dict.fromkeys(p for note in self.notes for p in note.media))


def deterministic_image_name(
    path: Path,
    registry: dict[str, str | bytes] | None = None,
    path_cache: dict[Path, str] | None = None,
) -> str:
    """Generate a deterministic 8-hex lowercase filename with counter for an image file."""
    if path_cache is not None and path in path_cache:
        return path_cache[path]
    content = path.read_bytes()
    digest = hashlib.sha256(content).hexdigest().lower()
    prefix = digest[:8]
    ext = path.suffix.lower() or ".png"
    if registry is None:
        name = f"{prefix}_01{ext}"
    else:
        counter = 1
        while True:
            candidate = f"{prefix}_{counter:02d}{ext}"
            existing = registry.get(candidate)
            if existing is None or existing == digest or existing == content:
                registry[candidate] = digest
                name = candidate
                break
            counter += 1
    if path_cache is not None:
        path_cache[path] = name
    return name


def resolve_image_path(card: Card, name: str, vault_root: Path | None = None) -> Path | None:
    """Resolve an image reference against the note directory and standard Obsidian asset folders."""
    note_dir = card.file.parent
    clean_name = name.lstrip("/\\")
    clean_unquoted = urllib.parse.unquote(clean_name)
    candidates: list[Path] = [
        note_dir / clean_name,
        note_dir / clean_unquoted,
        note_dir / "attachments" / clean_name,
        note_dir / "attachments" / clean_unquoted,
        note_dir / "assets" / clean_name,
        note_dir / "assets" / clean_unquoted,
        note_dir / "_resources" / clean_name,
        note_dir / "_resources" / clean_unquoted,
    ]
    if vault_root is not None:
        candidates.extend([
            vault_root / clean_name,
            vault_root / clean_unquoted,
            vault_root / "attachments" / clean_name,
            vault_root / "attachments" / clean_unquoted,
            vault_root / "assets" / clean_name,
            vault_root / "assets" / clean_unquoted,
            vault_root / "_resources" / clean_name,
            vault_root / "_resources" / clean_unquoted,
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
    image_occlusion_mode: str = "stage",
) -> BuildResult:
    """``cloze_notes``: export 'Cloze' cards with {{c1::}} markers as real cloze notes (default: basic note).
    ``hash_media``: rename embedded images to deterministic 8-hex lowercase hashes (e.g. 472d6b17_01.png)."""
    diag_list = diagnostics if diagnostics is not None else []
    result = BuildResult()
    media_names_checker = _MediaNames()
    media_registry: dict[str, str | bytes] = {}
    for card in cards:
        if card.deleted:
            continue
        try:
            if card.kind == KIND_IMAGE_OCCLUSION:
                if image_occlusion_mode == "native":
                    note = _native_occlusion(card, vault_root, hash_media, result.media_names, media_registry)
                    media_names_checker.check(note, result.media_names)
                    _check_html(note, diag_list)
                    result.notes.append(note)
                else:
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
    clean_answer = _CODE_BLOCK_RE.sub("", card.answer)
    raw_names = [m.group(1).strip() for m in OBSIDIAN_IMAGE_RE.finditer(clean_answer)]
    raw_names.extend(m.group(2).strip() for m in MARKDOWN_IMAGE_RE.finditer(clean_answer))
    paths: list[Path] = []
    missing: list[Diagnostic] = []
    for name in raw_names:
        resolved = resolve_image_path(card, name, vault_root)
        if resolved is not None:
            paths.append(resolved)
        else:
            missing.append(Diagnostic(
                file=card.file,
                line=card.line,
                level=LEVEL_ERROR,
                category=DiagnosticCategory.MEDIA,
                message=f"image not found: {name}",
                suggestion="Ensure the file is located in the note folder or configured attachment directory.",
            ))
    if missing or not paths:
        raise _Skip(*missing)
    return ImageOcclusion(card, paths, card.tag)


def _note(
    card: Card,
    cloze_notes: bool,
    vault_root: Path | None = None,
    hash_media: bool = False,
    media_names: dict[Path, str] | None = None,
    media_registry: dict[str, str | bytes] | None = None,
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


def _format_image_tag(
    card: Card,
    name: str,
    attr_str: str | None,
    vault_root: Path | None,
    hash_media: bool,
    media_names: dict[Path, str] | None,
    media_registry: dict[str, str | bytes] | None,
    media: list[Path],
    missing: list[Diagnostic],
    *,
    is_obsidian: bool = False,
) -> str:
    name = name.strip()
    path = resolve_image_path(card, name, vault_root)
    if path is None:
        missing.append(Diagnostic(
            file=card.file,
            line=card.line,
            level=LEVEL_ERROR,
            category=DiagnosticCategory.MEDIA,
            message=f"image not found next to the note: {name}",
            suggestion="Ensure the file is located in the note folder or configured attachment directory.",
        ))
        img_src = Path(name).name
    else:
        if path not in media:
            media.append(path)
        if hash_media:
            if media_names is not None and path in media_names:
                img_src = media_names[path]
            else:
                img_src = deterministic_image_name(path, media_registry, media_names)
        else:
            img_src = path.name
        if media_names is not None:
            media_names[path] = img_src

    attrs = f'src="{img_src}"'
    if attr_str:
        parts = [p.strip() for p in attr_str.split("|") if p.strip()]
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
            elif not is_obsidian and part and 'alt="' not in attrs:
                attrs += f' alt="{html.escape(part, quote=True)}"'
    return f"<img {attrs}>"


def _images(
    text: str,
    card: Card,
    vault_root: Path | None = None,
    hash_media: bool = False,
    media_names: dict[Path, str] | None = None,
    media_registry: dict[str, str | bytes] | None = None,
) -> tuple[str, list[Path]]:
    """Replace ``![[name.png]]`` and ``![alt](name.png)`` with <img> tags; images are resolved from the note directory, attachments, or vault."""
    media: list[Path] = []
    missing: list[Diagnostic] = []

    # Isolate code blocks and inline code so markdown code examples containing image syntax are preserved
    code_stash: list[str] = []
    def stash_repl(m: re.Match[str]) -> str:
        code_stash.append(m.group(0))
        return f"\ue002M2A_CODE_{len(code_stash) - 1}\ue003"

    stashed = _CODE_BLOCK_RE.sub(stash_repl, text)

    # 1. Replace Obsidian image wikilinks ![[name.png|attrs]]
    def repl_obsidian(m: re.Match[str]) -> str:
        return _format_image_tag(
            card, m.group(1), m.group(2), vault_root, hash_media, media_names, media_registry, media, missing, is_obsidian=True
        )

    stashed = OBSIDIAN_IMAGE_RE.sub(repl_obsidian, stashed)

    # 2. Replace standard Markdown images ![alt/attrs](name.png)
    def repl_markdown(m: re.Match[str]) -> str:
        return _format_image_tag(
            card, m.group(2), m.group(1), vault_root, hash_media, media_names, media_registry, media, missing
        )

    stashed = MARKDOWN_IMAGE_RE.sub(repl_markdown, stashed)

    # Restore code blocks
    for i, code_block in enumerate(code_stash):
        stashed = stashed.replace(f"\ue002M2A_CODE_{i}\ue003", code_block)

    if missing:
        raise _Skip(*missing)
    return stashed, media


class _MediaNames:
    """Anki stores media by bare file name, so two different files with the same name would overwrite\n    each other. The second one is reported and its card skipped."""

    def __init__(self) -> None:
        self.by_name: dict[str, Path] = {}

    def check(self, note: RenderedNote, media_names: dict[Path, str] | None = None) -> None:
        names = media_names or {}
        for path in note.media:
            target_name = names.get(path, path.name)
            first = self.by_name.setdefault(target_name, path)
            if first != path and not filecmp.cmp(first, path, shallow=False):
                raise _Skip(Diagnostic(
                    file=note.card.file,
                    line=note.card.line,
                    level=LEVEL_ERROR,
                    category=DiagnosticCategory.MEDIA,
                    message=(
                        f"media name clash: {path.name} differs from the file of the same name "
                        f"in {first.parent.name}; rename one of them"
                    ),
                    suggestion="Rename one of the conflicting media files to avoid overwriting.",
                ))


def _check_html(note: RenderedNote, diagnostics: list[Diagnostic]) -> None:
    """Warn about text a browser would swallow as a tag, e.g. ``<actual_type>`` written outside backticks."""
    for text in note.fields:
        unknown = sorted({m.group(1) for m in HTML_TAG_RE.finditer(text) if m.group(1).lower() not in KNOWN_HTML_TAGS})
        if unknown:
            diagnostics.append(Diagnostic(
                file=note.card.file,
                line=note.card.line,
                level=LEVEL_WARNING,
                category=DiagnosticCategory.SCHEMA,
                message=(
                    "looks like an HTML tag and will not display: "
                    + ", ".join(f"<{t}>" for t in unknown[:3]) + " - wrap it in backticks"
                ),
                suggestion="Wrap code or type declarations in backticks (`<tag>`) to prevent rendering issues.",
            ))
            return


def _native_occlusion(
    card: Card,
    vault_root: Path | None = None,
    hash_media: bool = False,
    media_names: dict[Path, str] | None = None,
    media_registry: dict[str, str | bytes] | None = None,
) -> RenderedNote:
    """Render an Image Occlusion card as a native RenderedNote for Anki Desktop."""
    tags = [card.tag] if card.tag else []
    if OCCLUSION_TAG not in tags:
        tags.append(OCCLUSION_TAG)

    clean_answer = _CODE_BLOCK_RE.sub("", card.answer)
    raw_names = [m.group(1).strip() for m in OBSIDIAN_IMAGE_RE.finditer(clean_answer)]
    raw_names.extend(m.group(2).strip() for m in MARKDOWN_IMAGE_RE.finditer(clean_answer))

    paths: list[Path] = []
    missing: list[Diagnostic] = []
    for name in raw_names:
        resolved = resolve_image_path(card, name, vault_root)
        if resolved is not None:
            paths.append(resolved)
        else:
            missing.append(Diagnostic(
                file=card.file,
                line=card.line,
                level=LEVEL_ERROR,
                category=DiagnosticCategory.MEDIA,
                message=f"image not found: {name}",
                suggestion="Ensure the file is located in the note folder or configured attachment directory.",
            ))
    if missing or not paths:
        raise _Skip(*missing)

    img_path = paths[0]
    if hash_media:
        if media_names is not None and img_path in media_names:
            img_src = media_names[img_path]
        else:
            img_src = deterministic_image_name(img_path, media_registry, media_names)
    else:
        img_src = img_path.name
    if media_names is not None:
        media_names[img_path] = img_src

    # If question starts with prefix like 'Image Cloze:' or 'Image Cloze -', strip prefix for cleaner header
    raw_header = card.question
    m_pref = re.match(r"^(?:image cloze|cloze image)\s*[:\-–—]\s*(.*)$", raw_header, re.IGNORECASE | re.DOTALL)
    if m_pref:
        header_content = m_pref.group(1).strip()
    elif raw_header.strip().lower() in ("image cloze", "cloze image"):
        header_content = ""
    else:
        header_content = raw_header

    header_text = render_markdown(header_content) if header_content else ""

    # Back Extra: extract any supplemental notes in answer outside image tags
    extra_text = OBSIDIAN_IMAGE_RE.sub("", MARKDOWN_IMAGE_RE.sub("", clean_answer)).strip()
    back_extra_text = render_markdown(extra_text) if extra_text else ""

    fields = [
        "",  # Occlusion (empty until user masks it in Anki)
        f'<img src="{img_src}">',  # Image
        header_text,  # Header
        back_extra_text,  # Back Extra
        "",  # Comments (holds <!--m2a:id--> when synced)
    ]
    return RenderedNote(card, MODEL_IMAGE_OCCLUSION, fields, tags, [img_path], deck=card.deck)
