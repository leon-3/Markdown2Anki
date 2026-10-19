"""Markdown2Anki: turn Obsidian flashcard notes into Anki cards."""
from importlib.metadata import PackageNotFoundError, version

from .diagnostics import Diagnostic, DiagnosticCategory, DiagnosticLevel
from .parser import Card, parse_file, parse_lines
from .build import BuildResult, RenderedNote, build, resolve_image_path
from .render import render_markdown
from .occlusions import export_occlusions
from .flags import clear_flags, write_flags
from .config import Config, load_config, load_vault_config, save_vault_config

try:
    __version__ = version("markdown2anki")
except PackageNotFoundError:  # running from a checkout without `pip install -e .`
    __version__ = "0.0.0"


def __getattr__(name: str):
    if name in ("export_apkg", "ApkgExport"):
        try:
            from .export import apkg
            return getattr(apkg, name)
        except ImportError:
            pass
    if name in ("AnkiConnect", "AnkiConnectError", "AnkiExport", "export_ankiconnect"):
        try:
            from .export import ankiconnect
            return getattr(ankiconnect, name)
        except ImportError:
            pass
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return sorted(__all__)


__all__ = [
    "__version__",
    "Card",
    "Diagnostic",
    "DiagnosticCategory",
    "DiagnosticLevel",
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
    "Config",
    "load_config",
    "load_vault_config",
    "save_vault_config",
]
