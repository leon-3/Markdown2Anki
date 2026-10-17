"""Anki note types and the card templates they are built from.

Templates are looked up per file in the personal ``templates_dir`` first and fall back to the bundled
copies under ``markdown2anki/templates``.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

BASIC_MODEL_ID = 1633854805146
CLOZE_MODEL_ID = 1633854805150

MODEL_NAME_BASIC: str = "M2A Basic"
MODEL_NAME_CLOZE: str = "M2A Cloze"
MODEL_NAME_IMAGE_OCCLUSION: str = "Image Occlusion"

BASIC_FIELDS: tuple[str, str] = ("Front", "Back")
CLOZE_FIELDS: tuple[str, str] = ("Text", "Back Extra")
IMAGE_OCCLUSION_FIELDS: tuple[str, ...] = ("Occlusion", "Image", "Header", "Back Extra", "Comments")

# Legacy internal aliases for backwards compatibility
BASIC_MODEL_NAME = MODEL_NAME_BASIC
CLOZE_MODEL_NAME = MODEL_NAME_CLOZE
IMAGE_OCCLUSION_MODEL_NAME = MODEL_NAME_IMAGE_OCCLUSION

KIND_BASIC = "Basic"
KIND_CLOZE = "Cloze"
KIND_IMAGE_OCCLUSION = "Image Occlusion"
TEMPLATE_FILES = ("front.html", "back.html", "styling.css")

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


def load_template(kind: str, display: dict[str, str] | None = None,
                  templates_dir: Path | None = None) -> Template:
    def read(name: str) -> str:
        return template_path(kind, name, templates_dir).read_text(encoding="utf-8")

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
    "KIND_IMAGE_OCCLUSION",
    "MODEL_NAME_IMAGE_OCCLUSION",
    "IMAGE_OCCLUSION_MODEL_NAME",
    "IMAGE_OCCLUSION_FIELDS",
    "TEMPLATE_FILES",
    "BUNDLED_DIR",
    "Template",
    "template_path",
    "load_template",
    "BasicNote",
    "ClozeNote",
    "basic_model",
    "cloze_model",
]
