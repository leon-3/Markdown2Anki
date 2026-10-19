from pathlib import Path

import pytest

from markdown2anki.build import BuildResult, RenderedNote
from markdown2anki.config import Config
from markdown2anki.export import ankiconnect
from markdown2anki.parser import Card


class FakeAnki:
    """Records AnkiConnect calls; answers the few queries the exporter makes."""

    def __init__(self, models, found=None, tags=None, field_names=None, stored_media=None, fields=None, cards=None, card_decks=None):
        self.models = models  # name -> id
        self.found = found or {}  # marker id -> note id
        self.tags = tags or {}  # note_id -> list of tags
        self.fields = fields or {}  # note_id -> dict of fields
        self.field_names = field_names or {}  # model_name -> list of field names
        self.stored_media = stored_media or {}  # filename -> stored filename
        self.cards = cards or {}  # note_id -> list of card_ids
        self.card_decks = card_decks or {}  # card_id -> deck_name
        self.calls = []

    def invoke(self, action, **params):
        self.calls.append((action, params))
        if action == "multi":
            return [self.invoke(a["action"], **a.get("params", {})) for a in params.get("actions", [])]
        if action == "modelNamesAndIds":
            return dict(self.models)
        if action == "addNotes":
            return [1000 + i if next(iter(n["fields"].values()), "") else None for i, n in enumerate(params["notes"])]
        if action == "createModel":
            self.models[params["modelName"]] = 1
        if action == "findNotes":
            return [nid for cid, nid in self.found.items() if f"m2a:{cid}-->" in params["query"]]
        if action == "getNoteTags":
            return list(self.tags.get(params.get("note"), []))
        if action == "notesInfo":
            return [
                {
                    "noteId": nid,
                    "tags": list(self.tags.get(nid, [])),
                    "fields": {k: {"value": v} for k, v in self.fields.get(nid, {}).items()},
                    "cards": list(self.cards.get(nid, [])),
                }
                for nid in params.get("notes", [])
            ]
        if action == "cardsInfo":
            return [
                {
                    "cardId": cid,
                    "deckName": self.card_decks.get(cid, "Default"),
                }
                for cid in params.get("cards", [])
            ]
        if action == "changeDeck":
            for cid in params.get("cards", []):
                self.card_decks[cid] = params.get("deck")
            return True
        if action == "modelFieldNames":
            return list(self.field_names.get(params.get("modelName"), []))
        if action == "storeMediaFile":
            return self.stored_media.get(params.get("filename"), params.get("filename"))
        return None

    def params(self, action):
        return [p for a, p in self.calls if a == action]


@pytest.fixture
def anki(monkeypatch):
    def install(models, found=None, tags=None, field_names=None, stored_media=None, fields=None, cards=None, card_decks=None):
        fake = FakeAnki(models, found, tags, field_names, stored_media, fields, cards, card_decks)
        monkeypatch.setattr(ankiconnect.AnkiConnect, "invoke", lambda self, action, **p: fake.invoke(action, **p))
        return fake
    return install


def _card(line, added=False, card_id=None):
    return Card(file=Path("n.md"), line=line, question="q", answer="a", tag="T", added=added, card_id=card_id)


def _note(card, front="q", back="a", tags=None):
    return RenderedNote(card, "basic", [front, back], tags if tags is not None else ["T"])


def test_uses_the_imported_note_type_by_id_even_if_name_collides(anki):
    fake = anki({"Basic": 1234, "Basic-m2a": ankiconnect.BASIC_MODEL_ID})
    cfg = Config(vault=Path("."), deck="D", anki_basic_model="Basic")
    export = ankiconnect.export_ankiconnect(BuildResult(notes=[_note(_card(3))]), cfg, [])
    payload = fake.params("addNotes")[0]["notes"][0]
    assert payload["modelName"] == "Basic-m2a"
    assert not fake.params("createModel")
    assert export.added == 1 and export.updated == 0
    card_id = export.flags[0][1]
    assert len(card_id) == 6 and payload["fields"]["Back"] == f"a<!--m2a:{card_id}-->"


