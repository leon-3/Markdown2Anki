from pathlib import Path

from markdown2anki.parser import KIND_BASIC, KIND_CLOZE, KIND_IMAGE_OCCLUSION, parse_lines

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
