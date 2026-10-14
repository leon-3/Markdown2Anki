from pathlib import Path
import markdown2anki
from markdown2anki import (
    Card,
    Diagnostic,
    parse_lines,
    parse_file,
    build,
    BuildResult,
    RenderedNote,
    render_markdown,
    export_apkg,
    ApkgExport,
    export_ankiconnect,
    AnkiExport,
    AnkiConnect,
    AnkiConnectError,
    write_flags,
    clear_flags,
)


def test_public_api_exports():
    """Verify all expected symbols are accessible directly from markdown2anki."""
    for symbol in [
        "Card",
        "Diagnostic",
        "parse_file",
        "parse_lines",
        "build",
        "BuildResult",
        "RenderedNote",
        "render_markdown",
        "export_apkg",
        "ApkgExport",
        "export_ankiconnect",
        "AnkiExport",
        "AnkiConnect",
        "AnkiConnectError",
        "write_flags",
        "clear_flags",
    ]:
        assert hasattr(markdown2anki, symbol), f"Missing symbol: {symbol}"


def test_parse_and_build_standalone(tmp_path):
    """Test parse_lines and build purely through the public API."""
    lines = [
        "# Chapter 1",
        "---",
        "What is 2 + 2?",
        "It is 4.",
        "---",
        "Cloze",
        "The capital of France is {{c1::Paris}}.",
    ]
    test_file = tmp_path / "notes.md"
    test_file.write_text("\n".join(lines), encoding="utf-8")

    diagnostics = []
    cards = parse_file(test_file, base_tag="Math", diagnostics=diagnostics)
    assert len(cards) == 2
    assert cards[0].question == "What is 2 + 2?"
    assert cards[0].pending is True
    assert cards[0].tag == "Math::notes::Chapter_1"

    result = build(cards, diagnostics=diagnostics, cloze_notes=True)
    assert len(result.notes) == 2
    assert result.notes[0].model == "basic"
    assert "What is 2 + 2?" in result.notes[0].fields[0]
    assert result.notes[1].model == "cloze"


def test_export_apkg_standalone(tmp_path):
    """Test export_apkg without requiring a Config instance."""
    cards = parse_lines(
        ["---", "Question 1", "Answer 1", "---", "Question 2", "Answer 2"],
        file=tmp_path / "test.md",
        base_tag="Test",
    )
    result = build(cards)
    out_apkg = tmp_path / "custom.apkg"

    export = export_apkg(result, output_path=out_apkg, deck="My Custom Deck")
    assert isinstance(export, ApkgExport)
    assert export.note_count == 2
    assert out_apkg.is_file()
    assert out_apkg.stat().st_size > 0
    assert len(export.flags) == 2


def test_flagging_helpers(tmp_path):
    """Test write_flags and clear_flags via the public API."""
    file_path = tmp_path / "flag_test.md"
    file_path.write_text("---\nQuestion\nAnswer\n", encoding="utf-8")

    cards = parse_file(file_path, base_tag="Test")
    assert cards[0].pending is True

    # Flag using write_flags
    flagged_count, problems = write_flags([(cards[0], "abc123")])
    assert flagged_count == 1
    assert not problems
    assert "ADDED: Question %%abc123%%" in file_path.read_text(encoding="utf-8")

    # Reparse
    reparsed = parse_file(file_path, base_tag="Test")
    assert reparsed[0].pending is False
    assert reparsed[0].card_id == "abc123"

    # Unflag using clear_flags
    cleared_count, problems = clear_flags(reparsed)
    assert cleared_count == 1
    assert not problems
    assert "ADDED" not in file_path.read_text(encoding="utf-8")
