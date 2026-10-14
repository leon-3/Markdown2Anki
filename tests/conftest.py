from pathlib import Path
import pytest

from markdown2anki import ui
from markdown2anki.export import ankiconnect


@pytest.fixture(autouse=True)
def isolated_environment(tmp_path, monkeypatch):
    """Never let a test read the developer's real config, .env, or a running Anki."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("markdown2anki.export.ankiconnect.AnkiConnect.reachable", lambda self: False)


@pytest.fixture
def answers(monkeypatch):
    """Script the interactive prompts: ``answers(a, b, c)`` hands them out in order."""

    def script(*values):
        queue = list(values)

        def take(*args, **kwargs):
            return queue.pop(0)

        monkeypatch.setattr(ui, "interactive", lambda: True)
        for name in ("ask_text", "ask_path", "ask_checkbox", "ask_select", "ask_confirm"):
            monkeypatch.setattr(ui, name, take)
        return queue

    return script


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
