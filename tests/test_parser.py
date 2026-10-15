from pathlib import Path

from markdown2anki.flags import clear_flags, write_flags
from markdown2anki.parser import KIND_BASIC, KIND_CLOZE, KIND_IMAGE_OCCLUSION, parse_file, parse_lines

F = Path("W01 Intro.md")


def parse(text, base="SUTD::50.054_Compiler::Lectures"):
    diags = []
    cards = parse_lines(text.split("\n"), F, base, diagnostics=diags)
    return cards, diags


def test_basic_card_and_tags():
    cards, diags = parse("# Intro\n---\nWhat is X?\nEQL: more question\nAnswer line 1\nAnswer line 2\n")
    assert len(cards) == 1 and not diags
    c = cards[0]
    assert c.question == "What is X?\nmore question"
    assert c.answer == "Answer line 1\nAnswer line 2"
    assert c.tag == "SUTD::50.054_Compiler::Lectures::W01_Intro::Intro"
    assert c.line == 3
    assert c.kind == KIND_BASIC and not c.added


def test_heading_levels_and_hash_in_heading():
    text = "# C# Basics\n---\nq1\na1\n## Sub\n---\nq2\na2\n### Deep\n---\nq3\na3\n# Other\n---\nq4\na4\n"
    cards, _ = parse(text, base="B")
    assert [c.tag for c in cards] == [
        "B::W01_Intro::C#_Basics",
        "B::W01_Intro::C#_Basics::Sub",
        "B::W01_Intro::C#_Basics::Sub::Deep",
        "B::W01_Intro::Other",
    ]


def test_single_character_file_name_does_not_crash():
    cards, _ = parse_lines(["---", "q", "a"], Path("1.md"), "B"), None
    assert cards[0].tag == "B::01"


def test_added_prefixes():
    text = ("---\nADDED: old\nx\n---\nADDED[7f3a9c2e]: hex\nx\n---\nADDED[n1694687123456]: anki\nx\n"
            "---\nADDED: current %%k3f9qz%%\nx\n---\nnew\nx")
    cards, _ = parse(text)
    assert [(c.added, c.card_id, c.question) for c in cards] == [
        (True, None, "old"), (True, "7f3a9c2e", "hex"), (True, "n1694687123456", "anki"),
        (True, "k3f9qz", "current"), (False, None, "new")]
    assert [c.updatable for c in cards] == [False, True, True, True, False]


def test_cloze_kinds():
    text = "---\nCloze\nThe {{c1::answer}} is here\n---\ncloze\nno markers\n---\nImage Cloze\n![[img.png]]\n---\nCloze Image\ntext only"
    cards, diags = parse(text)
    assert [c.kind for c in cards] == [KIND_CLOZE, KIND_CLOZE, KIND_IMAGE_OCCLUSION, KIND_IMAGE_OCCLUSION]
    assert cards[0].has_cloze_markers and not cards[1].has_cloze_markers
    assert any("image cloze without an image" in d.message for d in diags)


def test_template_slots_and_orphan_answers():
    text = "---\n\n\n\n---\n\n\n---\nq\na\n---\n\nstray text\n"
    cards, diags = parse(text)
    assert len(cards) == 1
    assert [d.line for d in diags if d.level == "error"] == [13]


def test_code_block_protects_headings_and_separators():
    text = "---\nq\n```python\n# not a heading\n---\nstill code\n```\nafter\n"
    cards, diags = parse(text)
    assert len(cards) == 1 and not diags
    assert "# not a heading" in cards[0].answer and "after" in cards[0].answer


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


def test_yaml_frontmatter_is_ignored_and_not_parsed_as_card(tmp_path):
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
    assert len(cards) == 1
    assert cards[0].question == "What is a sample space?"
    assert cards[0].answer == "The set of all possible outcomes."
    # Line 1: ---, 2: tags, 3: aliases, 4: date, 5: ---, 6: # ..., 7: ---, 8: Question
    assert cards[0].line == 8


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
    assert b"ADDED: Question 1 %%abc123%%" in raw

    # Clearing flags should also preserve CRLF
    cards_reloaded = parse_file(note, "Base")
    cleared, problems = clear_flags([cards_reloaded[0]])
    assert cleared == 1 and not problems
    raw_cleared = note.read_bytes()
    assert b"\r\n" in raw_cleared
    assert not any(b"\n" in l for l in raw_cleared.split(b"\r\n"))
