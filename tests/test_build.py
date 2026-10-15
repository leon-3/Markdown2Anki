from pathlib import Path

from markdown2anki.build import build, resolve_image_path
from markdown2anki.constants import CODE_TAG
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


def test_resolve_image_in_attachments_folder(tmp_path):
    note_dir = tmp_path / "notes"
    att_dir = note_dir / "attachments"
    att_dir.mkdir(parents=True)
    img_file = att_dir / "diagram.png"
    img_file.write_bytes(b"image data")

    cards = _cards(tmp_path, "notes", "---\nWhat is this?\n![[diagram.png]]\n")
    diagnostics = []
    result = build(cards, diagnostics)
    assert not diagnostics
    assert len(result.notes) == 1
    assert result.notes[0].media == [img_file.resolve()]
    assert '<img src="diagram.png">' in result.notes[0].fields[1]


def test_obsidian_image_resizing(tmp_path):
    note_dir = tmp_path / "notes"
    att_dir = note_dir / "attachments"
    att_dir.mkdir(parents=True)
    (att_dir / "schema.png").write_bytes(b"img")

    # Width only
    cards = _cards(tmp_path, "notes", "---\nQ1\n![[schema.png|400]]\n")
    res = build(cards, [])
    assert '<img src="schema.png" width="400">' in res.notes[0].fields[1]

    # Width and height
    cards2 = _cards(tmp_path, "notes", "---\nQ2\n![[schema.png|400x200]]\n")
    res2 = build(cards2, [])
    assert '<img src="schema.png" width="400" height="200">' in res2.notes[0].fields[1]

    # Multiple pipe tags e.g. alt text and width
    cards3 = _cards(tmp_path, "notes", "---\nQ3\n![[schema.png|my alt|300]]\n")
    res3 = build(cards3, [])
    assert '<img src="schema.png" width="300">' in res3.notes[0].fields[1]


def test_fenced_code_block_gets_code_tag(tmp_path):
    cards = _cards(tmp_path, "notes", "---\nQuestion\n```python\nprint('hello')\n```\n")
    result = build(cards, [])
    assert len(result.notes) == 1
    assert CODE_TAG in result.notes[0].tags


def test_inline_code_does_not_get_code_tag(tmp_path):
    cards = _cards(tmp_path, "notes", "---\nQuestion\nInline `code` only\n")
    result = build(cards, [])
    assert len(result.notes) == 1
    assert CODE_TAG not in result.notes[0].tags