def test_creates_configured_model_when_missing_and_updates_by_legacy_note_id(anki):
    fake = anki({"Basic": 1234})
    cfg = Config(vault=Path("."), deck="D", anki_basic_model="M2A Basic")
    notes = [_note(_card(3)), _note(_card(9, added=True, card_id="n555"), "q2", "a2")]
    export = ankiconnect.export_ankiconnect(BuildResult(notes=notes), cfg, [])
    assert fake.params("createModel")[0]["modelName"] == "M2A Basic"
    update = fake.params("updateNoteFields")[0]["note"]
    assert update["id"] == 555 and update["fields"]["Front"] == "q2" and update["fields"]["Back"].startswith("a2<!--m2a:")
    assert export.added == 1 and export.updated == 1
    assert len(export.flags) == 2 and all(len(cid) == 6 for _, cid in export.flags)  # new + migrated legacy card


def test_update_finds_note_by_embedded_marker_and_reports_missing_ones(anki):
    fake = anki({"Basic": 1234}, found={"abc123": 777})
    notes = [_note(_card(3, added=True, card_id="abc123")), _note(_card(9, added=True, card_id="zzz999"))]
    diagnostics = []
    result = BuildResult(notes=notes)
    export = ankiconnect.export_ankiconnect(result, Config(vault=Path("."), deck="D"), diagnostics)
    assert export.updated == 1 and export.added == 0 and export.flags == []
    assert fake.params("updateNoteFields")[0]["note"]["id"] == 777
    assert len(diagnostics) == 1 and "not found in Anki" in diagnostics[0].message and diagnostics[0].line == 9
    assert result.skipped == [notes[1].card]


def test_refused_notes_are_reported(anki):
    anki({"Basic": 1234})
    diagnostics = []
    result = BuildResult(notes=[_note(_card(3), front="")])
    export = ankiconnect.export_ankiconnect(result, Config(vault=Path("."), deck="D"), diagnostics)
    assert export.added == 0 and export.flags == []
    assert diagnostics[0].level == "error" and "refused" in diagnostics[0].message
    assert len(result.skipped) == 1


def test_media_is_only_uploaded_for_notes_that_go_through(anki, tmp_path):
    fake = anki({"Basic": 1234})
    image = tmp_path / "img.png"
    image.write_bytes(b"x")
    note = _note(_card(3, added=True, card_id="gone00"))
    note.media = [image]
    ankiconnect.export_ankiconnect(BuildResult(notes=[note]), Config(vault=Path("."), deck="D"), [])
    assert not fake.params("storeMediaFile")


def test_ankiconnect_removes_stale_tags_on_update(anki):
    fake = anki(
        {"Basic": 1234},
        found={"tag123": 888},
        tags={888: ["TagA", "OldTagToRemove"]},
    )
    cfg = Config(vault=Path("."), deck="D")
    note = _note(_card(3, added=True, card_id="tag123"), tags=["TagA", "NewTagToAdd"])
    export = ankiconnect.export_ankiconnect(BuildResult(notes=[note]), cfg, [])
    assert export.updated == 1

    removals = fake.params("removeTags")
    assert len(removals) == 1
    assert removals[0]["notes"] == [888] and removals[0]["tags"] == "OldTagToRemove"

    additions = fake.params("addTags")
    assert len(additions) == 1
    assert additions[0]["notes"] == [888] and additions[0]["tags"] == "NewTagToAdd"


