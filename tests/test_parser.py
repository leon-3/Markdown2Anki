from pathlib import Path

from markdown2anki.flags import clear_flags, write_flags
from markdown2anki.parser import (
    Diagnostic,
    format_tag_segment,
    parse_file,
    parse_lines,
    LEVEL_WARNING,
)


def parse(text: str) -> tuple[list, list[Diagnostic]]:
    diagnostics: list[Diagnostic] = []
    return parse_lines(text.split("\n"), Path("test.md"), "T", diagnostics=diagnostics), diagnostics


def test_basic_two_cards():
    cards, diags = parse("---\nWhat is a?\nA\n---\nWhat is b?\nB\n")
    assert len(cards) == 2
    assert cards[0].question == "What is a?" and cards[0].answer == "A"
    assert cards[1].question == "What is b?" and cards[1].answer == "B"
    assert not diags


def test_multiline_question_with_eql():
    cards, _ = parse("---\nWhat is a?\nEQL: Really?\nYes.\n")
    assert cards[0].question == "What is a?\nReally?"
    assert cards[0].answer == "Yes."


def test_heading_sets_tag():
    cards, _ = parse("# Topic\n---\nQ\nA\n## Subtopic\n---\nQ2\nA2\n")
    assert cards[0].tag == "T::test::Topic"
    assert cards[1].tag == "T::test::Topic::Subtopic"


def test_code_block_fence_ignores_separators_inside():
    cards, _ = parse("---\nQ\n```\n---\n# not a heading\n```\n")
    assert len(cards) == 1
    assert "---\n# not a heading" in cards[0].answer


def test_card_id_extracted_when_present():
    cards, _ = parse("---\nADDED: Q %%c12345%%\nA\n")
    assert cards[0].added
    assert cards[0].card_id == "c12345"
    assert cards[0].question == "Q"


def test_kind_detection():
    c_basic, _ = parse("---\nNormal Q\nA\n")
    assert c_basic[0].kind == "basic"

    c_cloze, _ = parse("---\nCloze\nThe {{c1::sky}} is blue.\n")
    assert c_cloze[0].kind == "cloze"

    c_img, _ = parse("---\nImage Cloze\n![[brain.png]]\n")
    assert c_img[0].kind == "image_occlusion"


def test_text_outside_card_emits_error():
    _, diags = parse("random text\n---\nQ\nA\n")
    assert len(diags) == 1
    assert "text outside a card" in diags[0].message


def test_empty_answer_warns():
    _, diags = parse("---\nQ\n---\nQ2\nA2\n")
    assert any("empty answer" in d.message for d in diags)


def test_cloze_markers_in_basic_warns():
    _, diags = parse("---\nNot Cloze\nA {{c1::test}}\n")
    assert any("cloze markers" in d.message for d in diags)


def test_image_cloze_without_image_errors():
    _, diags = parse("---\nImage Cloze\nno image here\n")
    assert any("image cloze without an image" in d.message for d in diags)


def test_code_keyword_detected():
    cards, _ = parse("---\nq\n```c\n#CODE#\nint x;\n```\n")
    assert cards[0].has_code


def test_fenced_code_block_in_answer_detected_as_code():
    cards, _ = parse("---\nQuestion\n```python\ndef hello():\n    return 'world'\n```\n")
    assert cards[0].has_code


def test_fenced_code_block_in_question_detected_as_code():
    cards, _ = parse("---\nWhat does this do?\nEQL: ```python\nEQL: print(1)\nEQL: ```\nAnswer\n")
    assert cards[0].has_code


def test_inline_code_not_detected_as_code():
    cards, _ = parse("---\nQuestion\nUse `x = 1` here\n")
    assert not cards[0].has_code


def test_leading_separator_with_metadata_parsed_as_regular_card(tmp_path):
    note = tmp_path / "note.md"
    note.write_text(
        "---\n"
        "tags: [math, probability]\n"
        "aliases: [PT]\n"
        "date: 2026-10-15\n"
        "---\n"
        "# Probability Theory\n"
        "---\n"
        "What is a sample space?\n"
        "The set of all possible outcomes.\n",
        encoding="utf-8",
    )
    cards = parse_file(note, "Base")
    assert len(cards) == 2
    assert cards[0].question == "tags: [math, probability]"
    assert cards[0].answer == "aliases: [PT]\ndate: 2026-10-15"
    assert cards[0].line == 2
    assert cards[1].question == "What is a sample space?"
    assert cards[1].answer == "The set of all possible outcomes."
    assert cards[1].line == 8


