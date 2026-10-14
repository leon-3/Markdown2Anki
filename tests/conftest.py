import pytest

from markdown2anki import ui


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