def test_ankiconnect_supports_custom_model_field_names(anki):
    fake = anki(
        {"CustomBasic": 1234},
        found={"custom1": 999},
        field_names={"CustomBasic": ["Question", "Answer"]},
    )
    cfg = Config(vault=Path("."), deck="D", anki_basic_model="CustomBasic")

    new_note = _note(_card(3), front="What is X?", back="Y")
    updated_note = _note(_card(7, added=True, card_id="custom1"), front="Q updated", back="A updated")

    export = ankiconnect.export_ankiconnect(BuildResult(notes=[new_note, updated_note]), cfg, [])
    assert export.added == 1 and export.updated == 1

    # Check new note payload used custom field names
    added_payload = fake.params("addNotes")[0]["notes"][0]
    assert "Question" in added_payload["fields"]
    assert added_payload["fields"]["Question"] == "What is X?"
    assert "Answer" in added_payload["fields"]
    assert "Front" not in added_payload["fields"]

    # Check update payload used custom field names
    updated_payload = fake.params("updateNoteFields")[0]["note"]
    assert updated_payload["id"] == 999
    assert "Question" in updated_payload["fields"]
    assert updated_payload["fields"]["Question"] == "Q updated"
    assert "Answer" in updated_payload["fields"]
    assert "Front" not in updated_payload["fields"]


def test_ankiconnect_batches_updates_via_multi(anki):
    fake = anki(
        {"Basic": 1234},
        found={"id1": 101, "id2": 102},
        tags={101: ["Old1"], 102: ["Old2"]},
    )
    cfg = Config(vault=Path("."), deck="D")
    note1 = _note(_card(1, added=True, card_id="id1"), front="Q1", back="A1", tags=["New1"])
    note2 = _note(_card(2, added=True, card_id="id2"), front="Q2", back="A2", tags=["New2"])
    export = ankiconnect.export_ankiconnect(BuildResult(notes=[note1, note2]), cfg, [])
    assert export.updated == 2

    # Check notesInfo was invoked in batch
    assert len(fake.params("notesInfo")) == 1
    assert fake.params("notesInfo")[0]["notes"] == [101, 102]

    # Check multi was invoked for findNotes batch and updates batch
    multi_calls = fake.params("multi")
    assert len(multi_calls) == 2

    # Check findNotes batch
    find_batch = multi_calls[0]["actions"]
    assert [a["action"] for a in find_batch] == ["findNotes", "findNotes"]

    # Check the update actions in the updates batch
    update_batch = multi_calls[1]["actions"]
    action_names = [a["action"] for a in update_batch]
    assert action_names.count("updateNoteFields") == 2
    assert action_names.count("removeTags") == 2
    assert action_names.count("addTags") == 2


def test_ankiconnect_rewrites_media_sources_to_stored_filenames(anki, tmp_path):
    img = tmp_path / "Pasted image 20260905091504.png"
    img.write_bytes(b"image_bytes")

    fake = anki(
        {"Basic": 1234},
        stored_media={"Pasted image 20260905091504.png": "pasted image 20260905091504.png"},
    )
    cfg = Config(vault=Path("."), deck="D")

    note = _note(
        _card(1),
        front="Question",
        back='<p>Answer<br><img src="Pasted image 20260905091504.png"></p>',
    )
    note.media = [img]

    export = ankiconnect.export_ankiconnect(BuildResult(notes=[note]), cfg, [])
    assert export.added == 1
    assert export.media_count == 1

    added_payload = fake.params("addNotes")[0]["notes"][0]
    assert '<img src="pasted image 20260905091504.png">' in added_payload["fields"]["Back"]
    assert "Pasted image" not in added_payload["fields"]["Back"]


def test_ankiconnect_rewrites_media_sources_on_update(anki, tmp_path):
    img = tmp_path / "Diagram.PNG"
    img.write_bytes(b"diagram_bytes")

    fake = anki(
        {"Basic": 1234},
        found={"upd1": 700},
        stored_media={"Diagram.PNG": "diagram.png"},
    )
    cfg = Config(vault=Path("."), deck="D")

    note = _note(
        _card(5, added=True, card_id="upd1"),
        front="Diagram Q",
        back='<p><img src="Diagram.PNG" width="300"></p>',
    )
    note.media = [img]

    export = ankiconnect.export_ankiconnect(BuildResult(notes=[note]), cfg, [])
    assert export.updated == 1

    multi_calls = fake.params("multi")
    update_action = next(a for call in multi_calls for a in call.get("actions", []) if a["action"] == "updateNoteFields")
    back_field = update_action["params"]["note"]["fields"]["Back"]
    assert '<img src="diagram.png" width="300">' in back_field


