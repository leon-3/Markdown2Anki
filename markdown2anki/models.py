"""Anki note types (genanki models) and the card templates they are built from.

Templates are looked up per file in the personal ``templates_dir`` first and fall back to the bundled
copies under ``markdown2anki/templates``. A template may contain ``__M2A_SUBJECT_SCRIPT__``, which is
replaced with a script that shows the ``[display]`` title matching the card's tag.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

import genanki

BASIC_MODEL_ID = 1633854805146
CLOZE_MODEL_ID = 1633854805150
BASIC_MODEL_NAME = "Basic"
CLOZE_MODEL_NAME = "Basic (Cloze)"

KIND_BASIC = "Basic"
KIND_CLOZE = "Cloze"
TEMPLATE_FILES = ("front.html", "back.html", "styling.css")
SUBJECT_SCRIPT_PLACEHOLDER = "__M2A_SUBJECT_SCRIPT__"

BUNDLED_DIR = Path(__file__).parent / "templates"


@dataclass(frozen=True)
class Template:
    qfmt: str
    afmt: str
    css: str


class BasicNote(genanki.Note):
    """Note whose GUID derives from the card id, so a re-import updates instead of duplicating."""

    def __init__(self, *args, card_id: Optional[str] = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.card_id = card_id

    @property
    def guid(self):
        if self.card_id:
            return genanki.guid_for("m2a", self.card_id)
        return genanki.guid_for(*self.fields)


class ClozeNote(BasicNote):
    @property
    def guid(self):
        if self.card_id:
            return genanki.guid_for("m2a", self.card_id)
        return genanki.guid_for(self.fields[0])


def template_path(kind: str, name: str, templates_dir: Optional[Path]) -> Path:
    """The personal template file if it exists, else the bundled one."""
    if templates_dir is not None:
        personal = templates_dir / kind / name
        if personal.is_file():
            return personal
    return BUNDLED_DIR / kind / name


def subject_script(display: Dict[str, str]) -> str:
    script = (BUNDLED_DIR / "subject_script.html").read_text(encoding="utf-8")
    return script.replace("__M2A_SUBJECTS__", json.dumps(display, ensure_ascii=False))


def load_template(kind: str, display: Optional[Dict[str, str]] = None,
                  templates_dir: Optional[Path] = None) -> Template:
    script = subject_script(display or {})

    def read(name: str) -> str:
        text = template_path(kind, name, templates_dir).read_text(encoding="utf-8")
        return text.replace(SUBJECT_SCRIPT_PLACEHOLDER, script)

    return Template(qfmt=read("front.html"), afmt=read("back.html"), css=read("styling.css"))


def basic_model(display: Optional[Dict[str, str]] = None, templates_dir: Optional[Path] = None) -> genanki.Model:
    t = load_template(KIND_BASIC, display, templates_dir)
    return genanki.Model(
        BASIC_MODEL_ID, BASIC_MODEL_NAME,
        fields=[{"name": "Front", "font": "Arial"}, {"name": "Back", "font": "Arial"}],
        templates=[{"name": "Card 1", "qfmt": t.qfmt, "afmt": t.afmt}],
        css=t.css,
    )


def cloze_model(display: Optional[Dict[str, str]] = None, templates_dir: Optional[Path] = None) -> genanki.Model:
    t = load_template(KIND_CLOZE, display, templates_dir)
    return genanki.Model(
        CLOZE_MODEL_ID, CLOZE_MODEL_NAME,
        model_type=genanki.Model.CLOZE,
        fields=[{"name": "Text", "font": "Arial"}, {"name": "Back Extra", "font": "Arial"}],
        templates=[{"name": "Cloze", "qfmt": t.qfmt, "afmt": t.afmt}],
        css=t.css,
    )
