from pathlib import Path

import pytest

from markdown2anki.build import BuildResult, RenderedNote
from markdown2anki.config import Config
from markdown2anki.export import ankiconnect
from markdown2anki.models import load_template
from markdown2anki.parser import Card


class FakeAnki:
    """Records AnkiConnect calls; answers the few queries the exporter makes."""

    def __init__(self, models, found=None, tags=None, field_names=None):
        self.models = models  # name -> id
        self.found = found or {}  # marker id -> note id
        self.tags = tags or {}  # note_id -> list of tags
        self.field_names = field_names or {}  # model_name -> list of field names
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
        if action == "modelFieldNames":
            return list(self.field_names.get(params.get("modelName"), []))
        return None

    def params(self, action):
        return [p for a, p in self.calls if a == action]


@pytest.fixture
def anki(monkeypatch):
    def install(models, found=None, tags=None, field_names=None):
        fake = FakeAnki(models, found, tags, field_names)
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


def test_template_status_and_push(anki):
    local = load_template("Basic", {"50.054_Compiler": "Compiler"})
    fake = anki({"Basic": ankiconnect.BASIC_MODEL_ID})
    base = fake.invoke

    def invoke(action, **params):
        if action == "modelTemplates":
            return {"Card 1": {"Front": "OLD FRONT", "Back": local.afmt}}
        if action == "modelStyling":
            return {"css": local.css}
        return base(action, **params)
    fake.invoke = invoke

    cfg = Config(vault=Path("."), display={"50.054_Compiler": "Compiler"})
    client = ankiconnect.AnkiConnect(cfg.anki_connect_url)
    statuses = ankiconnect.template_status(client, cfg)
    assert [s.name for s in statuses] == ["Basic"] and statuses[0].changed == ["front"]
    ankiconnect.push_template(client, statuses[0])
    update = fake.params("updateModelTemplates")[0]["model"]
    assert update["name"] == "Basic" and "Compiler" in update["templates"]["Card 1"]["Front"]
    assert fake.params("updateModelStyling")


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

    # Check multi was invoked
    multi_calls = fake.params("multi")
    assert len(multi_calls) == 2  # 1 for getNoteTags batch, 1 for update/tags batch

    # Check the update actions in the second multi call
    update_batch = multi_calls[1]["actions"]
    action_names = [a["action"] for a in update_batch]
    assert action_names.count("updateNoteFields") == 2
    assert action_names.count("removeTags") == 2
    assert action_names.count("addTags") == 2
