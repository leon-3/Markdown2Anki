from pathlib import Path

from markdown2anki.build import build
from markdown2anki.parser import parse_lines


def _cards(tmp_path, folder, text):
    note = tmp_path / folder / "n.md"
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text(text, encoding="utf-8")
    return parse_lines(text.split("\n"), note, "B")


def test_media_name_clash_skips_the_second_card(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "a" / "img.png").write_bytes(b"one")
    (tmp_path / "b" / "img.png").write_bytes(b"two")
    cards = _cards(tmp_path, "a", "---\nq\n![[img.png]]\n") + _cards(tmp_path, "b", "---\nq\n![[img.png]]\n")
    diagnostics = []
    result = build(cards, diagnostics)
    assert len(result.notes) == 1 and result.skipped == [cards[1]]
    assert "media name clash" in diagnostics[0].message


def test_identical_media_in_two_folders_is_fine(tmp_path):
    for folder in ("a", "b"):
        (tmp_path / folder).mkdir()
        (tmp_path / folder / "img.png").write_bytes(b"same")
    cards = _cards(tmp_path, "a", "---\nq\n![[img.png]]\n") + _cards(tmp_path, "b", "---\nq\n![[img.png]]\n")
    result = build(cards, [])
    assert len(result.notes) == 2 and len(result.media) == 2


def test_unknown_html_tag_is_reported(tmp_path):
    cards = _cards(tmp_path, "a", "---\nq\nreturns <actual_type> here\n")
    diagnostics = []
    build(cards, diagnostics)
    assert any("<actual_type>" in d.message for d in diagnostics)
    cards = _cards(tmp_path, "a", "---\nq\n`<actual_type>` and **bold**\n")
    diagnostics = []
    build(cards, diagnostics)
    assert not diagnostics
