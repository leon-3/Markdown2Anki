from pathlib import Path
from markdown2anki.config import Config
from markdown2anki.vault import discover


def test_recursive_discovery_with_empty_subdirectories(tmp_path):
    """When subdirectories table is empty, vault should recurse all levels without warnings."""
    vault_dir = tmp_path / "vault"
    deep_dir = vault_dir / "general" / "coding" / "python"
    deep_dir.mkdir(parents=True)
    (deep_dir / "async.md").write_text("---\nWhat is asyncio?\nA library\n", encoding="utf-8")
    (vault_dir / "general" / "loose.md").write_text("---\nQuick note?\nQuick answer\n", encoding="utf-8")

    cfg = Config(
        vault=vault_dir,
        base_tag="Notes",
        subdirectories={},  # Empty subdirectories table = recursive walk
    )

    diagnostics = []
    sources = discover(cfg, course_filter=None, diagnostics=diagnostics)

    assert not diagnostics
    assert len(sources) == 2

    # Check tags
    tags = {s.path.name: s.base_tag for s in sources}
    assert tags["loose.md"] == "Notes::general"
    assert tags["async.md"] == "Notes::general::coding::python"


def test_deep_nesting_inside_mapped_subdirectories(tmp_path):
    """When subdirectories are mapped, deep nesting inside them should recurse with proper tags."""
    vault_dir = tmp_path / "vault"
    unit_dir = vault_dir / "50.054 Compiler" / "Anki - Lectures" / "Unit1" / "LessonA"
    unit_dir.mkdir(parents=True)
    (unit_dir / "syntax.md").write_text("---\nSyntax?\nGrammar\n", encoding="utf-8")

    cfg = Config(
        vault=vault_dir,
        base_tag="Uni",
        subdirectories={"Anki - Lectures": "Lectures"},
    )

    diagnostics = []
    sources = discover(cfg, course_filter=None, diagnostics=diagnostics)

    assert not diagnostics
    assert len(sources) == 1
    assert sources[0].base_tag == "Uni::50.054_Compiler::Lectures::Unit1::LessonA"
