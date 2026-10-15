import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_basic_adding_from_input_runs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "sample.md").write_text("# Test\n---\nQuestion 1\nAnswer 1\n", encoding="utf-8")

    script_path = REPO_ROOT / "basic_adding_from_input.py"
    # Pass empty input for base_tag prompt
    res = subprocess.run([sys.executable, str(script_path)], input="\n", capture_output=True, text=True, cwd=tmp_path)
    assert res.returncode == 0
    assert "Created package" in res.stdout
    assert (tmp_path / "output.apkg").is_file()


def test_basic_adding_from_input_with_occlusion_and_tag(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    img_file = input_dir / "diag.png"
    img_file.write_bytes(b"occlusion image content")
    (input_dir / "occ.md").write_text("# Test\n---\nImage Cloze\n![[diag.png]]\n", encoding="utf-8")

    script_path = REPO_ROOT / "basic_adding_from_input.py"
    res = subprocess.run([sys.executable, str(script_path)], input="MyBaseTag\n", capture_output=True, text=True, cwd=tmp_path)
    assert res.returncode == 0
    assert (tmp_path / "output.apkg").is_file()
    assert "Staged 1 image occlusion(s)" in res.stdout
    assert (tmp_path / "occlusions").is_dir()
    copied = list((tmp_path / "occlusions").glob("*.png"))
    assert len(copied) == 1
    assert copied[0].name.endswith("_01.png")
    assert copied[0].name in res.stdout
