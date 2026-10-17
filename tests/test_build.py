from pathlib import Path

import hashlib
from markdown2anki.build import build, deterministic_image_name, resolve_image_path
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


def test_export_occlusions_single_folder_sequential_names(tmp_path):
    from markdown2anki.export.apkg import export_occlusions
    from markdown2anki.build import ImageOcclusion
    from markdown2anki.parser import Card

    img1 = tmp_path / "img1.png"
    img2 = tmp_path / "img2.jpg"
    img3 = tmp_path / "img3.png"
    img1.write_bytes(b"data1")
    img2.write_bytes(b"data2")
    img3.write_bytes(b"data3")

    c1 = Card(file=tmp_path / "n1.md", line=1, question="Image Cloze", answer="", tag="Uni::Math::Probability")
    c2 = Card(file=tmp_path / "n2.md", line=1, question="Image Cloze", answer="", tag="Uni::Math::Analysis")

    occlusions = [
        ImageOcclusion(card=c1, images=[img1, img2], tag=c1.tag),
        ImageOcclusion(card=c2, images=[img3], tag=c2.tag),
    ]

    out_dir, flags, staged = export_occlusions(occlusions, tmp_path, prefix="TESTHEX8")

    assert out_dir == tmp_path / "occlusions"
    assert len(flags) == 2
    assert "Uni::Math::Probability" in staged
    assert "Uni::Math::Analysis" in staged

    # Sequential numbering
    assert staged["Uni::Math::Probability"] == ["TESTHEX8_01.png", "TESTHEX8_02.jpg"]
    assert staged["Uni::Math::Analysis"] == ["TESTHEX8_03.png"]

    # All files exist directly in out_dir
    assert (out_dir / "TESTHEX8_01.png").is_file()
    assert (out_dir / "TESTHEX8_02.jpg").is_file()
    assert (out_dir / "TESTHEX8_03.png").is_file()
    assert (out_dir / "TESTHEX8_01.png").read_bytes() == b"data1"


def test_deterministic_image_name(tmp_path):
    img = tmp_path / "My Diagram.PNG"
    img.write_bytes(b"hello image data")
    expected_hash = hashlib.sha256(b"hello image data").hexdigest()[:8].lower()

    name = deterministic_image_name(img)
    assert name == f"{expected_hash}_01.png"

    # Collision test with registry
    reg = {}
    name1 = deterministic_image_name(img, reg)
    assert name1 == f"{expected_hash}_01.png"

    # Same file re-uses candidate
    name1_again = deterministic_image_name(img, reg)
    assert name1_again == f"{expected_hash}_01.png"

    # Fake collision with different bytes in registry
    reg[f"{expected_hash}_01.png"] = b"different data"
    name2 = deterministic_image_name(img, reg)
    assert name2 == f"{expected_hash}_02.png"


def test_build_with_hash_media(tmp_path):
    note_dir = tmp_path / "notes"
    att_dir = note_dir / "attachments"
    att_dir.mkdir(parents=True)
    img_file = att_dir / "Pasted image 20260905091504.png"
    img_file.write_bytes(b"sample bytes")
    expected_hash = hashlib.sha256(b"sample bytes").hexdigest()[:8].lower()
    expected_name = f"{expected_hash}_01.png"

    cards = _cards(tmp_path, "notes", "---\nWhat is Archimedes' Principle?\n![[Pasted image 20260905091504.png|300]]\n")
    diagnostics = []
    result = build(cards, diagnostics, hash_media=True)
    assert not diagnostics
    assert len(result.notes) == 1
    assert result.media == [img_file.resolve()]
    assert result.media_names[img_file.resolve()] == expected_name
    assert f'<img src="{expected_name}" width="300">' in result.notes[0].fields[1]


def test_apkg_with_hash_media(tmp_path):
    import json
    import zipfile
    from markdown2anki.export.apkg import export_apkg

    note_dir = tmp_path / "notes"
    note_dir.mkdir(parents=True)
    img = note_dir / "Schema Diagram.PNG"
    img.write_bytes(b"schema image content")
    expected_hash = hashlib.sha256(b"schema image content").hexdigest()[:8].lower()
    expected_name = f"{expected_hash}_01.png"

    cards = _cards(tmp_path, "notes", "---\nQ?\n![[Schema Diagram.PNG]]\n")
    result = build(cards, [], hash_media=True)
    apkg_out = tmp_path / "out.apkg"
    export = export_apkg(result, apkg_out)
    assert export.media_count == 1

    with zipfile.ZipFile(apkg_out, "r") as z:
        media_json = json.loads(z.read("media").decode("utf-8"))
        assert expected_name in media_json.values()


