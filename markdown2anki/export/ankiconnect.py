"""Export rendered notes to a running Anki instance via AnkiConnect."""
from __future__ import annotations

import base64
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..build import MODEL_CLOZE, BuildResult, RenderedNote
from ..config import Config
from ..ids import anki_note_id, is_anki_note_id, new_card_id, search_query, with_marker
from ..models import (
    BASIC_MODEL_ID,
    CLOZE_MODEL_ID,
    KIND_BASIC,
    KIND_CLOZE,
    Template,
    load_template,
)
from ..parser import LEVEL_ERROR, LEVEL_WARNING, Card, Diagnostic

Flags = list[tuple[Card, str]]


class AnkiConnectError(RuntimeError):
    pass


class AnkiConnect:
    def __init__(self, url: str = "http://127.0.0.1:8765"):
        self.url = url

    def invoke(self, action: str, **params: Any) -> Any:
        payload = json.dumps({"action": action, "version": 6, "params": params}).encode("utf-8")
        req = urllib.request.Request(self.url, data=payload, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise AnkiConnectError(f"cannot reach AnkiConnect at {self.url} - is Anki running with the add-on? "
                                   f"({exc.reason})") from exc
        if data.get("error"):
            raise AnkiConnectError(f"{action}: {data['error']}")
        return data.get("result")

    def reachable(self) -> bool:
        try:
            self.invoke("version")
            return True
        except AnkiConnectError:
            return False

    ping = reachable

    def model_names_by_id(self) -> dict[int, str]:
        return {int(model_id): name for name, model_id in self.invoke("modelNamesAndIds").items()}

    def model_field_names(self, model_name: str) -> list[str]:
        try:
            return self.invoke("modelFieldNames", modelName=model_name) or []
        except (AnkiConnectError, Exception):
            return []

    def create_model(self, kind: str, name: str, template: Template) -> None:
        if kind == KIND_CLOZE:
            self.invoke("createModel", modelName=name, inOrderFields=["Text", "Back Extra"], css=template.css,
                        isCloze=True, cardTemplates=[{"Name": "Cloze", "Front": template.qfmt, "Back": template.afmt}])
        else:
            self.invoke("createModel", modelName=name, inOrderFields=["Front", "Back"], css=template.css,
                        cardTemplates=[{"Name": "Card 1", "Front": template.qfmt, "Back": template.afmt}])

    def ensure_deck(self, name: str) -> None:
        self.invoke("createDeck", deck=name)

    def store_media(self, notes: list[RenderedNote], media_names: dict[Path, str] | None = None) -> dict[str, str]:
        """Store media files in Anki and return a mapping of {original_name: stored_name}."""
        stored: dict[str, str] = {}
        seen: set[Path] = set()
        names = media_names or {}
        for note in notes:
            for path in note.media:
                if path in seen:
                    continue
                seen.add(path)
                target_name = names.get(path, path.name)
                data = base64.b64encode(path.read_bytes()).decode("ascii")
                res = self.invoke("storeMediaFile", filename=target_name, data=data)
                stored[target_name] = res if isinstance(res, str) else target_name
        return stored

    def find_note(self, field_name: str, card_id: str) -> int | None:
        ids = self.invoke("findNotes", query=search_query(field_name, card_id)) or []
        if not ids:
            ids = self.invoke("findNotes", query=f'"*m2a:{card_id}-->*"') or []
        return ids[0] if ids else None


# --- note types -----------------------------------------------------------------------------------


MODEL_KINDS = ((KIND_BASIC, BASIC_MODEL_ID, "anki_basic_model"), (KIND_CLOZE, CLOZE_MODEL_ID, "anki_cloze_model"))


def resolve_model_names(
    client: AnkiConnect,
    cfg: Config | None = None,
    basic_model_name: str = "M2A Basic",
    cloze_model_name: str = "M2A Cloze",
) -> dict[str, str]:
    """Kind -> note type name in Anki. A note type created by an .apkg import is recognised by its id, so
    the same styling keeps being used even if a stock note type shares the configured name."""
    by_id = client.model_names_by_id()
    fallback = {
        "anki_basic_model": cfg.anki_basic_model if cfg else basic_model_name,
        "anki_cloze_model": cfg.anki_cloze_model if cfg else cloze_model_name,
    }
    return {kind: by_id.get(model_id, fallback[setting]) for kind, model_id, setting in MODEL_KINDS}


@dataclass
class TemplateStatus:
    kind: str
    name: str  # note type name in Anki
    card_name: str  # name of its (single) card template
    local: Template
    changed: list[str] = field(default_factory=list)  # subset of front / back / styling

    @property
    def up_to_date(self) -> bool:
        return not self.changed


def template_status(client: AnkiConnect, cfg: Config) -> list[TemplateStatus]:
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


def _model_kind(model: str) -> str:
    return KIND_CLOZE if model == MODEL_CLOZE else KIND_BASIC


def _back_field(note: RenderedNote) -> str:
    return "Back Extra" if note.model == MODEL_CLOZE else "Back"


def _fields(note: RenderedNote, card_id: str, front_name: str = "Front", back_name: str = "Back") -> dict[str, str]:
    back = with_marker(note.fields[1], card_id)
    return {front_name: note.fields[0], back_name: back}


def _rewrite_media_sources(text: str, media_map: dict[str, str]) -> str:
    for orig, stored in media_map.items():
        if orig != stored:
            text = re.sub(r'src=(["\'])' + re.escape(orig) + r'\1', r'src=\1' + stored + r'\1', text)
    return text


def _locate_update(client: AnkiConnect, note: RenderedNote, back_field: str | None = None) -> tuple[int | None, str]:
    """(Anki note id, card id to use) for an already exported card. Cards flagged by an older version with
    Anki's note id are migrated to a short id, which is embedded now and written back afterwards."""
    card_id = note.card.card_id
    if is_anki_note_id(card_id):
        return anki_note_id(card_id), new_card_id()
    field = back_field or _back_field(note)
    return client.find_note(field, card_id), card_id


def export_ankiconnect(
    result: BuildResult,
    cfg: Config | None = None,
    diagnostics: list[Diagnostic] | None = None,
    *,
    deck: str | None = None,
    anki_connect_url: str | None = None,
    display: dict[str, str] | None = None,
    templates_dir: Path | None = None,
    anki_basic_model: str | None = None,
    anki_cloze_model: str | None = None,
) -> AnkiExport:
    """Add new notes and update already exported ones in place.

    An exported card is found again by the ``<!--m2a:id-->`` marker embedded in its back field, or, for
    cards flagged by an older version, by the stored Anki note id. A card that cannot be found is
    skipped with a warning.
    """
    url = anki_connect_url or (cfg.anki_connect_url if cfg is not None else "http://127.0.0.1:8765")
    default_deck_name = deck or (cfg.deck if cfg is not None else "Anki")
    disp = display if display is not None else (cfg.display if cfg is not None else {})
    tpl_dir = templates_dir if templates_dir is not None else (cfg.templates_dir if cfg is not None else None)
    basic_name = anki_basic_model or (cfg.anki_basic_model if cfg is not None else "M2A Basic")
    cloze_name = anki_cloze_model or (cfg.anki_cloze_model if cfg is not None else "M2A Cloze")
    diag_list = diagnostics if diagnostics is not None else []

    client = AnkiConnect(url)
    models = resolve_model_names(client, cfg, basic_name, cloze_name)
    existing = set(client.invoke("modelNamesAndIds"))
    needed = {KIND_BASIC} | ({KIND_CLOZE} if any(n.model == MODEL_CLOZE for n in result.notes) else set())

    for kind in needed:
        if models[kind] not in existing:
            client.create_model(kind, models[kind], load_template(kind, disp, tpl_dir))

    # Determine dynamic field names for the models (defaults: Front/Back, Text/Back Extra)
    model_field_names: dict[str, tuple[str, str]] = {}
    for kind, model_name in models.items():
        names = client.model_field_names(model_name)
        if len(names) >= 2:
            model_field_names[kind] = (names[0], names[1])
        elif kind == KIND_CLOZE:
            model_field_names[kind] = ("Text", "Back Extra")
        else:
            model_field_names[kind] = ("Front", "Back")

    to_add: list[tuple[RenderedNote, str]] = []
    to_update: list[tuple[RenderedNote, str, int]] = []
    for note in result.notes:
        if not note.card.updatable:
            to_add.append((note, new_card_id()))
            continue
        kind = _model_kind(note.model)
        _, back_name = model_field_names.get(kind, ("Front", "Back"))
        note_id, card_id = _locate_update(client, note, back_field=back_name)
        if note_id is None:
            diag_list.append(Diagnostic(note.card.file, note.card.line, LEVEL_WARNING,
                                        "not found in Anki (deleted, other profile, or exported before ids "
                                        "were embedded) - `m2a unflag --file ...` to add it again; skipped"))
            result.skipped.append(note.card)
            continue
        to_update.append((note, card_id, note_id))

    media_map = client.store_media([n for n, _ in to_add] + [n for n, _, _ in to_update], result.media_names)
    export = AnkiExport()
    export.media_count = len(media_map)

    if media_map:
        for note, _ in to_add:
            note.fields = [_rewrite_media_sources(f, media_map) for f in note.fields]
        for note, _, _ in to_update:
            note.fields = [_rewrite_media_sources(f, media_map) for f in note.fields]

    if to_update:
        tag_actions = [{"action": "getNoteTags", "params": {"note": note_id}} for _, _, note_id in to_update]
        tag_results = client.invoke("multi", actions=tag_actions)
        if not isinstance(tag_results, list) or len(tag_results) != len(to_update):
            tag_results = [client.invoke("getNoteTags", note=note_id) for _, _, note_id in to_update]

        update_actions: list[dict[str, Any]] = []
        for (note, card_id, note_id), raw_tags in zip(to_update, tag_results):
            kind = _model_kind(note.model)
            front_name, back_name = model_field_names.get(kind, ("Front", "Back"))
            update_actions.append({
                "action": "updateNoteFields",
                "params": {"note": {"id": note_id, "fields": _fields(note, card_id, front_name, back_name)}},
            })

            # Synchronize tags: remove stale tags and add fresh tags
            existing_tags = set(raw_tags or [])
            wanted_tags = set(note.tags)
            to_remove = existing_tags - wanted_tags
            to_add_tags = wanted_tags - existing_tags
            if to_remove:
                update_actions.append({
                    "action": "removeTags",
                    "params": {"notes": [note_id], "tags": " ".join(to_remove)},
                })
            if to_add_tags:
                update_actions.append({
                    "action": "addTags",
                    "params": {"notes": [note_id], "tags": " ".join(to_add_tags)},
                })
            elif not existing_tags and wanted_tags:
                update_actions.append({
                    "action": "addTags",
                    "params": {"notes": [note_id], "tags": " ".join(wanted_tags)},
                })

            if card_id != note.card.card_id:
                export.flags.append((note.card, card_id))
            export.updated += 1

        if update_actions:
            res = client.invoke("multi", actions=update_actions)
            if res is None:
                for act in update_actions:
                    client.invoke(act["action"], **act.get("params", {}))

    if to_add:
        model_names = {MODEL_CLOZE: models[KIND_CLOZE]}
        payloads = [
            {
                "deckName": n.deck or default_deck_name,
                "modelName": model_names.get(n.model, models[KIND_BASIC]),
                "fields": _fields(
                    n,
                    cid,
                    model_field_names.get(_model_kind(n.model), ("Front", "Back"))[0],
                    model_field_names.get(_model_kind(n.model), ("Front", "Back"))[1],
                ),
                "tags": n.tags,
                "options": {"allowDuplicate": True},
            }
            for n, cid in to_add
        ]

        target_decks = {p["deckName"] for p in payloads}
        for d in target_decks:
            client.ensure_deck(d)

        for (note, card_id), note_id in zip(to_add, client.invoke("addNotes", notes=payloads)):
            if note_id is None:
                diag_list.append(Diagnostic(note.card.file, note.card.line, LEVEL_ERROR,
                                            "Anki refused the note (empty front field?); not added"))
                result.skipped.append(note.card)
                continue
            export.flags.append((note.card, card_id))
            export.added += 1
    else:
        client.ensure_deck(default_deck_name)

    return export
