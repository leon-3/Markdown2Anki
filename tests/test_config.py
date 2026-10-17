from pathlib import Path
from markdown2anki.config import (
    Config,
    load_vault_config,
    save_vault_config,
    CONFIG_FILE_NAME,
)


def test_load_vault_config_nonexistent(tmp_path):
    vault = tmp_path / "my_vault"
    vault.mkdir()
    cfg = load_vault_config(vault)
    assert cfg.vault == vault
    assert cfg.deck == "Anki"
    assert cfg.deck_routing == {}
    assert cfg.tag_aliases == {}
    assert cfg.pad_single_digit_tags is True


def test_save_and_load_vault_config_roundtrip(tmp_path):
    vault = tmp_path / "my_vault"
    vault.mkdir()

    cfg = Config(
        vault=vault,
        deck="Custom::Deck",
        base_tag="Base",
        pad_single_digit_tags=False,
        output_dir=vault / "out",
        cloze_notes=True,
        hash_media=False,
        re_stage_occlusions=True,
        deck_routing={"TopicA": "DeckA", "TopicA/SubtopicB": "SpecialDeck"},
        tag_aliases={"01. TopicA": "01_topica", "TopicA/SubtopicB": "SubtopicB"},
    )

    save_vault_config(vault, cfg)
    config_file = vault / CONFIG_FILE_NAME
    assert config_file.is_file()

    loaded = load_vault_config(vault)
    assert loaded.vault == vault
    assert loaded.deck == "Custom::Deck"
    assert loaded.base_tag == "Base"
    assert loaded.pad_single_digit_tags is False
    assert loaded.output_dir == vault / "out"
    assert loaded.cloze_notes is True
    assert loaded.hash_media is False
    assert loaded.re_stage_occlusions is True
    assert loaded.deck_routing == {"TopicA": "DeckA", "TopicA/SubtopicB": "SpecialDeck"}
    assert loaded.tag_aliases == {"01. TopicA": "01_topica", "TopicA/SubtopicB": "SubtopicB"}


def test_save_vault_config_preserves_comments(tmp_path):
    vault = tmp_path / "my_vault"
    vault.mkdir()
    config_file = vault / CONFIG_FILE_NAME

    initial_content = """# Top-level comment
vault = "{vault}"
deck = "InitialDeck"

# Section comment for deck_routing
[deck_routing]
# TopicA comment
TopicA = "DeckA"
# TopicB comment
TopicB = "DeckB"
""".format(vault=str(vault))

    config_file.write_text(initial_content, encoding="utf-8")

    cfg = load_vault_config(vault)
    assert cfg.deck == "InitialDeck"

    # Modify a key and table
    cfg.deck = "UpdatedDeck"
    cfg.deck_routing["TopicC"] = "DeckC"

    save_vault_config(vault, cfg)

    saved_text = config_file.read_text(encoding="utf-8")
    assert "# Top-level comment" in saved_text
    assert "# Section comment for deck_routing" in saved_text
    assert "# TopicA comment" in saved_text
    assert "# TopicB comment" in saved_text
    assert 'deck = "UpdatedDeck"' in saved_text
    assert 'TopicC = "DeckC"' in saved_text


def test_config_load_classmethod(tmp_path):
    vault = tmp_path / "my_vault"
    vault.mkdir()
    cfg = Config(vault=vault, deck="TestDeck")
    save_vault_config(vault, cfg)

    config_file = vault / CONFIG_FILE_NAME
    loaded = Config.load(config_file)
    assert loaded.deck == "TestDeck"