def test_build_with_url_encoded_image(tmp_path):
    note_dir = tmp_path / "notes"
    note_dir.mkdir(parents=True)
    img_file = note_dir / "My Photo 2026.png"
    img_file.write_bytes(b"photo bytes")

    cards = _cards(tmp_path, "notes", "---\nQuestion\n![[My%20Photo%202026.png]]\n")
    diagnostics = []
    result = build(cards, diagnostics)
    assert not diagnostics
    assert len(result.notes) == 1
    assert result.media == [img_file.resolve()]
    assert '<img src="My Photo 2026.png">' in result.notes[0].fields[1]


def test_build_with_standard_markdown_image(tmp_path):
    note_dir = tmp_path / "notes"
    note_dir.mkdir(parents=True)
    img1 = note_dir / "img1.png"
    img1.write_bytes(b"bytes1")
    img2 = note_dir / "img2.png"
    img2.write_bytes(b"bytes2")

    cards = _cards(
        tmp_path,
        "notes",
        "---\nQuestion\n![Alt text](img1.png)\n![300x200](img2.png)\n",
    )
    diagnostics = []
    result = build(cards, diagnostics)
    assert not diagnostics
    assert len(result.notes) == 1
    assert set(result.media) == {img1.resolve(), img2.resolve()}
    answer = result.notes[0].fields[1]
    assert "<img src=\"img1.png\" alt=\"Alt text\">" in answer
    assert "<img src=\"img2.png\" width=\"300\" height=\"200\">" in answer


def test_build_code_block_isolates_image_syntax(tmp_path):
    cards = _cards(
        tmp_path,
        "notes",
        "---\nQuestion\n"
        "Here is some code:\n"
        "```markdown\n"
        "![[non_existent_img.png]]\n"
        "![alt](missing.png)\n"
        "```\n"
        "And inline `![[inline_missing.png]]` code.\n",
    )
    diagnostics = []
    result = build(cards, diagnostics)
    assert not diagnostics
    assert len(result.notes) == 1
    assert result.media == []
    answer = result.notes[0].fields[1]
    assert "<img" not in answer
    assert "![[non_existent_img.png]]" in answer
    assert "![alt](missing.png)" in answer
    assert "![[inline_missing.png]]" in answer


def test_build_native_image_occlusion(tmp_path):
    from markdown2anki.build import MODEL_IMAGE_OCCLUSION, build
    from markdown2anki.parser import Card, KIND_IMAGE_OCCLUSION
    from markdown2anki.constants import OCCLUSION_TAG

    img = tmp_path / "anatomy.png"
    img.write_bytes(b"anatomy_data")

    card = Card(
        file=tmp_path / "notes.md",
        line=5,
        kind=KIND_IMAGE_OCCLUSION,
        question="Brain Anatomy",
        answer="![[anatomy.png]]",
        tag="Medicine::Neuro",
        deck="Uni::Neuro",
    )

    # 1. Mode stage (default) -> puts card in occlusions list
    res_stage = build([card], vault_root=tmp_path, image_occlusion_mode="stage")
    assert len(res_stage.occlusions) == 1
    assert len(res_stage.notes) == 0

    # 2. Mode native -> puts card in notes list as RenderedNote with 5 fields
    res_native = build([card], vault_root=tmp_path, hash_media=True, image_occlusion_mode="native")
    assert len(res_native.occlusions) == 0
    assert len(res_native.notes) == 1

    note = res_native.notes[0]
    assert note.model == MODEL_IMAGE_OCCLUSION
    assert note.deck == "Uni::Neuro"
    assert "Medicine::Neuro" in note.tags
    assert OCCLUSION_TAG in note.tags

    # 5 fields: ['Occlusion', 'Image', 'Header', 'Back Extra', 'Comments']
    assert len(note.fields) == 5
    assert note.fields[0] == ""  # Occlusion empty
    assert "<img src=" in note.fields[1]
    assert "Brain Anatomy" in note.fields[2]
    assert note.fields[3] == ""  # Back Extra
    assert note.fields[4] == ""  # Comments (ready for <!--m2a:id-->)
    assert note.media == [img]
