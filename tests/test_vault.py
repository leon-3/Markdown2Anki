from pathlib import Path
from markdown2anki.config import Config
from markdown2anki.vault import discover, normalize_rel_parts, resolve_deck_for_parts, resolve_tags_for_parts


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
