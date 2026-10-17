from pathlib import Path
import unicodedata
from markdown2anki.config import Config
from markdown2anki.parser import parse_file
from markdown2anki.vault import collect, discover, normalize_rel_parts, resolve_deck_for_parts, resolve_tags_for_parts


def test_normalize_rel_parts():
    assert normalize_rel_parts(None) == ()
    assert normalize_rel_parts("") == ()
    assert normalize_rel_parts(".") == ()
    assert normalize_rel_parts("./") == ()
    assert normalize_rel_parts("TopicA") == ("TopicA",)
    assert normalize_rel_parts("TopicA/") == ("TopicA",)
    assert normalize_rel_parts("TopicA/SubtopicB") == ("TopicA", "SubtopicB")
    assert normalize_rel_parts("TopicA\\SubtopicB") == ("TopicA", "SubtopicB")
    assert normalize_rel_parts("./TopicA/SubtopicB/.") == ("TopicA", "SubtopicB")


def test_resolve_deck_for_parts():
    rules = {
        "TopicA": "DeckA",
        "TopicA/SubtopicB": "DeckB",
        "TopicC": "DeckC",
    }
    # Root level
    assert resolve_deck_for_parts((), rules, "Default") == "Default"
    # Exact match
    assert resolve_deck_for_parts(("TopicA",), rules, "Default") == "DeckA"
    # Longest prefix match wins
    assert resolve_deck_for_parts(("TopicA", "SubtopicB"), rules, "Default") == "DeckB"
    assert resolve_deck_for_parts(("TopicA", "SubtopicB", "Detail"), rules, "Default") == "DeckB"
    # Subfolder inherits parent rule if no deeper rule exists
    assert resolve_deck_for_parts(("TopicA", "OtherSub"), rules, "Default") == "DeckA"
    # Boundary matching: TopicAdvanced must not match TopicA
    assert resolve_deck_for_parts(("TopicAdvanced",), rules, "Default") == "Default"


def test_resolve_tags_for_parts():
    aliases = {
        "01. TopicA": "01_topica",
        "TopicB/SubtopicC": "SubtopicC",
        "Archive": "",
        "Domain": "Custom::Hierarchy",
    }
    # Unaliased segment with single-digit padding
    assert resolve_tags_for_parts(("1. Intro",), "Base", aliases, pad_single_digits=True) == "Base::01_Intro"
    assert resolve_tags_for_parts(("1. Intro",), "Base", aliases, pad_single_digits=False) == "Base::1_Intro"
    # Alphanumeric terms must not have false-positive padding
    assert resolve_tags_for_parts(("2D Geometry",), "Base", aliases, pad_single_digits=True) == "Base::2D_Geometry"
    assert resolve_tags_for_parts(("1st Law",), "Base", aliases, pad_single_digits=True) == "Base::1st_Law"
    # Explicit single-segment alias
    assert resolve_tags_for_parts(("01. TopicA", "Detail"), "Base", aliases) == "Base::01_topica::Detail"
    # Prefix alias replacement (single-pass greedy)
    assert resolve_tags_for_parts(("TopicB", "SubtopicC", "Deep"), "Base", aliases) == "Base::SubtopicC::Deep"
    # Segment suppression
    assert resolve_tags_for_parts(("Archive", "TopicD"), "Base", aliases) == "Base::TopicD"
    # Hierarchical explicit alias
    assert resolve_tags_for_parts(("Domain", "Unit1"), "", aliases) == "Custom::Hierarchy::Unit1"
    # Root level: returns only base_tag (no bogus _ tag)
    assert resolve_tags_for_parts((), "Base", aliases) == "Base"
    assert resolve_tags_for_parts((), "", aliases) == ""


def test_recursive_discovery_and_routing(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    # Note at root
    (vault / "root_note.md").write_text("---\nQ0\nA0\n", encoding="utf-8")
    # Nested notes
    deep_dir = vault / "TopicA" / "SubtopicB" / "Unit1"
    deep_dir.mkdir(parents=True)
    (deep_dir / "deep.md").write_text("---\nQ1\nA1\n", encoding="utf-8")
    other_dir = vault / "TopicA" / "Other"
    other_dir.mkdir(parents=True)
    (other_dir / "other.md").write_text("---\nQ2\nA2\n", encoding="utf-8")
    ignored_dir = vault / "Archive" / "Sub"
    ignored_dir.mkdir(parents=True)
    (ignored_dir / "ignored.md").write_text("---\nQ3\nA3\n", encoding="utf-8")

    cfg = Config(
        vault=vault,
        deck="DefaultDeck",
        base_tag="RootTag",
        pad_single_digit_tags=True,
        ignore=[".git", ".obsidian", "Archive"],
        deck_routing={
            "TopicA": "DeckA",
            "TopicA/SubtopicB": "DeckB",
        },
        tag_aliases={
            "TopicA/SubtopicB": "SubtopicB",
        },
    )

    sources = discover(cfg)
    # 3 notes discovered (Archive is ignored)
    assert len(sources) == 3
    sources_by_file = {s.path.name: s for s in sources}

    # Root note
    root_s = sources_by_file["root_note.md"]
    assert root_s.deck == "DefaultDeck"
    assert root_s.base_tag == "RootTag"

    # Deep note with specific routing and tag alias
    deep_s = sources_by_file["deep.md"]
    assert deep_s.deck == "DeckB"
    assert deep_s.base_tag == "RootTag::SubtopicB::Unit1"

    # Other note inheriting TopicA routing
    other_s = sources_by_file["other.md"]
    assert other_s.deck == "DeckA"
    assert other_s.base_tag == "RootTag::TopicA::Other"


def test_directory_pruning_with_glob_suffix(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "note.md").write_text("---\nQ\nA\n", encoding="utf-8")
    arch_dir = vault / "archive" / "old_sub"
    arch_dir.mkdir(parents=True)
    (arch_dir / "arch_note.md").write_text("---\nQ\nA\n", encoding="utf-8")

    cfg = Config(
        vault=vault,
        ignore=["archive/*"],
    )
    sources = discover(cfg)
    assert len(sources) == 1
    assert sources[0].path.name == "note.md"


def test_base_tag_alias_exemption_preserved_in_card_tags(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    lec_dir = vault / "Lectures" / "1. Intro"
    lec_dir.mkdir(parents=True)
    (lec_dir / "2. Basics.md").write_text("# 3. Syntax\n---\nWhat is a grammar?\nSyntax rules.\n", encoding="utf-8")

    cfg = Config(
        vault=vault,
        base_tag="Course",
        pad_single_digit_tags=True,
        tag_aliases={
            # Explicit alias exempt from digit padding (must stay 1_Intro, not 01_Intro)
            "Lectures/1. Intro": "1. Intro",
        },
    )

    collected = collect(cfg)
    assert len(collected.cards) == 1
    card = collected.cards[0]
    # "1. Intro" is the alias (exempt from padding -> "1_Intro")
    # "2. Basics.md" is unaliased file stem (padded -> "02_Basics")
    # "3. Syntax" is unaliased heading (padded -> "03_Syntax")
    assert card.tag == "Course::1_Intro::02_Basics::03_Syntax"