def test_file_without_frontmatter_works_normally(tmp_path):
    # Scenario 1: Note starting with a heading, then separator
    note1 = tmp_path / "with_heading.md"
    note1.write_text(
        "# Discrete Mathematics\n"
        "---\n"
        "What is a bijection?\n"
        "A function that is both injective and surjective.\n",
        encoding="utf-8",
    )
    cards1 = parse_file(note1, "Base")
    assert len(cards1) == 1
    assert cards1[0].line == 3
    assert cards1[0].question == "What is a bijection?"
    assert cards1[0].tag == "Base::with_heading::Discrete_Mathematics"

    # Scenario 2: Note starting directly with --- as the very first line (no frontmatter)
    note2 = tmp_path / "starts_with_separator.md"
    note2.write_text(
        "---\n"
        "Question 1\n"
        "Answer 1\n"
        "---\n"
        "Question 2\n"
        "Answer 2\n",
        encoding="utf-8",
    )
    cards2 = parse_file(note2, "Base")
    assert len(cards2) == 2
    assert cards2[0].line == 2
    assert cards2[0].question == "Question 1"
    assert cards2[1].line == 5
    assert cards2[1].question == "Question 2"

    # Flagging and unflagging work without issue
    flagged, problems = write_flags([(cards2[0], "c11111"), (cards2[1], "c22222")])
    assert flagged == 2 and not problems
    reloaded = parse_file(note2, "Base")
    assert [c.added for c in reloaded] == [True, True]
    assert [c.card_id for c in reloaded] == ["c11111", "c22222"]

    cleared, problems = clear_flags(reloaded)
    assert cleared == 2 and not problems
    assert [c.added for c in parse_file(note2, "Base")] == [False, False]


def test_crlf_line_endings_preserved_when_flagging(tmp_path):
    note = tmp_path / "crlf_note.md"
    content = "---\r\nQuestion 1\r\nAnswer 1\r\n---\r\nQuestion 2\r\nAnswer 2\r\n"
    note.write_bytes(content.encode("utf-8"))

    cards = parse_file(note, "Base")
    assert len(cards) == 2
    assert cards[0].line == 2
    assert cards[1].line == 5

    flagged, problems = write_flags([(cards[0], "abc123")])
    assert flagged == 1 and not problems

    # File must still strictly use CRLF line endings
    raw = note.read_bytes()
    assert b"\r\n" in raw
    # Every line must end in CRLF, no bare LF
    lines = raw.split(b"\r\n")
    assert not any(b"\n" in l for l in lines)


def test_format_tag_segment_boundaries():
    # Isolated single digit
    assert format_tag_segment("1", pad_single_digits=True) == "01"
    assert format_tag_segment("1", pad_single_digits=False) == "1"
    # Single digit with delimiter
    assert format_tag_segment("1. Intro", pad_single_digits=True) == "01_Intro"
    assert format_tag_segment("1. Intro", pad_single_digits=False) == "1_Intro"
    assert format_tag_segment("2-Part", pad_single_digits=True) == "02-Part"
    # Already padded or multi-digit
    assert format_tag_segment("01", pad_single_digits=True) == "01"
    assert format_tag_segment("10", pad_single_digits=True) == "10"
    # Alphanumeric terms must not have false-positive padding
    assert format_tag_segment("2D Geometry", pad_single_digits=True) == "2D_Geometry"
    assert format_tag_segment("3D Rendering", pad_single_digits=True) == "3D_Rendering"
    assert format_tag_segment("1st Law", pad_single_digits=True) == "1st_Law"
    assert format_tag_segment("3Blue1Brown", pad_single_digits=True) == "3Blue1Brown"
    # Decimal numbers / dot preservation
    assert format_tag_segment("50.054", pad_single_digits=True) == "50.054"


def test_code_fence_with_symbols_and_attributes():
    text = (
        "---\n"
        "Question 1\n"
        "```c++\n"
        "int x = 1;\n"
        "---\n"
        "```\n"
        "---\n"
        "Question 2\n"
        "```python {linenos=true}\n"
        "def foo(): pass\n"
        "```\n"
    )
    cards, diags = parse(text)
    assert not diags
    assert len(cards) == 2
    assert cards[0].question == "Question 1"
    assert cards[1].question == "Question 2"