def test_ankiconnect_skips_noop_updates(anki):
    fake = anki(
        {"Basic": 1234},
        found={"noop1": 501},
        tags={501: ["Tag1"]},
        fields={501: {"Front": "Q1", "Back": "A1<!--m2a:noop1-->"}},
    )
    cfg = Config(vault=Path("."), deck="D")
    note = _note(_card(1, added=True, card_id="noop1"), front="Q1", back="A1", tags=["Tag1"])

    export = ankiconnect.export_ankiconnect(BuildResult(notes=[note]), cfg, [])
    assert export.added == 0
    assert export.updated == 0
    assert export.unchanged == 1
    assert not fake.params("updateNoteFields")
    assert not fake.params("addTags")
    assert not fake.params("removeTags")


def test_ankiconnect_normalizes_html_whitespace_and_src(anki):
    # Anki has Windows newlines, self-closing tags, and URL encoded space in src
    fake = anki(
        {"Basic": 1234},
        found={"norm1": 601},
        tags={601: ["T"]},
        fields={601: {
            "Front": "<p>Hello</p><br/>\r\n<img src='my%20img.png' />",
            "Back": "<p>World</p><!--m2a:norm1-->",
        }},
    )
    cfg = Config(vault=Path("."), deck="D")
    note = _note(
        _card(1, added=True, card_id="norm1"),
        front='<p>Hello</p><br>\n<img src="my img.png">',
        back="<p>World</p>",
        tags=["T"],
    )

    export = ankiconnect.export_ankiconnect(BuildResult(notes=[note]), cfg, [])
    assert export.updated == 0
    assert export.unchanged == 1
    assert not fake.params("updateNoteFields")


def test_ankiconnect_updates_only_tags_when_fields_identical(anki):
    fake = anki(
        {"Basic": 1234},
        found={"tags1": 701},
        tags={701: ["OldTag"]},
        fields={701: {"Front": "Q", "Back": "A<!--m2a:tags1-->"}},
    )
    cfg = Config(vault=Path("."), deck="D")
    note = _note(_card(1, added=True, card_id="tags1"), front="Q", back="A", tags=["NewTag"])

    export = ankiconnect.export_ankiconnect(BuildResult(notes=[note]), cfg, [])
    assert export.updated == 1
    assert export.unchanged == 0
    assert not fake.params("updateNoteFields")
    assert len(fake.params("removeTags")) == 1
    assert len(fake.params("addTags")) == 1


def test_ankiconnect_updates_only_fields_when_tags_identical(anki):
    fake = anki(
        {"Basic": 1234},
        found={"fld1": 801},
        tags={801: ["SameTag"]},
        fields={801: {"Front": "Old Question", "Back": "A<!--m2a:fld1-->"}},
    )
    cfg = Config(vault=Path("."), deck="D")
    note = _note(_card(1, added=True, card_id="fld1"), front="New Question", back="A", tags=["SameTag"])

    export = ankiconnect.export_ankiconnect(BuildResult(notes=[note]), cfg, [])
    assert export.updated == 1
    assert export.unchanged == 0
    assert len(fake.params("updateNoteFields")) == 1
    assert not fake.params("removeTags")
    assert not fake.params("addTags")


def test_ankiconnect_detects_image_hash_migration_as_change(anki):
    # Anki has unhashed filename, local build has hashed filename -> MUST update note in Anki
    fake = anki(
        {"Basic": 1234},
        found={"hash1": 901},
        tags={901: ["T"]},
        fields={901: {
            "Front": 'Q',
            "Back": '<p><img src="pasted image 123.png"></p><!--m2a:hash1-->',
        }},
    )
    cfg = Config(vault=Path("."), deck="D")
    note = _note(
        _card(1, added=True, card_id="hash1"),
        front="Q",
        back='<p><img src="5bcc4ef4_01.png"></p>',
        tags=["T"],
    )

    export = ankiconnect.export_ankiconnect(BuildResult(notes=[note]), cfg, [])
    assert export.updated == 1
    assert export.unchanged == 0
    assert len(fake.params("updateNoteFields")) == 1
    update_back = fake.params("updateNoteFields")[0]["note"]["fields"]["Back"]
    assert '<img src="5bcc4ef4_01.png">' in update_back


