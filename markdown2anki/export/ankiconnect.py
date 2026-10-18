"""Export rendered notes to a running Anki instance via AnkiConnect."""
from __future__ import annotations

import base64
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..build import MODEL_CLOZE, MODEL_IMAGE_OCCLUSION, BuildResult, RenderedNote
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
from ..parser import KIND_IMAGE_OCCLUSION, LEVEL_ERROR, LEVEL_WARNING, Card, Diagnostic

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

    def notes_info(self, notes: list[int]) -> list[dict[str, Any]]:
        if not notes:
            return []
        res = self.invoke("notesInfo", notes=notes)
        return res if isinstance(res, list) else []

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

    def find_notes_batch(self, queries: list[str], chunk_size: int = 100) -> list[list[int]]:
        """Run multiple findNotes queries in chunks using AnkiConnect's multi action."""
        if not queries:
            return []
        results: list[list[int]] = []
        for i in range(0, len(queries), chunk_size):
            chunk = queries[i : i + chunk_size]
            actions = [{"action": "findNotes", "params": {"query": q}} for q in chunk]
            res = self.invoke("multi", actions=actions)
            if isinstance(res, list) and len(res) == len(chunk):
                results.extend([r if isinstance(r, list) else [] for r in res])
            else:
                results.extend([(self.invoke("findNotes", query=q) or []) for q in chunk])
        return results


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


# --- sync -----------------------------------------------------------------------------------------


@dataclass
class AnkiExport:
    added: int = 0
    updated: int = 0
    unchanged: int = 0
    media_count: int = 0
    flags: Flags = field(default_factory=list)  # (card, id) pairs to write back into the notes
    missing_in_anki: list[Card] = field(default_factory=list)
    added_image_cloze: int = 0
    added_text_cloze: int = 0
    added_basic: int = 0


def _model_kind(model: str) -> str:
    if model == MODEL_IMAGE_OCCLUSION:
        return KIND_IMAGE_OCCLUSION
    return KIND_CLOZE if model == MODEL_CLOZE else KIND_BASIC


def _back_field(note: RenderedNote) -> str:
    if note.model == MODEL_IMAGE_OCCLUSION:
        return "Comments"
    return "Back Extra" if note.model == MODEL_CLOZE else "Back"


def _fields(note: RenderedNote, card_id: str, front_name: str = "Front", back_name: str = "Back") -> dict[str, str]:
    if note.model == MODEL_IMAGE_OCCLUSION:
        return {
            "Occlusion": note.fields[0] if note.fields[0] else "{{c1::}}",
            "Image": note.fields[1] if len(note.fields) > 1 else "",
            "Header": note.fields[2] if len(note.fields) > 2 else "",
            "Back Extra": note.fields[3] if len(note.fields) > 3 else "",
            "Comments": with_marker(note.fields[4] if len(note.fields) > 4 else "", card_id),
        }
    back = with_marker(note.fields[1], card_id)
    return {front_name: note.fields[0], back_name: back}


def _rewrite_media_sources(text: str, media_map: dict[str, str]) -> str:
    for orig, stored in media_map.items():
        if orig != stored:
            text = re.sub(r'src=(["\'])' + re.escape(orig) + r'\1', r'src=\1' + stored + r'\1', text)
    return text


