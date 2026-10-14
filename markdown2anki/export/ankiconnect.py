"""Push rendered notes straight into a running Anki via the AnkiConnect add-on
(https://ankiweb.net/shared/info/2055492159).

Notes go into the note types named in the config (``anki_basic_model`` / ``anki_cloze_model``), unless a
note type created by an earlier .apkg import exists (found by id). Missing note types are created from
the templates; existing ones are never modified by ``sync`` (see ``m2a templates``).
"""
from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from ..build import MODEL_CLOZE, BuildResult, RenderedNote
from ..config import Config
from ..ids import anki_note_id, is_anki_note_id, new_card_id, search_query, with_marker
from ..models import (BASIC_MODEL_ID, CLOZE_MODEL_ID, KIND_BASIC, KIND_CLOZE, Template, load_template)
from ..parser import LEVEL_ERROR, LEVEL_WARNING, Card, Diagnostic

Flags = List[Tuple[Card, str]]


class AnkiConnectError(RuntimeError):
    pass


class AnkiConnect:
    def __init__(self, url: str) -> None:
        self.url = url

    def invoke(self, action: str, **params: Any) -> Any:
        payload = json.dumps({"action": action, "version": 6, "params": params}).encode("utf-8")
        request = urllib.request.Request(self.url, payload, {"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = json.load(response)
        except urllib.error.URLError as exc:
            raise AnkiConnectError(f"cannot reach AnkiConnect at {self.url} - is Anki running with the add-on? "
                                   f"({exc.reason})") from exc
        if body.get("error"):
            raise AnkiConnectError(f"{action}: {body['error']}")
        return body.get("result")

    def reachable(self) -> bool:
        try:
            self.invoke("version")
            return True
        except AnkiConnectError:
            return False

    def model_names_by_id(self) -> Dict[int, str]:
        return {int(model_id): name for name, model_id in self.invoke("modelNamesAndIds").items()}

    def create_model(self, kind: str, name: str, template: Template) -> None:
        if kind == KIND_CLOZE:
            self.invoke("createModel", modelName=name, inOrderFields=["Text", "Back Extra"], css=template.css,
                        isCloze=True, cardTemplates=[{"Name": "Cloze", "Front": template.qfmt, "Back": template.afmt}])
        else:
            self.invoke("createModel", modelName=name, inOrderFields=["Front", "Back"], css=template.css,
                        cardTemplates=[{"Name": "Card 1", "Front": template.qfmt, "Back": template.afmt}])

    def ensure_deck(self, name: str) -> None:
        self.invoke("createDeck", deck=name)

    def store_media(self, notes: List[RenderedNote]) -> int:
        seen = set()
        for note in notes:
            for path in note.media:
                if path in seen:
                    continue
                seen.add(path)
                data = base64.b64encode(path.read_bytes()).decode("ascii")
                self.invoke("storeMediaFile", filename=path.name, data=data)
        return len(seen)

    def find_note(self, field_name: str, card_id: str) -> Optional[int]:
        ids = self.invoke("findNotes", query=search_query(field_name, card_id)) or []
        return ids[0] if ids else None


# --- note types -----------------------------------------------------------------------------------


MODEL_KINDS = ((KIND_BASIC, BASIC_MODEL_ID, "anki_basic_model"), (KIND_CLOZE, CLOZE_MODEL_ID, "anki_cloze_model"))


def resolve_model_names(client: AnkiConnect, cfg: Config) -> Dict[str, str]:
    """Kind -> note type name in Anki. A note type created by an .apkg import is recognised by its id, so
    the same styling keeps being used even if a stock note type shares the configured name."""
    by_id = client.model_names_by_id()
    return {kind: by_id.get(model_id, getattr(cfg, setting)) for kind, model_id, setting in MODEL_KINDS}


@dataclass
class TemplateStatus:
    kind: str
    name: str  # note type name in Anki
    card_name: str  # name of its (single) card template
    local: Template
    changed: List[str] = field(default_factory=list)  # subset of front / back / styling

    @property
    def up_to_date(self) -> bool:
        return not self.changed


def template_status(client: AnkiConnect, cfg: Config) -> List[TemplateStatus]:
    """Compare the local templates with the note types that exist in Anki."""
    existing = set(client.invoke("modelNamesAndIds"))
    out = []
    for kind, name in resolve_model_names(client, cfg).items():
        if name not in existing:
            continue
        local = load_template(kind, cfg.display, cfg.templates_dir)
        card_name, remote = next(iter(client.invoke("modelTemplates", modelName=name).items()))
        remote_css = client.invoke("modelStyling", modelName=name)["css"]
        changed = [label for label, mine, theirs in (("front", local.qfmt, remote.get("Front", "")),
                                                    ("back", local.afmt, remote.get("Back", "")),
                                                    ("styling", local.css, remote_css))
                   if mine.strip() != theirs.strip()]
        out.append(TemplateStatus(kind, name, card_name, local, changed))
    return out


def push_template(client: AnkiConnect, status: TemplateStatus) -> None:
    """Overwrite one note type's card template and styling in Anki with the local version."""
    client.invoke("updateModelTemplates", model={"name": status.name, "templates": {
        status.card_name: {"Front": status.local.qfmt, "Back": status.local.afmt}}})
    client.invoke("updateModelStyling", model={"name": status.name, "css": status.local.css})


# --- sync -----------------------------------------------------------------------------------------


@dataclass
class AnkiExport:
    added: int = 0
    updated: int = 0
    media_count: int = 0
    flags: Flags = field(default_factory=list)  # (card, id) pairs to write back into the notes


def _back_field(note: RenderedNote) -> str:
    return "Back Extra" if note.model == MODEL_CLOZE else "Back"


def _fields(note: RenderedNote, card_id: str) -> Dict[str, str]:
    back = with_marker(note.fields[1], card_id)
    if note.model == MODEL_CLOZE:
        return {"Text": note.fields[0], "Back Extra": back}
    return {"Front": note.fields[0], "Back": back}


def _locate_update(client: AnkiConnect, note: RenderedNote) -> Tuple[Optional[int], str]:
    """(Anki note id, card id to use) for an already exported card. Cards flagged by an older version with
    Anki's note id are migrated to a short id, which is embedded now and written back afterwards."""
    card_id = note.card.card_id
    if is_anki_note_id(card_id):
        return anki_note_id(card_id), new_card_id()
    return client.find_note(_back_field(note), card_id), card_id


def export_ankiconnect(result: BuildResult, cfg: Config, diagnostics: List[Diagnostic]) -> AnkiExport:
    """Add new notes and update already exported ones in place.

    An exported card is found again by the ``<!--m2a:id-->`` marker embedded in its back field, or, for
    cards flagged by an older version, by the stored Anki note id. A card that cannot be found is
    skipped with a warning.
    """
    client = AnkiConnect(cfg.anki_connect_url)
    models = resolve_model_names(client, cfg)
    existing = set(client.invoke("modelNamesAndIds"))
    needed = {KIND_BASIC} | ({KIND_CLOZE} if any(n.model == MODEL_CLOZE for n in result.notes) else set())
    for kind in needed:
        if models[kind] not in existing:
            client.create_model(kind, models[kind], load_template(kind, cfg.display, cfg.templates_dir))
    client.ensure_deck(cfg.deck)

    to_add: List[Tuple[RenderedNote, str]] = []
    to_update: List[Tuple[RenderedNote, str, int]] = []
    for note in result.notes:
        if not note.card.updatable:
            to_add.append((note, new_card_id()))
            continue
        note_id, card_id = _locate_update(client, note)
        if note_id is None:
            diagnostics.append(Diagnostic(note.card.file, note.card.line, LEVEL_WARNING,
                                          "not found in Anki (deleted, other profile, or exported before ids "
                                          "were embedded) - `m2a unflag --file ...` to add it again; skipped"))
            result.skipped.append(note.card)
            continue
        to_update.append((note, card_id, note_id))

    export = AnkiExport()
    export.media_count = client.store_media([n for n, _ in to_add] + [n for n, _, _ in to_update])

    for note, card_id, note_id in to_update:
        client.invoke("updateNoteFields", note={"id": note_id, "fields": _fields(note, card_id)})
        client.invoke("addTags", notes=[note_id], tags=" ".join(note.tags))
        if card_id != note.card.card_id:
            export.flags.append((note.card, card_id))
        export.updated += 1

    if to_add:
        model_names = {MODEL_CLOZE: models[KIND_CLOZE]}
        payloads = [{"deckName": cfg.deck, "modelName": model_names.get(n.model, models[KIND_BASIC]),
                     "fields": _fields(n, cid), "tags": n.tags, "options": {"allowDuplicate": True}}
                    for n, cid in to_add]
        for (note, card_id), note_id in zip(to_add, client.invoke("addNotes", notes=payloads)):
            if note_id is None:
                diagnostics.append(Diagnostic(note.card.file, note.card.line, LEVEL_ERROR,
                                              "Anki refused the note (empty front field?); not added"))
                result.skipped.append(note.card)
                continue
            export.flags.append((note.card, card_id))
            export.added += 1
    return export