def test_code_fence_nested_lengths():
    text = (
        "---\n"
        "Question Outer\n"
        "````markdown\n"
        "```python\n"
        "inner_code = True\n"
        "---\n"
        "```\n"
        "````\n"
        "---\n"
        "Question Next\n"
        "Answer Next\n"
    )
    cards, diags = parse(text)
    assert not diags
    assert len(cards) == 2
    assert cards[0].question == "Question Outer"
    assert "inner_code = True" in cards[0].answer
    assert cards[1].question == "Question Next"


def test_unclosed_code_fence_emits_warning():
    text = (
        "---\n"
        "Question 1\n"
        "```python\n"
        "unclosed code\n"
    )
    cards, diags = parse(text)
    assert len(cards) == 1
    assert any(d.level == LEVEL_WARNING and "unclosed code fence" in d.message for d in diags)


def test_mixed_line_endings_in_parse_file(tmp_path):
    note = tmp_path / "mixed.md"
    content = "---\r\nQuestion 1\nAnswer 1\r\n---\nQuestion 2\r\nAnswer 2\n"
    note.write_bytes(content.encode("utf-8"))
    cards = parse_file(note, "Base")
    assert len(cards) == 2
    assert "\r" not in cards[0].question
    assert "\r" not in cards[0].answer
    assert "\r" not in cards[1].question
    assert "\r" not in cards[1].answer


def test_eql_inside_answer_does_not_mutate_question():
    text = (
        "---\n"
        "Question 1\n"
        "Answer line 1\n"
        "EQL: this is part of the answer\n"
        "Answer line 2\n"
    )
    cards, _ = parse(text)
    assert len(cards) == 1
    assert cards[0].question == "Question 1"
    assert "EQL: this is part of the answer" in cards[0].answer


def test_prose_keywords_do_not_trigger_has_code():
    cards, _ = parse(
        "---\n"
        "What is the policy?\n"
        "Please return the book to the library for the class of 2026 and import goods.\n"
    )
    assert len(cards) == 1
    assert cards[0].has_code is False

def test_deleted_prefix_parsing_and_flagging(tmp_path):
    from markdown2anki.build import build
    from markdown2anki.flags import clear_flags, write_deleted_flags, write_flags

    note = tmp_path / "deleted_card.md"
    content = (
        "---\n"
        "DELETED: Question 1 %%k3f9qz%%\n"
        "Answer 1\n"
        "---\n"
        "ADDED: Question 2 %%a1b2c3%%\n"
        "Answer 2\n"
    )
    note.write_text(content, encoding="utf-8")

    cards = parse_file(note, "Base")
    assert len(cards) == 2

    # Card 1 is deleted
    assert cards[0].deleted is True
    assert cards[0].added is False
    assert cards[0].card_id == "k3f9qz"
    assert cards[0].question == "Question 1"
    assert cards[0].pending is False
    assert cards[0].updatable is False

    # Card 2 is added (regular active card)
    assert cards[1].deleted is False
    assert cards[1].added is True
    assert cards[1].card_id == "a1b2c3"
    assert cards[1].question == "Question 2"
    assert cards[1].updatable is True

    # Build skips deleted card
    res = build(cards, [])
    assert len(res.notes) == 1
    assert res.notes[0].card.card_id == "a1b2c3"

    # Test write_deleted_flags converts Card 2 to DELETED:
    flagged, problems = write_deleted_flags([cards[1]])
    assert flagged == 1 and not problems
    reloaded = parse_file(note, "Base")
    assert reloaded[1].deleted is True
    assert reloaded[1].card_id == "a1b2c3"
    assert "DELETED: Question 2 %%a1b2c3%%" in note.read_text(encoding="utf-8")

    # Test clear_flags reverts both cards to clean questions
    cleared, problems = clear_flags(reloaded)
    assert cleared == 2 and not problems
    clean_cards = parse_file(note, "Base")
    assert clean_cards[0].deleted is False and clean_cards[0].added is False
    assert clean_cards[1].deleted is False and clean_cards[1].added is False