def normalize_field_html(text: str) -> str:
    """Normalize HTML for safe diff comparison between local field and Anki field."""
    if not text:
        return ""
    text = text.replace("\r\n", "\n")
    # Normalize self-closing tags: <br/> -> <br>, <img .../> -> <img ...>
    text = re.sub(r"<(img|br|hr)\b([^>]*?)\s*/>", r"<\1\2>", text, flags=re.IGNORECASE)
    # Normalize URL encoding in src attributes: src="a%20b.png" -> src="a b.png"
    def _unquote_src(m: re.Match[str]) -> str:
        return f"{m.group(1)}{urllib.parse.unquote(m.group(2))}{m.group(3)}"
    text = re.sub(r'(src=[\"\'])(.*?)([\"\'])', _unquote_src, text, flags=re.IGNORECASE)
    # Normalize single quotes to double quotes in src attributes
    text = re.sub(r"src='([^']*?)'", r'src="\1"', text, flags=re.IGNORECASE)
    # Strip whitespace per line and overall
    lines = [line.rstrip() for line in text.strip().splitlines()]
    return "\n".join(lines)


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
    recreate_missing: bool = False,
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
    export = AnkiExport()

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
    candidates: list[tuple[RenderedNote, str, str]] = []

    for note in result.notes:
        if not note.card.updatable:
            to_add.append((note, new_card_id()))
            continue
        card_id = note.card.card_id
        if is_anki_note_id(card_id):
            if recreate_missing:
                to_add.append((note, new_card_id()))
            else:
                to_update.append((note, new_card_id(), anki_note_id(card_id)))
            continue
        kind = _model_kind(note.model)
        if note.model == MODEL_IMAGE_OCCLUSION:
            back_name = "Comments"
        else:
            _, back_name = model_field_names.get(kind, ("Front", "Back"))
        candidates.append((note, card_id, back_name))

    if candidates:
        queries = [search_query(back_name, card_id) for _, card_id, back_name in candidates]
        batch_results = client.find_notes_batch(queries)

        unresolved: list[tuple[RenderedNote, str, str]] = []
        for (note, card_id, back_name), ids in zip(candidates, batch_results):
            if ids:
                to_update.append((note, card_id, ids[0]))
            else:
                unresolved.append((note, card_id, back_name))

        if unresolved:
            fb_queries = [f'\"*m2a:{c[1]}-->*\"' for c in unresolved]
            fb_results = client.find_notes_batch(fb_queries)
            for (note, card_id, _), fb_ids in zip(unresolved, fb_results):
                if fb_ids:
                    to_update.append((note, card_id, fb_ids[0]))
                else:
                    if recreate_missing:
                        to_add.append((note, card_id))
                    else:
                        export.missing_in_anki.append(note.card)
                        diag_list.append(Diagnostic(
                            note.card.file, note.card.line, LEVEL_WARNING,
                            "not found in Anki (deleted, other profile, or exported before ids "
                            "were embedded) - run `m2a orphans --recreate` to add it again, or `m2a orphans --mark-deleted` to mark in vault; skipped",
                        ))
                        result.skipped.append(note.card)

    info_by_id: dict[int, dict[str, Any]] = {}
    if to_update:
        update_note_ids = [nid for _, _, nid in to_update]
        note_infos = client.notes_info(update_note_ids)
        for info in note_infos:
            if isinstance(info, dict) and "noteId" in info:
                info_by_id[info["noteId"]] = info

    # Pre-diff fields to enable lazy media uploads (only upload media for new notes or notes with modified fields)
    to_update_diffs: list[dict[str, Any]] = []
    notes_needing_media: list[RenderedNote] = [n for n, _ in to_add]

    for note, card_id, note_id in to_update:
        if note.model == MODEL_IMAGE_OCCLUSION:
            front_name, back_name = "Header", "Comments"
            new_fields = _fields(note, card_id)
        else:
            kind = _model_kind(note.model)
            front_name, back_name = model_field_names.get(kind, ("Front", "Back"))
            new_fields = _fields(note, card_id, front_name, back_name)

        info = info_by_id.get(note_id)
        if info is not None and "fields" in info:
            raw_existing_fields = info.get("fields", {})
            existing_fields = {
                k: v.get("value", "") if isinstance(v, dict) else str(v)
                for k, v in raw_existing_fields.items()
            }
            existing_tags = set(info.get("tags") or [])
            if note.model == MODEL_IMAGE_OCCLUSION:
                new_fields["Occlusion"] = existing_fields.get("Occlusion", "{{c1::}}")
                new_fields["Image"] = existing_fields.get("Image", new_fields.get("Image", ""))
                if getattr(cfg, "freeze_image_occlusions", False):
                    fields_changed = False
                else:
                    fields_changed = any(
                        normalize_field_html(new_fields.get(fname, "")) != normalize_field_html(existing_fields.get(fname, ""))
                        for fname in ("Header", "Back Extra")
                    )
            else:
                fields_changed = any(
                    normalize_field_html(new_fields.get(fname, "")) != normalize_field_html(existing_fields.get(fname, ""))
                    for fname in new_fields
                )
        else:
            raw_tags = client.invoke("getNoteTags", note=note_id) or []
            existing_tags = set(raw_tags)
            fields_changed = True

        if fields_changed and note.media:
            notes_needing_media.append(note)

        to_update_diffs.append({
            "note": note,
            "card_id": card_id,
            "note_id": note_id,
            "front_name": front_name,
            "back_name": back_name,
            "new_fields": new_fields,
            "existing_tags": existing_tags,
            "fields_changed": fields_changed,
            "info": info,
        })

    media_map = client.store_media(notes_needing_media, result.media_names)
    export.media_count = len(media_map)

    if media_map:
        for note, _ in to_add:
            note.fields = [_rewrite_media_sources(f, media_map) for f in note.fields]
        for item in to_update_diffs:
            if item["fields_changed"] and item["note"].media:
                note = item["note"]
                note.fields = [_rewrite_media_sources(f, media_map) for f in note.fields]
                item["new_fields"] = _fields(note, item["card_id"], item["front_name"], item["back_name"])

    if to_update:
        # Batch query cardsInfo to inspect deck assignment for updated notes
        all_card_ids: list[int] = []
        for info in info_by_id.values():
            for cid in info.get("cards", []):
                if isinstance(cid, int):
                    all_card_ids.append(cid)

        card_deck_map: dict[int, str] = {}
        if all_card_ids:
            try:
                for i in range(0, len(all_card_ids), 100):
                    chunk = all_card_ids[i : i + 100]
                    res = client.invoke("cardsInfo", cards=chunk)
                    if isinstance(res, list):
                        for c in res:
                            if isinstance(c, dict) and "cardId" in c and "deckName" in c:
                                card_deck_map[c["cardId"]] = c["deckName"]
            except Exception:
                pass

        update_actions: list[dict[str, Any]] = []
        for item in to_update_diffs:
            note = item["note"]
            card_id = item["card_id"]
            note_id = item["note_id"]
            new_fields = item["new_fields"]
            existing_tags = item["existing_tags"]
            fields_changed = item["fields_changed"]
            info = item["info"]

            # Case-insensitive tag diff prevents infinite dirty-marking from Anki's case normalization
            existing_tags_map = {t.lower(): t for t in existing_tags}
            wanted_tags_map = {t.lower(): t for t in note.tags}

            to_remove = {existing_tags_map[k] for k in existing_tags_map if k not in wanted_tags_map}
            to_add_tags = {wanted_tags_map[k] for k in wanted_tags_map if k not in existing_tags_map}
            tags_changed = bool(to_remove or to_add_tags)

            # Deck routing diff
            wanted_deck = note.deck or default_deck_name
            note_card_ids = [cid for cid in (info.get("cards") or []) if isinstance(cid, int)] if info else []
            cards_to_move = [cid for cid in note_card_ids if card_deck_map.get(cid) and card_deck_map[cid] != wanted_deck]
            deck_changed = bool(cards_to_move)

            if fields_changed:
                update_actions.append({
                    "action": "updateNoteFields",
                    "params": {"note": {"id": note_id, "fields": new_fields}},
                })

            if to_remove:
                update_actions.append({
                    "action": "removeTags",
                    "params": {"notes": [note_id], "tags": " ".join(sorted(to_remove))},
                })
            if to_add_tags:
                update_actions.append({
                    "action": "addTags",
                    "params": {"notes": [note_id], "tags": " ".join(sorted(to_add_tags))},
                })
            if cards_to_move:
                client.ensure_deck(wanted_deck)
                update_actions.append({
                    "action": "changeDeck",
                    "params": {"cards": cards_to_move, "deck": wanted_deck},
                })

            if card_id != note.card.card_id:
                export.flags.append((note.card, card_id))

            if fields_changed or tags_changed or deck_changed or card_id != note.card.card_id:
                export.updated += 1
            else:
                export.unchanged += 1

        if update_actions:
            res = client.invoke("multi", actions=update_actions)
            if res is None:
                for act in update_actions:
                    client.invoke(act["action"], **act.get("params", {}))

    if to_add:
        model_names = {
            MODEL_CLOZE: models[KIND_CLOZE],
            MODEL_IMAGE_OCCLUSION: "Image Occlusion",
        }
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

        note_ids = client.invoke("addNotes", notes=payloads)
        suspend_new_occlusions = getattr(cfg, "suspend_new_occlusions", True) if cfg else True
        suspend_new_clozes = getattr(cfg, "suspend_new_clozes", False) if cfg else False
        notes_to_suspend: list[int] = []

        for (note, card_id), note_id in zip(to_add, note_ids):
            if note_id is None:
                diag_list.append(Diagnostic(note.card.file, note.card.line, LEVEL_ERROR,
                                            "Anki refused the note (empty front field?); not added"))
                result.skipped.append(note.card)
                continue
            export.flags.append((note.card, card_id))
            export.added += 1
            is_io = (
                note.model == MODEL_IMAGE_OCCLUSION
                or "occlusion" in str(note.model).lower()
                or getattr(note.card, "kind", None) in ("image_occlusion", "Image Occlusion", KIND_IMAGE_OCCLUSION)
            )
            is_cloze = (
                not is_io and (
                    note.model == MODEL_CLOZE
                    or "cloze" in str(note.model).lower()
                    or getattr(note.card, "kind", None) in ("cloze", "Cloze", KIND_CLOZE)
                    or getattr(note.card, "has_cloze_markers", False)
                )
            )
            if is_io:
                export.added_image_cloze += 1
            elif is_cloze:
                export.added_text_cloze += 1
            else:
                export.added_basic += 1
            if (note.model == MODEL_IMAGE_OCCLUSION and suspend_new_occlusions) or \
               (note.model == MODEL_CLOZE and suspend_new_clozes):
                notes_to_suspend.append(note_id)

        if notes_to_suspend:
            try:
                card_ids_to_suspend = []
                for nid in notes_to_suspend:
                    cids = client.invoke("findCards", query=f"nid:{nid}")
                    if isinstance(cids, list):
                        card_ids_to_suspend.extend(cids)
                if card_ids_to_suspend:
                    client.invoke("suspend", cards=card_ids_to_suspend)
            except Exception:
                pass
    else:
        client.ensure_deck(default_deck_name)

    return export
