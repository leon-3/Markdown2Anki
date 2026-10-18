import re
import shutil
from pathlib import Path

import pytest

from markdown2anki.cli import main
from markdown2anki.config import load_config, render_toml, Config

NOTE = """---
---
# Parsing
---
What is a token?
A **lexical unit**
---
ADDED: already exported
answer
---
Cloze
A {{c1::grammar}} defines syntax
---
Code?
```c
#CODE#
int x;
```
"""


@pytest.fixture
def vault(tmp_path):
    v = tmp_path / "vault"
    (v / "50.054 Compiler" / "Anki - Lectures").mkdir(parents=True)
    (v / "50.054 Compiler" / "Anki - Lectures" / "W01 Intro.md").write_text(NOTE, encoding="utf-8")
    (v / "50.054 Compiler" / "Unknown").mkdir()
    (v / "50.054 Compiler" / "Unknown" / "x.md").write_text("---\nq\na\n", encoding="utf-8")
    (v / "Archive" / "Old" / "Anki - Lectures").mkdir(parents=True)
    (v / "templates").mkdir()
    cfg = Config(
        vault=v,
        package_name="Test",
        base_tag="SUTD",
        output_dir=tmp_path / "out",
        target="apkg",
        ignore=[".git", ".obsidian", "Archive", "templates", "Unknown"],
    )
    cfg_path = tmp_path / "m2a.toml"
    cfg_path.write_text(render_toml(cfg), encoding="utf-8")
    return v, cfg_path


def run(*argv):
    return main([str(a) for a in argv])


def test_config_roundtrip(vault):
    v, cfg_path = vault
    cfg = load_config(cfg_path)
    assert cfg.vault == v and cfg.base_tag == "SUTD" and cfg.ignore == [".git", ".obsidian", "Archive", "templates", "Unknown"]
    assert cfg.subject_tag("50.054 Compiler") == "50.054_Compiler"
    assert cfg.subject_tag("Archive") is None


def test_check_and_status(vault, capsys):
    v, cfg_path = vault
    assert run("-c", cfg_path, "check") == 0
    out = capsys.readouterr().out
    assert "cards 4" in out and "pending 3" in out and "added 1" in out

    run("-c", cfg_path, "status")
    out = capsys.readouterr().out
    assert "50.054 Compiler / Anki - Lectures" in out


def test_sync_dry_run_writes_nothing(vault, capsys):
    v, cfg_path = vault
    before = (v / "50.054 Compiler" / "Anki - Lectures" / "W01 Intro.md").read_text(encoding="utf-8")
    assert run("-c", cfg_path, "sync", "--dry-run") == 0
    assert "new 3" in capsys.readouterr().out
    assert (v / "50.054 Compiler" / "Anki - Lectures" / "W01 Intro.md").read_text(encoding="utf-8") == before
    assert not (cfg_path.parent / "out").exists()


def test_sync_apkg_flags_and_update(vault, capsys, tmp_path):
    v, cfg_path = vault
    note = v / "50.054 Compiler" / "Anki - Lectures" / "W01 Intro.md"
    assert run("-c", cfg_path, "sync", "--yes") == 0
    out = capsys.readouterr().out
    assert (tmp_path / "out" / "Test.apkg").is_file()
    assert "flagged 3 card(s)" in out

    text = note.read_text(encoding="utf-8")
    import re
    assert len(re.findall(r"%%[0-9a-z]{6}%%", text)) == 3 and "ADDED: already exported\n" in text
    assert re.search(r"^ADDED: What is a token\? %%[0-9a-z]{6}%%$", text, re.M)

    # second run: nothing pending
    assert run("-c", cfg_path, "sync", "--yes") == 0
    assert "nothing to export" in capsys.readouterr().out

    # --update re-exports the three cards with ids, but never the legacy one
    assert run("-c", cfg_path, "sync", "--yes", "--update", "--dry-run") == 0
    out = capsys.readouterr().out
    assert "updates 3" in out and "new 0" in out


def test_flag_guard_when_note_edited(vault, monkeypatch, capsys):
    v, cfg_path = vault
    note = v / "50.054 Compiler" / "Anki - Lectures" / "W01 Intro.md"
    from markdown2anki.flags import write_flags
    from markdown2anki.vault import collect
    collected = collect(load_config(cfg_path))
    # mutate the note's existing line behind m2a's back
    note.write_text(NOTE.replace("What is a token?", "What is a lexeme?"), encoding="utf-8")
    flagged, problems = write_flags([(collected.pending[0], "12345678")])
    assert flagged == 0 and problems and "changed since parsing" in problems[0]


