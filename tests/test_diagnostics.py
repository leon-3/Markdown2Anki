from pathlib import Path
import pytest

from markdown2anki.config import Config
from markdown2anki.diagnostics import Diagnostic, DiagnosticCategory, DiagnosticLevel
from markdown2anki.ui import format_diagnostic_cli, level
from markdown2anki.commands._shared import print_diagnostics


def test_diagnostic_immutability():
    d = Diagnostic(
        file=Path("test.md"),
        line=10,
        level=DiagnosticLevel.ERROR,
        category=DiagnosticCategory.SYNTAX,
        message="Test error",
        suggestion="Test suggestion",
    )
    with pytest.raises(AttributeError):
        d.message = "New message"


def test_diagnostic_location_label():
    d_with_line = Diagnostic(Path("note.md"), line=42, level=DiagnosticLevel.WARNING, message="Warn")
    assert d_with_line.location_label == "note.md:42"

    d_without_line = Diagnostic(Path("note.md"), line=None, level=DiagnosticLevel.ERROR, message="File error")
    assert d_without_line.location_label == "note.md"

    d_zero_line = Diagnostic(Path("note.md"), line=0, level=DiagnosticLevel.ERROR, message="File error")
    assert d_zero_line.location_label == "note.md"


def test_to_obsidian_uri(tmp_path):
    vault_root = tmp_path / "My Vault"
    vault_root.mkdir()
    (vault_root / ".obsidian").mkdir()

    subfolder = vault_root / "Lectures & Notes"
    subfolder.mkdir()
    note_file = subfolder / "Lecture #1 [Draft].md"
    note_file.write_text("content", encoding="utf-8")

    diag = Diagnostic(
        file=note_file,
        line=15,
        level=DiagnosticLevel.ERROR,
        category=DiagnosticCategory.SYNTAX,
        message="Bad syntax",
    )

    uri = diag.to_obsidian_uri(vault_root=subfolder)
    assert "obsidian://open?vault=My%20Vault&file=" in uri
    assert "Lectures%20%26%20Notes%2FLecture%20%231%20%5BDraft%5D.md" in uri


def test_to_obsidian_uri_fallback(tmp_path):
    note_file = tmp_path / "Standalone Note.md"
    note_file.write_text("content", encoding="utf-8")

    diag = Diagnostic(
        file=note_file,
        line=5,
        level=DiagnosticLevel.WARNING,
        message="Warning",
    )

    uri = diag.to_obsidian_uri()
    assert uri.startswith("obsidian://open?path=")
    assert "Standalone%20Note.md" in uri


def test_format_diagnostic_cli():
    diag = Diagnostic(
        file=Path("My [red] Note.md"),
        line=10,
        level=DiagnosticLevel.ERROR,
        category=DiagnosticCategory.SYNTAX,
        message="Unescaped [tag] inside",
        suggestion="Wrap in `backticks`",
    )
    formatted = format_diagnostic_cli(diag)
    assert "[red]●[/]" in formatted
    assert r"\[tag]" in formatted
    assert r"\[red]" in formatted
    assert "Tip: Wrap in `backticks`" in formatted


def test_ui_level_formatting():
    assert level(DiagnosticLevel.ERROR) == "[red]error  [/]"
    assert level(DiagnosticLevel.WARNING) == "[yellow]warning[/]"
    assert level(DiagnosticLevel.INFO) == "[dim]info   [/]"
    assert level("error") == "[red]error  [/]"
    assert "DiagnosticLevel" not in level(DiagnosticLevel.ERROR)


def test_print_diagnostics_formatting(capsys):
    cfg = Config(vault=Path("/vault"))
    diag = Diagnostic(
        file=Path("/vault/test.md"),
        line=2,
        level=DiagnosticLevel.ERROR,
        message="Syntax issue",
        suggestion="Fix syntax",
    )
    errors = print_diagnostics([diag], cfg)
    assert errors == 1
    out = capsys.readouterr().out
    assert "error" in out
    assert "DiagnosticLevel" not in out
    assert "test.md:2" in out
    assert "Tip: Fix syntax" in out
