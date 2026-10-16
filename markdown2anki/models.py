"""Anki note types and the card templates they are built from.

Templates are looked up per file in the personal ``templates_dir`` first and fall back to the bundled
copies under ``markdown2anki/templates``. A template may contain ``__M2A_SUBJECT_SCRIPT__``, which is
replaced with a script that shows the ``[display]`` title matching the card's tag.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

BASIC_MODEL_ID = 1633854805146
CLOZE_MODEL_ID = 1633854805150

MODEL_NAME_BASIC: str = "M2A Basic"
MODEL_NAME_CLOZE: str = "M2A Cloze"
BASIC_FIELDS: tuple[str, str] = ("Front", "Back")
CLOZE_FIELDS: tuple[str, str] = ("Text", "Back Extra")

# Legacy internal aliases for backwards compatibility
BASIC_MODEL_NAME = MODEL_NAME_BASIC
CLOZE_MODEL_NAME = MODEL_NAME_CLOZE

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


def template_path(kind: str, name: str, templates_dir: Path | None) -> Path:
    """The personal template file if it exists, else the bundled one."""
    if templates_dir is not None:
        personal = templates_dir / kind / name
        if personal.is_file():
            return personal
    return BUNDLED_DIR / kind / name


def subject_script(display: dict[str, str]) -> str:
    script = (BUNDLED_DIR / "subject_script.html").read_text(encoding="utf-8")
    return script.replace("__M2A_SUBJECTS__", json.dumps(display, ensure_ascii=False))


def load_template(kind: str, display: dict[str, str] | None = None,
                  templates_dir: Path | None = None) -> Template:
    script = subject_script(display or {})

    def read(name: str) -> str:
        text = template_path(kind, name, templates_dir).read_text(encoding="utf-8")
        return text.replace(SUBJECT_SCRIPT_PLACEHOLDER, script)

    return Template(qfmt=read("front.html"), afmt=read("back.html"), css=read("styling.css"))


def __getattr__(name: str):
    if name in ("BasicNote", "ClozeNote", "basic_model", "cloze_model"):
        from .export import apkg
        return getattr(apkg, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return sorted(__all__)


__all__ = [
    "BASIC_MODEL_ID",
    "CLOZE_MODEL_ID",
    "MODEL_NAME_BASIC",
    "MODEL_NAME_CLOZE",
    "BASIC_MODEL_NAME",
    "CLOZE_MODEL_NAME",
    "BASIC_FIELDS",
    "CLOZE_FIELDS",
    "KIND_BASIC",
    "KIND_CLOZE",
    "TEMPLATE_FILES",
    "SUBJECT_SCRIPT_PLACEHOLDER",
    "BUNDLED_DIR",
    "Template",
    "template_path",
    "subject_script",
    "load_template",
    "BasicNote",
    "ClozeNote",
    "basic_model",
    "cloze_model",
]