def test_init_migrates_env(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "vault" / "50.020 Network Security" / "Anki - Lectures").mkdir(parents=True)
    (tmp_path / ".env").write_text(
        f'BASE_TAG=SUTD\nOBSIDIAN_VAULT_DIRECTORY={tmp_path / "vault"}\nPACKAGE_NAME=SUTD-Anki\n'
        'SUBJECT_TAG_DICTIONARY={"50.020 Network Security": "50.020_NetSec"}\n'
        'SUB_DIRECTORY_TAG_DICTIONARY={"Anki - Lectures": "Lectures", "Anki - Exercises": "Exercises"}\n'
        'IGNORE_DIRECTORIES=[".git", "Archive", "Exercises"]\n', encoding="utf-8")
    assert run("init", "--here", "--yes") == 0
    cfg = load_config(tmp_path / "m2a.toml")
    assert cfg.package_name == "SUTD-Anki"
    assert cfg.tag_aliases == {"50.020 Network Security": "50.020_NetSec"}
    assert "Exercises" not in cfg.ignore


def test_cloze_notes_is_opt_in(vault):
    from markdown2anki.build import MODEL_BASIC, MODEL_CLOZE, build
    from markdown2anki.parser import parse_lines
    from pathlib import Path
    cards = parse_lines(["---", "Cloze", "A {{c1::grammar}} defines syntax"], Path("n.md"), "B")
    legacy = build(cards, [])
    assert legacy.notes[0].model == MODEL_BASIC and "TODO_PROCESS_CLOZES" in legacy.notes[0].tags
    real = build(cards, [], cloze_notes=True)
    assert real.notes[0].model == MODEL_CLOZE and "TODO_PROCESS_CLOZES" not in real.notes[0].tags


def test_target_comes_from_config(vault, capsys, monkeypatch):
    v, cfg_path = vault
    cfg_path.write_text(cfg_path.read_text(encoding="utf-8").replace('target = "apkg"', 'target = "anki"'), encoding="utf-8")
    from markdown2anki.export import ankiconnect

    def boom(self, action, **params):
        raise ankiconnect.AnkiConnectError("cannot reach AnkiConnect")
    monkeypatch.setattr(ankiconnect.AnkiConnect, "invoke", boom)
    assert run("-c", cfg_path, "sync", "--yes") == 2
    assert "cannot reach AnkiConnect" in capsys.readouterr().err
    assert run("-c", cfg_path, "sync", "--yes", "--target", "apkg") == 0


