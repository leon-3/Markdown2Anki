from pathlib import Path
import sqlite3
import zipfile

import pytest

from markdown2anki.build import BuildResult, RenderedNote, build
from markdown2anki.config import Config
from markdown2anki.export import ankiconnect, apkg
from markdown2anki.parser import Card, parse_lines
from markdown2anki.vault import collect


def test_config_resolve_deck():
    cfg = Config(
        vault=Path("."),
        deck="Uni::{course}",
        decks={"Math": "Special::Math", "Physics": "Science::Physics"},
    )
    # Exact mapping in [decks]
    assert cfg.resolve_deck("Math") == "Special::Math"
    assert cfg.resolve_deck("Physics") == "Science::Physics"
    # Fallback with {course} placeholder
    assert cfg.resolve_deck("Computer Science") == "Uni::Computer_Science"
    # Fallback without {course} placeholder
    cfg_simple = Config(vault=Path("."), deck="General")
    assert cfg_simple.resolve_deck("Math") == "General"


def test_parse_and_build_preserves_deck(tmp_path):
    md_file = tmp_path / "test.md"
    md_file.write_text("# Section\n---\nQuestion\nAnswer\n", encoding="utf-8")
    cards = parse_lines(md_file.read_text().splitlines(), md_file, base_tag="tag", deck="CustomDeck")
    assert len(cards) == 1
    assert cards[0].deck == "CustomDeck"

    res = build(cards)
    assert len(res.notes) == 1
    assert res.notes[0].deck == "CustomDeck"


def test_vault_collect_multi_deck(tmp_path):
    vault = tmp_path / "vault"
    (vault / "CourseA").mkdir(parents=True)
    (vault / "CourseB").mkdir(parents=True)
    (vault / "CourseA" / "note1.md").write_text("# QA\n---\nQuestion A\nAnsA\n", encoding="utf-8")
    (vault / "CourseB" / "note2.md").write_text("# QB\n---\nQuestion B\nAnsB\n", encoding="utf-8")

    cfg = Config(
        vault=vault,
        subdirectories={},
        deck="DefaultDeck",
        decks={"CourseA": "DeckA", "CourseB": "DeckB"},
    )
    collected = collect(cfg)
    assert len(collected.cards) == 2
    cards_by_stem = {c.file.stem: c for c in collected.cards}
    assert cards_by_stem["note1"].deck == "DeckA"
    assert cards_by_stem["note2"].deck == "DeckB"


def test_export_apkg_multi_deck(tmp_path):
    out = tmp_path / "multi.apkg"
    card1 = Card(file=tmp_path / "a.md", line=1, question="Q1", answer="A1", tag="", deck="Deck One")
    card2 = Card(file=tmp_path / "b.md", line=1, question="Q2", answer="A2", tag="", deck="Deck Two")
    res = build([card1, card2])

    export = apkg.export_apkg(res, out)
    assert out.is_file()
    assert len(export.flags) == 2

    # Verify that the generated apkg contains both decks in collection.anki2
    with zipfile.ZipFile(out, "r") as z:
        assert "collection.anki2" in z.namelist()
        z.extract("collection.anki2", tmp_path)

    conn = sqlite3.connect(tmp_path / "collection.anki2")
    cur = conn.cursor()
    cur.execute("SELECT decks FROM col")
    decks_json = cur.fetchone()[0]
    conn.close()

    assert "Deck One" in decks_json
    assert "Deck Two" in decks_json


def test_export_ankiconnect_multi_deck(anki):
    fake = anki({"Basic": 1234})
    card1 = Card(file=Path("a.md"), line=1, question="Q1", answer="A1", tag="", deck="Deck One")
    card2 = Card(file=Path("b.md"), line=1, question="Q2", answer="A2", tag="", deck="Deck Two")
    res = build([card1, card2])

    cfg = Config(vault=Path("."), deck="DefaultDeck")
    export = ankiconnect.export_ankiconnect(res, cfg, [])

    # ensure_deck should be called for both target decks
    deck_calls = [p["deck"] for p in fake.params("createDeck")]
    assert "Deck One" in deck_calls
    assert "Deck Two" in deck_calls

    # addNotes payload should have deckName matching each note's deck
    add_calls = fake.params("addNotes")[0]["notes"]
    assert len(add_calls) == 2
    assert add_calls[0]["deckName"] == "Deck One"
    assert add_calls[1]["deckName"] == "Deck Two"
    assert export.added == 2
