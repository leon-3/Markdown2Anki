"""Markdown2Anki: turn Obsidian flashcard notes into Anki cards. Command line entry point: ``m2a``."""
from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("markdown2anki")
except PackageNotFoundError:  # running from a checkout without `pip install -e .`
    __version__ = "0.0.0"
