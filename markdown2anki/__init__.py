"""Markdown2Anki: turn Obsidian flashcard notes into Anki cards."""
from importlib.metadata import PackageNotFoundError, version

from .parser import Card, Diagnostic, parse_file, parse_lines
from .build import BuildResult, RenderedNote, build, resolve_image_path
from .render import render_markdown
from .export.apkg import ApkgExport, export_apkg, export_occlusions
from .export.ankiconnect import AnkiConnect, AnkiConnectError, AnkiExport, export_ankiconnect
from .flags import clear_flags, write_flags

try:
    __version__ = version("markdown2anki")
except PackageNotFoundError:  # running from a checkout without `pip install -e .`
    __version__ = "0.0.0"

__all__ = [
    "__version__",
    "Card",
    "Diagnostic",
    "parse_file",
    "parse_lines",
    "build",
    "BuildResult",
    "RenderedNote",
    "resolve_image_path",
    "render_markdown",
    "export_apkg",
    "ApkgExport",
    "export_occlusions",
    "export_ankiconnect",
    "AnkiExport",
    "AnkiConnect",
    "AnkiConnectError",
    "write_flags",
    "clear_flags",
]