def test_init_refuses_missing_vault(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert run("--vault", tmp_path / "nonexistent", "init", "--yes") == 2
    assert "not found" in capsys.readouterr().err
    assert not (tmp_path / "m2a.toml").exists()


def test_update_across_targets_is_refused(vault, capsys, monkeypatch):
    v, cfg_path = vault
    note = v / "50.054 Compiler" / "Anki - Lectures" / "W01 Intro.md"
    note.write_text(note.read_text(encoding="utf-8").replace("What is a token?", "ADDED[n4242]: What is a token?"),
                    encoding="utf-8")
    assert run("-c", cfg_path, "sync", "--yes", "--update", "--no-flag") == 0
    out = capsys.readouterr().out
    assert "an .apkg cannot update it" in out and "new 2" in out


def test_init_writes_user_config_by_default_and_refuses_twice(tmp_path, monkeypatch, capsys):
    import os
    monkeypatch.chdir(tmp_path)
    (tmp_path / "vault" / "50.020 Network Security" / "Anki - Lectures").mkdir(parents=True)
    assert run("--vault", tmp_path / "vault", "init", "--yes") == 0
    written = Path(os.environ["XDG_CONFIG_HOME"]) / "m2a" / "m2a.toml"
    assert written.is_file()
    assert "next:" in capsys.readouterr().out
    # found from any directory
    monkeypatch.chdir(tmp_path / "vault")
    assert run("status") == 0
    # a second init refuses...
    assert run("--vault", tmp_path / "vault", "init", "--yes") == 1
    assert "already exists" in capsys.readouterr().err
    # ...but a project config next to it is fine
    assert run("--vault", tmp_path / "vault", "init", "--yes", "--here") == 0
    assert (tmp_path / "vault" / "m2a.toml").is_file()
    # ...and --force replaces the user config, keeping a backup
    assert run("--vault", tmp_path / "vault", "init", "--yes", "--force") == 0
    assert written.with_suffix(".toml.bak").is_file()


def test_init_needs_a_vault(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert run("init", "--yes") == 2
    assert "--vault" in capsys.readouterr().err


def test_unflag(vault, capsys):
    v, cfg_path = vault
    note = v / "50.054 Compiler" / "Anki - Lectures" / "W01 Intro.md"
    assert run("-c", cfg_path, "sync", "--yes", "--target", "apkg") == 0
    assert note.read_text(encoding="utf-8").count("%%") == 6
    # --legacy touches only the old-style flag
    assert run("-c", cfg_path, "unflag", "--legacy", "--yes") == 0
    text = note.read_text(encoding="utf-8")
    assert "ADDED: already exported" not in text and text.count("%%") == 6
    # without a filter every flagged card is cleared; they are pending again
    assert run("-c", cfg_path, "unflag", "--yes") == 0
    assert "ADDED" not in note.read_text(encoding="utf-8")
    # Also unflags DELETED cards
    txt = note.read_text(encoding="utf-8")
    note.write_text(txt.replace("What is a compiler?", "DELETED: What is a compiler? %%del123%%"), encoding="utf-8")
    assert run("-c", cfg_path, "unflag", "--yes") == 0
    assert "DELETED" not in note.read_text(encoding="utf-8")
    run("-c", cfg_path, "status")
    assert "4" in capsys.readouterr().out


def test_relative_vault_resolves_against_config_file(tmp_path, monkeypatch):
    (tmp_path / "cfg").mkdir()
    (tmp_path / "cfg" / "vault" / "C" / "Anki - Lectures").mkdir(parents=True)
    (tmp_path / "cfg" / "m2a.toml").write_text('vault = "vault"\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)  # a different cwd
    cfg = load_config(tmp_path / "cfg" / "m2a.toml")
    assert cfg.vault == (tmp_path / "cfg" / "vault").resolve()
    assert cfg.target == "anki"


def test_tilde_in_output_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "v" / "C" / "Anki - Lectures").mkdir(parents=True)
    (tmp_path / "m2a.toml").write_text('vault = "v"\noutput_dir = "~/Downloads/M2A"\n', encoding="utf-8")
    cfg = load_config(tmp_path / "m2a.toml")
    assert cfg.output_dir == tmp_path / "Downloads" / "M2A"


def test_init_non_interactive_sets_deck_and_target(tmp_path, capsys):
    v = tmp_path / "vault"
    (v / "TopicA").mkdir(parents=True)
    (v / "TopicA" / "a.md").write_text("---\nq\na\n")
    cfg_path = tmp_path / "m2a.toml"
    assert run("-c", cfg_path, "--vault", v, "init", "--yes", "--deck", "Uni::Target", "--target", "apkg") == 0
    cfg = load_config(cfg_path)
    assert cfg.deck == "Uni::Target" and cfg.package_name == "Uni-Target" and cfg.target == "apkg"


def test_init_wizard_answers(tmp_path, answers):
    v = tmp_path / "vault"
    (v / "TopicA").mkdir(parents=True)
    (v / "TopicA" / "x.md").write_text("---\nq\na\n")
    queue = answers(str(v), "Deck", "", "apkg", True, str(tmp_path / "out"))
    cfg_path = tmp_path / "m2a.toml"
    assert run("-c", cfg_path, "init") == 0
    assert not queue
    cfg = load_config(cfg_path)
    assert cfg.vault == v.resolve()
    assert cfg.deck == "Deck" and cfg.base_tag == "" and cfg.target == "apkg" and cfg.cloze_notes
    assert cfg.output_dir == tmp_path / "out"


def test_no_arguments_prints_help(capsys):
    assert run() == 0
    out = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", capsys.readouterr().out)
    assert "Usage: m2a" in out


def test_unknown_setting_is_rejected(tmp_path):
    (tmp_path / "m2a.toml").write_text('vault = "."\nrandom_field = 123\n', encoding="utf-8")
    with pytest.raises(ValueError, match="unknown setting.*random_field"):
        load_config(tmp_path / "m2a.toml")


def test_card_with_code_gets_code_tag_and_stripped_lines(tmp_path):
    note = tmp_path / "n.md"
    note.write_text("""# Python
---
What is Python?
#CODE#
def foo():
    pass
A language.
""", encoding="utf-8")
    from markdown2anki.parser import parse_file
    from markdown2anki.build import build
    cards = parse_file(note, "Base")
    assert len(cards) == 1
    assert cards[0].has_code is True

    res = build(cards, [])
    assert len(res.notes) == 1
    assert "TODO_PROCESS_CODE" in res.notes[0].tags
    assert "#CODE#" not in res.notes[0].fields[1]
    assert "A language." in res.notes[0].fields[1]


def test_cards_with_no_tag_gets_no_base_prefix(tmp_path):
    note = tmp_path / "n.md"
    note.write_text("""---
Question
Answer
""", encoding="utf-8")
    from markdown2anki.parser import parse_file
    cards = parse_file(note, base_tag="")
    assert len(cards) == 1
    assert cards[0].tag == "n"


def test_non_ascii_and_umlauts_in_notes_and_tags(tmp_path, capsys):
    v = tmp_path / "vault"
    course_dir = v / "Einführung in die Informatik" / "Anki - Vorlesung"
    course_dir.mkdir(parents=True)
    note_file = course_dir / "01. Wahrscheinlichkeitstheorie (Einführung) & Logik.md"
    note_file.write_text(
        "---\n"
        "# Maß- und Wahrscheinlichkeitsräume\n"
        "---\n"
        "Was ist ein Ereignisraum $\\mathcal{A}$?\n"
        "Ein Mengensystem über $\\Omega$.\n",
        encoding="utf-8",
    )
    cfg = Config(
        vault=v,
        package_name="UmlautTest",
        base_tag="Uni_München",
        output_dir=tmp_path / "out",
        target="apkg",
        tag_aliases={"Anki - Vorlesung": "Vorlesung"},
    )
    cfg_path = tmp_path / "m2a.toml"
    cfg_path.write_text(render_toml(cfg), encoding="utf-8")

    assert run("-c", cfg_path, "sync", "--yes") == 0
    out = capsys.readouterr().out
    assert "flagged 1 card(s)" in out

    assert (tmp_path / "out" / "UmlautTest.apkg").is_file()
    text = note_file.read_text(encoding="utf-8")
    assert "ADDED: Was ist ein Ereignisraum" in text


def test_sync_recovers_from_missing_media(tmp_path, capsys):
    v = tmp_path / "vault"
    course_dir = v / "Algorithms" / "Anki - Lectures"
    course_dir.mkdir(parents=True)
    note_file = course_dir / "Graph.md"
    note_file.write_text(
        "---\n"
        "Valid Q1?\n"
        "Valid A1\n"
        "---\n"
        "Image Cloze\n"
        "![[missing_image_xyz.png]]\n"
        "---\n"
        "Valid Q2?\n"
        "Valid A2\n",
        encoding="utf-8",
    )
    cfg = Config(
        vault=v,
        package_name="MissingMediaTest",
        base_tag="CS",
        output_dir=tmp_path / "out",
        target="apkg",
    )
    cfg_path = tmp_path / "m2a.toml"
    cfg_path.write_text(render_toml(cfg), encoding="utf-8")

    assert run("-c", cfg_path, "sync", "--yes") == 0
    out = capsys.readouterr().out
    assert "image not found: missing_image_xyz.png" in out
    assert "skipped 1" in out
    assert "flagged 2 card(s)" in out
    assert (tmp_path / "out" / "MissingMediaTest.apkg").is_file()

def test_orphans_command_and_actions(vault, monkeypatch, capsys):
    from markdown2anki.export import ankiconnect

    class FakeOrphanAnki:
        def __init__(self):
            self.calls = []

        def invoke(self, action, **params):
            self.calls.append((action, params))
            if action == "version":
                return 6
            if action == "modelNamesAndIds":
                return {"M2A Basic": 1, "M2A Cloze": 2}
            if action == "findNotes":
                return [101, 102]
            if action == "notesInfo":
                return [
                    {
                        "noteId": 101,
                        "modelName": "M2A Basic",
                        "fields": {"Front": {"value": "Active Q"}, "Back": {"value": "Active A<!--m2a:act101-->"}},
                        "cards": [1001],
                    },
                    {
                        "noteId": 102,
                        "modelName": "M2A Basic",
                        "fields": {"Front": {"value": "Orphan Q"}, "Back": {"value": "Orphan A<!--m2a:orph999-->"}},
                        "cards": [1002],
                    },
                ]
            if action == "suspend":
                return True
            if action == "deleteNotes":
                return True
            return None

    fake = FakeOrphanAnki()
    monkeypatch.setattr(ankiconnect.AnkiConnect, "invoke", lambda self, action, **p: fake.invoke(action, **p))
    monkeypatch.setattr(ankiconnect.AnkiConnect, "reachable", lambda self: True)

    v, cfg_path = vault
    note = v / "50.054 Compiler" / "Anki - Lectures" / "W01 Intro.md"
    content = (
        note.read_text(encoding="utf-8")
        + "\n---\nADDED: Active Q %%act101%%\nActive A\n"
        + "\n---\nADDED: Missing In Anki Q %%miss555%%\nMissing A\n"
    )
    note.write_text(content, encoding="utf-8")

    # 1. Inspect orphans
    assert run("-c", cfg_path, "orphans") == 0
    out = capsys.readouterr().out
    assert "orph999" in out
    assert "Orphan Q" in out
    assert "miss555" in out
    assert "Cards Deleted in Anki" in out

    # 2. Suspend orphans
    assert run("-c", cfg_path, "orphans", "--suspend") == 0
    out = capsys.readouterr().out
    assert "Suspended 1 card(s)" in out
    assert any(a == "suspend" and p.get("cards") == [1002] for a, p in fake.calls)

    # 3. Delete orphans with confirmation
    assert run("-c", cfg_path, "orphans", "--delete", "--yes") == 0
    out = capsys.readouterr().out
    assert "Permanently deleted 1 orphaned note(s)" in out
    assert any(a == "deleteNotes" and p.get("notes") == [102] for a, p in fake.calls)


def test_sync_mark_deleted_and_recreate_missing(tmp_path, monkeypatch, capsys):
    from markdown2anki.export import ankiconnect

    v = tmp_path / "vault"
    v.mkdir()
    (v / "Notes").mkdir()
    img_file = v / "Notes" / "img.png"
    img_file.write_bytes(b"dummy image data")
    note_file = v / "Notes" / "test.md"
    note_content = (
        "---\nADDED: Question Missing %%miss111%%\nAnswer Missing\n"
        "---\nADDED: Image Cloze %%occ222%%\n![[img.png]]\n"
    )
    note_file.write_text(note_content, encoding="utf-8")
    cfg_file = tmp_path / "m2a.toml"
    cfg = Config(vault=v, package_name="Test", output_dir=tmp_path / "out", target="anki", image_occlusion_mode="native")
    cfg_file.write_text(render_toml(cfg), encoding="utf-8")

    class FakeSyncAnki:
        def __init__(self):
            self.calls = []

        def invoke(self, action, **params):
            self.calls.append((action, params))
            if action == "version":
                return 6
            if action == "modelNamesAndIds":
                return {"M2A Basic": 1, "M2A Cloze": 2}
            if action == "findNotes":
                return []  # Not found in Anki!
            if action == "modelFieldNames":
                return ["Front", "Back"]
            if action == "addNotes":
                return [5001]
            return None

    fake = FakeSyncAnki()
    monkeypatch.setattr(ankiconnect.AnkiConnect, "invoke", lambda self, action, **p: fake.invoke(action, **p))
    monkeypatch.setattr(ankiconnect.AnkiConnect, "reachable", lambda self: True)

    # 0. Plain sync (no --update) notifies about cards deleted in Anki
    assert run("-c", cfg_file, "sync") == 0
    out = capsys.readouterr().out
    assert "deleted in Anki (still active in vault)" in out

    # 1. By default, missing cards are skipped and hint is shown
    assert run("-c", cfg_file, "sync", "--update") == 0
    out = capsys.readouterr().out
    assert "missing card(s) skipped in Anki" in out
    assert "ADDED: Question Missing %%miss111%%" in note_file.read_text(encoding="utf-8")

    # 2. With --mark-deleted, both basic and image occlusion cards are marked DELETED: in note
    assert run("-c", cfg_file, "sync", "--update", "--mark-deleted") == 0
    out = capsys.readouterr().out
    assert "marked 2 card(s) as DELETED" in out
    txt = note_file.read_text(encoding="utf-8")
    assert "DELETED: Question Missing %%miss111%%" in txt
    assert "DELETED: Image Cloze %%occ222%%" in txt

    # 3. With --recreate-missing (revert to ADDED first)
    note_file.write_text(note_content, encoding="utf-8")
    assert run("-c", cfg_file, "sync", "--recreate-missing", "--yes") == 0
    out = capsys.readouterr().out
    assert "1 added" in out
    assert any(a == "addNotes" for a, p in fake.calls)

def test_sync_summary_output(vault, capsys):
    v, cfg_path = vault
    assert run("-c", cfg_path, "sync", "--yes", "--target", "apkg") == 0
    out = capsys.readouterr().out
    assert "Sync Summary:" in out
    assert "added" in out



def test_help_panels_and_hidden_check(capsys):
    assert run("--help") == 0
    out = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", capsys.readouterr().out)
    assert "Core Workflow" in out
    assert "Setup & Configuration" in out
    assert "Maintenance & Cleanup" in out
    # check should be hidden in the main help overview
    assert re.search(r"^\s*check\s+", out, re.M) is None
    # but still accessible directly
    assert run("check", "--help") == 0
    check_help = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", capsys.readouterr().out)
    assert "Usage: m2a check" in check_help


def test_summary_line_and_broken_pipe(monkeypatch):
    from markdown2anki.commands._shared import summary_line
    from markdown2anki.parser import Diagnostic, LEVEL_ERROR, LEVEL_WARNING
    from pathlib import Path

    healthy = summary_line([])
    assert "✓ Vault healthy" in healthy
    assert "0 errors, 0 warnings" in healthy

    diag_err = Diagnostic(Path("test.md"), 10, LEVEL_ERROR, "Broken image")
    diag_warn = Diagnostic(Path("test.md"), 12, LEVEL_WARNING, "Loose whitespace")
    summary = summary_line([diag_err, diag_warn], skipped_count=1)
    assert "✗" in summary
    assert "1 error" in summary
    assert "1 warning" in summary
    assert "1 card would be skipped during sync" in summary

    # BrokenPipeError exit code 0
    import markdown2anki.cli
    def mock_app(**kwargs):
        raise BrokenPipeError()
    monkeypatch.setattr(markdown2anki.cli, "app", mock_app)
    assert run("status") == 0


def test_status_healthy_vs_broken_vault(vault, capsys):
    v, cfg_path = vault
    # Healthy vault
    assert run("-c", cfg_path, "status") == 0
    out = capsys.readouterr().out
    assert "✓ Vault healthy" in out
    assert "0 errors, 0 warnings" in out

    # Broken card in vault (missing image produces an error diagnostic in build)
    broken_note = v / "50.054 Compiler" / "Anki - Lectures" / "broken.md"
    broken_note.write_text("---\nQuestion\n![[nonexistent_image.png]]\n", encoding="utf-8")
    assert run("-c", cfg_path, "status") == 1
    out = capsys.readouterr().out
    assert "✗ 1 error" in out
    assert "1 card would be skipped during sync" in out


def test_status_deleted_cards_not_counted_as_pending(vault, capsys):
    v, cfg_path = vault
    note = v / "50.054 Compiler" / "Anki - Lectures" / "W01 Intro.md"
    # Append a DELETED card
    content = note.read_text(encoding="utf-8") + "\n---\nDELETED: Old Question %%old123%%\nOld Answer\n"
    note.write_text(content, encoding="utf-8")

    assert run("-c", cfg_path, "status") == 0
    out = capsys.readouterr().out
    # Total cards in summary: 4 active + 1 deleted
    assert "cards 4" in out
    assert "pending 3" in out
    assert "added 1" in out
    assert "deleted 1" in out


def test_status_verbose_shows_card_states(vault, capsys):
    v, cfg_path = vault
    note = v / "50.054 Compiler" / "Anki - Lectures" / "W01 Intro.md"
    content = note.read_text(encoding="utf-8") + "\n---\nDELETED: Old Question %%old123%%\nOld Answer\n"
    note.write_text(content, encoding="utf-8")

    assert run("-c", cfg_path, "status", "-v") == 0
    out = capsys.readouterr().out
    assert "new" in out
    assert "added" in out
    assert "deleted" in out
