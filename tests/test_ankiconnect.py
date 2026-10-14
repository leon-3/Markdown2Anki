from pathlib import Path

import pytest

from markdown2anki.build import BuildResult, RenderedNote
from markdown2anki.config import Config
from markdown2anki.export import ankiconnect
from markdown2anki.models import load_template
from markdown2anki.parser import Card


class FakeAnki:
    """Records AnkiConnect calls; answers the few queries the exporter makes."""

    def __init__(self, models, found=None):
        self.models = models  # name -> id
        self.found = found or {}  # marker id -> note id
        self.calls = []

    def invoke(self, action, **params):
        self.calls.append((action, params))
        if action == "modelNamesAndIds":
            return dict(self.models)
        if action == "addNotes":
            return [1000 + i if n["fields"].get("Front", "x") else None for i, n in enumerate(params["notes"])]
        if action == "createModel":
            self.models[params["modelName"]] = 1
        if action == "findNotes":
            return [nid for cid, nid in self.found.items() if f"m2a:{cid}-->" in params["query"]]
        return None

    def params(self, action):
        return [p for a, p in self.calls if a == action]


@pytest.fixture
def anki(monkeypatch):
    def install(models, found=None):
        fake = FakeAnki(models, found)
        monkeypatch.setattr(ankiconnect.AnkiConnect, "invoke", lambda self, action, **p: fake.invoke(action, **p))
        return fake
    return install


def _card(line, added=False, card_id=None):
    return Card(file=Path("n.md"), line=line, question="q", answer="a", tag="T", added=added, card_id=card_id)


def _note(card, front="q", back="a"):
    return RenderedNote(card, "basic", [front, back], ["T"])


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