def test_ankiconnect_case_insensitive_tag_comparison(anki):
    fake = anki(
        {"Basic": 1234},
        found={"tag1": 101},
        tags={101: ["topic::subtopic", "OldTag"]},
        fields={101: {"Front": "Q", "Back": "A<!--m2a:tag1-->"}},
    )
    cfg = Config(vault=Path("."), deck="D")
    note = _note(_card(1, added=True, card_id="tag1"), front="Q", back="A", tags=["Topic::Subtopic", "NewTag"])

    export = ankiconnect.export_ankiconnect(BuildResult(notes=[note]), cfg, [])
    assert export.updated == 1
    assert not fake.params("updateNoteFields")

    removals = fake.params("removeTags")
    assert len(removals) == 1
    assert removals[0]["tags"] == "OldTag"

    additions = fake.params("addTags")
    assert len(additions) == 1
    assert additions[0]["tags"] == "NewTag"

    # Only case difference -> no-op tag update
    fake2 = anki(
        {"Basic": 1234},
        found={"tag2": 102},
        tags={102: ["topic::subtopic"]},
        fields={102: {"Front": "Q", "Back": "A<!--m2a:tag2-->"}},
    )
    note2 = _note(_card(2, added=True, card_id="tag2"), front="Q", back="A", tags=["Topic::Subtopic"])
    export2 = ankiconnect.export_ankiconnect(BuildResult(notes=[note2]), cfg, [])
    assert export2.updated == 0
    assert export2.unchanged == 1
    assert not fake2.params("removeTags")
    assert not fake2.params("addTags")


def test_ankiconnect_lazy_media_upload(anki, tmp_path):
    img_unchanged = tmp_path / "unchanged.png"
    img_unchanged.write_bytes(b"data1")
    img_changed = tmp_path / "changed.png"
    img_changed.write_bytes(b"data2")

    fake = anki(
        {"Basic": 1234},
        found={"noop": 201, "chg": 202},
        tags={201: ["T"], 202: ["T"]},
        fields={
            201: {"Front": "Q1", "Back": "<p><img src=\"unchanged.png\"></p><!--m2a:noop-->"},
            202: {"Front": "Old Question", "Back": "A<!--m2a:chg-->"},
        },
    )
    cfg = Config(vault=Path("."), deck="D")

    note1 = _note(
        _card(1, added=True, card_id="noop"),
        front="Q1",
        back="<p><img src=\"unchanged.png\"></p>",
        tags=["T"],
    )
    note1.media = [img_unchanged]

    note2 = _note(
        _card(2, added=True, card_id="chg"),
        front="New Question",
        back="<p><img src=\"changed.png\"></p>",
        tags=["T"],
    )
    note2.media = [img_changed]

    export = ankiconnect.export_ankiconnect(BuildResult(notes=[note1, note2]), cfg, [])
    assert export.updated == 1
    assert export.unchanged == 1

    stored_files = [p["filename"] for p in fake.params("storeMediaFile")]
    assert "unchanged.png" not in stored_files
    assert "changed.png" in stored_files


