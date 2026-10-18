"""Export rendered notes as an .apkg file via genanki."""
from __future__ import annotations

import hashlib
import shutil
import tempfile
import warnings
from dataclasses import dataclass, field
from pathlib import Path

import genanki

from ..build import MODEL_CLOZE, BuildResult, ImageOcclusion, RenderedNote
from ..config import Config
from ..diagnostics import Diagnostic, DiagnosticCategory, DiagnosticLevel
from ..ids import is_anki_note_id, new_card_id, with_marker
from ..models import (
    BASIC_MODEL_ID,
    BASIC_MODEL_NAME,
    CLOZE_MODEL_ID,
    CLOZE_MODEL_NAME,
    KIND_BASIC,
    KIND_CLOZE,
    load_template,
)
from ..occlusions import export_occlusions
from ..parser import Card

LEVEL_WARNING = DiagnosticLevel.WARNING

Flags = list[tuple[Card, str]]


@dataclass
class ApkgExport:
    path: Path
    note_count: int
    media_count: int
    flags: Flags = field(default_factory=list)  # (card, id) pairs to write back into the notes
    occlusion_dir: Path | None = None
    staged_occlusions: dict[str, list[str]] = field(default_factory=dict)


class BasicNote(genanki.Note):
    """Note whose GUID derives from the card id, so a re-import updates instead of duplicating."""

    def __init__(self, *args, card_id: str | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.card_id = card_id

    @property
    def guid(self):
        if self.card_id:
            return genanki.guid_for("m2a", self.card_id)
        return genanki.guid_for(*self.fields)


class ClozeNote(BasicNote):
    @property
    def guid(self):
        if self.card_id:
            return genanki.guid_for("m2a", self.card_id)
        return genanki.guid_for(self.fields[0])


def basic_model(display: dict[str, str] | None = None, templates_dir: Path | None = None) -> genanki.Model:
    t = load_template(KIND_BASIC, display, templates_dir)
    return genanki.Model(
        BASIC_MODEL_ID, BASIC_MODEL_NAME,
        fields=[{"name": "Front", "font": "Arial"}, {"name": "Back", "font": "Arial"}],
        templates=[{"name": "Card 1", "qfmt": t.qfmt, "afmt": t.afmt}],
        css=t.css,
    )


def cloze_model(display: dict[str, str] | None = None, templates_dir: Path | None = None) -> genanki.Model:
    t = load_template(KIND_CLOZE, display, templates_dir)
    return genanki.Model(
        CLOZE_MODEL_ID, CLOZE_MODEL_NAME,
        fields=[{"name": "Text", "font": "Arial"}, {"name": "Back Extra", "font": "Arial"}],
        templates=[{"name": "Cloze", "qfmt": t.qfmt, "afmt": t.afmt}],
        css=t.css,
        model_type=genanki.Model.CLOZE,
    )


def stable_deck_id(name: str) -> int:
    digest = hashlib.sha1(name.encode("utf-8")).hexdigest()
    return (1 << 30) + int(digest[:8], 16) % (1 << 30)


def drop_unsupported_updates(result: BuildResult, diagnostics: list[Diagnostic]) -> None:
    """Cards flagged by an older version with an Anki note id (``n<id>``) have no GUID an .apkg import
    could match, so they are skipped with a warning instead of being imported as duplicates."""
    kept: list[RenderedNote] = []
    for note in result.notes:
        if note.card.added and is_anki_note_id(note.card.card_id):
            diagnostics.append(
                Diagnostic(
                    file=note.card.file,
                    line=note.card.line,
                    level=DiagnosticLevel.WARNING,
                    category=DiagnosticCategory.SCHEMA,
                    message=(
                        "flagged with an Anki note id by an older version; an .apkg cannot "
                        "update it (use `--target anki --update`), skipped"
                    ),
                    suggestion="Re-export using `--target anki` to update existing cards via AnkiConnect.",
                )
            )
            result.skipped.append(note.card)
        else:
            kept.append(note)
    result.notes = kept


def export_apkg(
    result: BuildResult,
    output_path: Path,
    *,
    deck: str | None = None,
    cfg: Config | None = None,
    display: dict[str, str] | None = None,
    templates_dir: Path | None = None,
) -> ApkgExport:
    """Write the package and copy image-occlusion sources next to it."""
    default_deck_name = deck or (cfg.deck if cfg is not None else "Anki")
    disp = display if display is not None else (cfg.display if cfg is not None else {})
    tpl_dir = templates_dir if templates_dir is not None else (cfg.templates_dir if cfg is not None else None)

    decks_by_name: dict[str, genanki.Deck] = {}
    models = {MODEL_CLOZE: (ClozeNote, cloze_model(disp, tpl_dir))}
    basic = (BasicNote, basic_model(disp, tpl_dir))

    flags: Flags = []
    for note in result.notes:
        deck_name = note.deck or default_deck_name
        if deck_name not in decks_by_name:
            decks_by_name[deck_name] = genanki.Deck(stable_deck_id(deck_name), deck_name)
        deck_obj = decks_by_name[deck_name]

        card_id = note.card.card_id or new_card_id()
        note_class, model = models.get(note.model, basic)
        fields = [note.fields[0], with_marker(note.fields[1], card_id)]
        deck_obj.add_note(note_class(model=model, fields=fields, tags=note.tags, card_id=card_id))
        flags.append((note.card, card_id))

    decks_list = list(decks_by_name.values())
    if not decks_list:
        decks_list = [genanki.Deck(stable_deck_id(default_deck_name), default_deck_name)]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)
        staged_media: list[str] = []
        seen_targets: set[str] = set()
        for p in result.media:
            target_name = result.media_names.get(p, p.name)
            if target_name in seen_targets:
                continue
            seen_targets.add(target_name)
            if target_name != p.name:
                staged = tmp_dir / target_name
                if not staged.exists():
                    try:
                        staged.hardlink_to(p)
                    except (OSError, AttributeError):
                        shutil.copy2(p, staged)
                staged_media.append(str(staged))
            else:
                staged_media.append(str(p))

        package = genanki.Package(decks_list if len(decks_list) > 1 else decks_list[0])
        package.media_files = staged_media
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", module="genanki", message="^Field contained the following invalid HTML tags")
            package.write_to_file(str(output_path))

    occlusion_dir = None
    staged_occlusions: dict[str, list[str]] = {}
    if result.occlusions:
        occlusion_dir, occ_flags, staged_occlusions = export_occlusions(result.occlusions, output_path.parent)
        flags.extend(occ_flags)
    return ApkgExport(output_path, len(result.notes), len(result.media), flags, occlusion_dir, staged_occlusions)
