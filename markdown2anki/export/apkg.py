"""Export rendered notes as an .apkg file via genanki."""
from __future__ import annotations

import hashlib
import shutil
import warnings
from dataclasses import dataclass, field
from pathlib import Path

import genanki

from ..build import MODEL_CLOZE, BuildResult, ImageOcclusion, RenderedNote
from ..config import Config
from ..ids import is_anki_note_id, new_card_id, with_marker
from ..models import BasicNote, ClozeNote, basic_model, cloze_model
from ..parser import LEVEL_WARNING, Card, Diagnostic

Flags = list[tuple[Card, str]]


@dataclass
class ApkgExport:
    path: Path
    note_count: int
    media_count: int
    flags: Flags = field(default_factory=list)  # (card, id) pairs to write back into the notes
    occlusion_dir: Path | None = None


def stable_deck_id(name: str) -> int:
    digest = hashlib.sha1(name.encode("utf-8")).hexdigest()
    return (1 << 30) + int(digest[:8], 16) % (1 << 30)


def drop_unsupported_updates(result: BuildResult, diagnostics: list[Diagnostic]) -> None:
    """Cards flagged by an older version with an Anki note id (``n<id>``) have no GUID an .apkg import
    could match, so they are skipped with a warning instead of being imported as duplicates."""
    kept: list[RenderedNote] = []
    for note in result.notes:
        if note.card.added and is_anki_note_id(note.card.card_id):
            diagnostics.append(Diagnostic(note.card.file, note.card.line, LEVEL_WARNING,
                                          "flagged with an Anki note id by an older version; an .apkg cannot "
                                          "update it (use `--target anki --update`), skipped"))
            result.skipped.append(note.card)
        else:
            kept.append(note)
    result.notes = kept


def export_occlusions(occlusions: list[ImageOcclusion], base_dir: Path) -> tuple[Path, Flags]:
    """Copy image occlusion images into base_dir/occlusions/<tag>/... and return (occlusion_dir, flags)."""
    occlusion_dir = base_dir / "occlusions"
    flags: Flags = []
    for occlusion in occlusions:
        target_dir = occlusion_dir / occlusion.tag.replace("::", "__")
        target_dir.mkdir(parents=True, exist_ok=True)
        for image in occlusion.images:
            shutil.copy2(image, target_dir / image.name)
        flags.append((occlusion.card, occlusion.card.card_id or new_card_id()))
    return occlusion_dir, flags


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

    package = genanki.Package(decks_list if len(decks_list) > 1 else decks_list[0])
    package.media_files = [str(p) for p in result.media]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", module="genanki", message="^Field contained the following invalid HTML tags")
        package.write_to_file(str(output_path))

    occlusion_dir = None
    if result.occlusions:
        occlusion_dir, occ_flags = export_occlusions(result.occlusions, output_path.parent)
        flags.extend(occ_flags)
    return ApkgExport(output_path, len(result.notes), len(package.media_files), flags, occlusion_dir)