def test_ankiconnect_changes_deck_on_sync(anki):
    fake = anki(
        {"Basic": 1234},
        found={"move1": 301},
        cards={301: [5001]},
        card_decks={5001: "OldDeck"},
        fields={301: {"Front": "Q", "Back": "A<!--m2a:move1-->"}},
    )
    cfg = Config(vault=Path("."), deck="OldDeck")
    note = _note(_card(1, added=True, card_id="move1"), front="Q", back="A")
    note.deck = "NewDeck"

    export = ankiconnect.export_ankiconnect(BuildResult(notes=[note]), cfg, [])
    assert export.updated == 1
    assert export.unchanged == 0

    change_deck_calls = fake.params("changeDeck")
    assert len(change_deck_calls) == 1
    assert change_deck_calls[0]["cards"] == [5001]
    assert change_deck_calls[0]["deck"] == "NewDeck"
    assert fake.card_decks[5001] == "NewDeck"


def test_ankiconnect_exports_native_image_occlusion_and_suspends(anki):
    fake = anki({"Basic": 1234, "Image Occlusion": 5678})
    cfg = Config(vault=Path("."), deck="D", suspend_new_occlusions=True)
    card = Card(file=Path("io.md"), line=1, question="Image Cloze", answer="![[brain.png]]", tag="Anatomy")
    note = RenderedNote(card, "image_occlusion", ["", '<img src="brain.png">', "Header", "Extra", ""], ["Anatomy", "TODO_PROCESS_OCCLUSION"])
    export = ankiconnect.export_ankiconnect(BuildResult(notes=[note]), cfg, [])
    assert export.added == 1
    add_payload = fake.params("addNotes")[0]["notes"][0]
    assert add_payload["modelName"] == "Image Occlusion"
    assert add_payload["fields"]["Occlusion"] == "{{c1::}}"
    assert "<img src=" in add_payload["fields"]["Image"]
    assert "TODO_PROCESS_OCCLUSION" in add_payload["tags"]


def test_is_occlusion_completed():
    from markdown2anki.occlusions import is_occlusion_completed

    assert is_occlusion_completed("") is False
    assert is_occlusion_completed("   ") is False
    assert is_occlusion_completed(None) is False
    assert is_occlusion_completed("<svg viewBox='0 0 100 100'></svg>") is False
    assert is_occlusion_completed("<svg><rect x='10' y='10' width='50' height='20' data-cloze='1'/></svg>") is True
    assert is_occlusion_completed("<svg><ellipse cx='50' cy='50' rx='20' ry='10'/></svg>") is True
    assert is_occlusion_completed("<svg><path d='M10 10 L20 20 Z'/></svg>") is True
    assert is_occlusion_completed("<svg><polygon points='10,10 20,20 30,10'/></svg>") is True
    assert is_occlusion_completed("data-cloze=\"1\"") is True


def test_is_cloze_completed():
    from markdown2anki.occlusions import is_cloze_completed

    assert is_cloze_completed("") is False
    assert is_cloze_completed("Just regular text") is False
    assert is_cloze_completed(None) is False
    assert is_cloze_completed("Text with {{c1::a cloze}} deletion") is True
    assert is_cloze_completed("Text with {{c2::another cloze}} deletion") is True


def test_resolve_completed_occlusions(anki):
    fake = anki(
        models={"Basic": 1, "Image Occlusion": 2},
        tags={
            101: ["Anatomy", "TODO_PROCESS_OCCLUSION"],  # has masks -> should complete
            102: ["Anatomy", "TODO_PROCESS_OCCLUSION"],  # empty occlusion -> awaiting masks
            103: ["Anatomy"],                            # no TODO tag -> MUST NOT TOUCH
        },
        fields={
            101: {"Occlusion": "<svg><rect data-cloze='1'/></svg>"},
            102: {"Occlusion": ""},
            103: {"Occlusion": "<svg><rect data-cloze='1'/></svg>"},
        },
        cards={
            101: [1001, 1002],
            102: [1003],
            103: [1004],
        },
    )
    # Customize findNotes for fake
    def custom_invoke(action, **params):
        if action == "findNotes" and "tag:TODO_PROCESS_OCCLUSION" in params.get("query", ""):
            return [101, 102]
        return fake.__class__.invoke(fake, action, **params)
    fake.invoke = custom_invoke

    client = ankiconnect.AnkiConnect()

    # 1. Dry run
    dry_res = ankiconnect.resolve_completed_occlusions(client, dry_run=True)
    assert dry_res.total_checked == 2
    assert dry_res.awaiting_masks_count == 1
    assert dry_res.completed_notes_count == 1
    assert dry_res.unsuspended_cards_count == 2
    assert dry_res.unflagged_note_ids == [101]
    assert dry_res.unsuspended_card_ids == [1001, 1002]
    # Verify no mutation calls in dry run
    assert not any(a == "removeTags" or a == "unsuspend" for a, _ in fake.calls)

    # 2. Real execution
    res = ankiconnect.resolve_completed_occlusions(client, dry_run=False)
    assert res.completed_notes_count == 1
    assert any(a == "removeTags" and p.get("notes") == [101] and p.get("tags") == "TODO_PROCESS_OCCLUSION" for a, p in fake.calls)
    assert any(a == "unsuspend" and p.get("cards") == [1001, 1002] for a, p in fake.calls)
    # Ensure note 103 and card 1004 were never touched
    assert not any(p.get("cards") == [1004] for a, p in fake.calls)


def test_is_native_occlusion_completed():
    from markdown2anki.occlusions import is_occlusion_completed
    assert is_occlusion_completed("{{c1::image-occlusion:rect:left=.3583:top=.0021:width=.4975:height=.4951}}<br>") is True


def test_resolve_completed_clozes(anki):
    fake = anki(
        models={"Basic": 1, "Basic (Cloze)": 2},
        tags={
            201: ["Biology", "TODO_PROCESS_CLOZES"],
            202: ["Biology", "TODO_PROCESS_CLOZES"],
        },
        fields={
            201: {"Text": "Mitosis has {{c1::prophase}}", "Back Extra": ""},
            202: {"Text": "Meiosis has stages", "Back Extra": ""},
        },
        cards={
            201: [2001],
            202: [2002],
        },
    )
    def custom_invoke(action, **params):
        if action == "findNotes":
            q = params.get("query", "")
            if "tag:TODO_PROCESS_CLOZES" in q:
                return [201, 202]
            if "tag:TODO_PROCESS_OCCLUSION" in q:
                return []
        return fake.__class__.invoke(fake, action, **params)
    fake.invoke = custom_invoke

    client = ankiconnect.AnkiConnect()
    res = ankiconnect.resolve_completed_occlusions(client, dry_run=False)
    assert res.completed_notes_count == 1
    assert res.unflagged_note_ids == [201]
    assert any(a == "removeTags" and p.get("notes") == [201] and p.get("tags") == "TODO_PROCESS_CLOZES" for a, p in fake.calls)
    assert any(a == "unsuspend" and p.get("cards") == [2001] for a, p in fake.calls)


def test_ankiconnect_preserves_cloze_markers_on_diff(anki, tmp_path):
    from markdown2anki.build import BuildResult, RenderedNote
    from markdown2anki.parser import Card

    fake = anki(
        models={"M2A Basic": 1, "M2A Cloze": 2},
        found={"cid123": 301},
        tags={
            301: ["Deck"],
        },
        fields={
            301: {"Text": "<p>222 {{c1::Cloze}}</p>", "Back Extra": "<!--m2a:cid123-->"},
        },
        cards={
            301: [3001],
        },
        card_decks={
            3001: "Deck",
        },
    )
    c = Card(file=tmp_path / "n.md", line=1, question="Cloze", answer="222 Cloze", tag="Deck", card_id="cid123", kind="cloze", added=True)
    note = RenderedNote(card=c, model="cloze", fields=["<p>222 Cloze</p>", "<!--m2a:cid123-->"], tags=["Deck"], deck="Deck")
    result = BuildResult(notes=[note])

    client = ankiconnect.AnkiConnect()
    export = ankiconnect.export_ankiconnect(result, anki_connect_url=client.url)
    assert export.updated == 0
    assert export.unchanged == 1
    assert not any(a == "updateNoteFields" for a, _ in fake.calls)
