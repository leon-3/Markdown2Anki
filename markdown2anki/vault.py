"""Discover and parse notes in the vault."""
from __future__ import annotations

import fnmatch
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .config import Config, sanitize_tag
from .parser import LEVEL_ERROR, LEVEL_INFO, LEVEL_WARNING, Card, Diagnostic, parse_file

logger = logging.getLogger("markdown2anki.vault")


@dataclass
class SourceFile:
    path: Path
    course: str  # folder name
    subdirectory: str  # folder name
    base_tag: str  # tag hierarchy above the file
    deck: str | None = None

    @property
    def group(self) -> str:
        return f"{self.course} / {self.subdirectory}"


@dataclass
class Collected:
    sources: list[SourceFile] = field(default_factory=list)
    cards: list[Card] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)

    @property
    def pending(self) -> list[Card]:
        return [c for c in self.cards if c.pending]

    @property
    def added(self) -> list[Card]:
        return [c for c in self.cards if c.added]

    @property
    def problems(self) -> list[Diagnostic]:
        return [d for d in self.diagnostics if d.level != LEVEL_INFO]

    @property
    def has_errors(self) -> bool:
        return any(d.level == LEVEL_ERROR for d in self.diagnostics)


def collect(
    cfg: Config,
    course_filter: str | None = None,
    trace_fn: Callable[[str], None] | None = None,
) -> Collected:
    """Discover every note (optionally only one course) and parse it into cards."""
    result = Collected()

    def _trace(msg: str) -> None:
        logger.debug(msg)
        if trace_fn is not None:
            trace_fn(msg)

    _trace("discovering notes")
    result.sources = discover(cfg, course_filter, result.diagnostics)
    _trace(f"parsing {len(result.sources)} note(s)")
    for source in result.sources:
        _trace(f"  {source.path}")
        result.cards.extend(parse_file(source.path, source.base_tag, result.diagnostics, deck=source.deck))
    _trace(f"{len(result.cards)} card(s)")
    return result


def discover(cfg: Config, course_filter: str | None, diagnostics: list[Diagnostic]) -> list[SourceFile]:
    """Find note files to parse based on vault configuration.

    Supports two distinct vault organization modes:

    1. Mode A: Strict Two-Step Academic Hierarchy (when `cfg.subdirectories` is non-empty)
       - Vault layout: `<vault>/<course>/<subdirectory>/*.md`
       - Origin: Designed for structured university vaults where each module contains specific
         learning activity folders (e.g. `Anki - Lectures`, `Anki - Exercises`).
       - Behavior: Only subfolders explicitly listed in `[subdirectories]` are parsed, mapping
         each subdirectory to a fixed sub-tag (e.g. `Lectures`). Non-matching subfolders (e.g.
         `Summaries`, `Cheat Sheets`) and loose `.md` files directly in `<course>/` are intentionally
         quarantined and skipped with diagnostic warnings to prevent accidental note ingestion.

    2. Mode B: Full Recursive Traversal (when `cfg.subdirectories` is empty)
       - Vault layout: `<vault>/<topic>/.../arbitrary/nested/folders/*.md`
       - Origin: Designed for personal knowledge bases and Long Term Knowledge (LTK) vaults where
         notes are organized by topic trees rather than fixed academic course categories.
       - Behavior: Recursively walks all folders down to arbitrary depth. Every intermediate folder
         becomes a segment in the hierarchical Anki tag (e.g. `01_General::Math::Probability_Theory`),
         and notes can reside at any depth (including directly in top-level subject folders).
    """
    if not cfg.vault.is_dir():
        raise FileNotFoundError(f"vault directory not found: {cfg.vault}")

    sources: list[SourceFile] = []
    top_dirs = _subdirs(cfg.vault)
    if not top_dirs:
        top_dirs = [cfg.vault]

    for course_dir in top_dirs:
        name = course_dir.name if course_dir != cfg.vault else ""
        subject_tag = cfg.subject_tag(name) if name else None
        if name and subject_tag is None:
            if name not in cfg.ignore:
                diagnostics.append(Diagnostic(course_dir, 0, LEVEL_INFO, "skipped folder (not in [subjects])"))
            continue
        if course_filter and name and not _matches(course_filter, name, subject_tag or ""):
            continue

        deck = cfg.resolve_deck(name)

        # Traversal Mode Switch:
        # If [subdirectories] is configured, enforce strict two-step academic hierarchy
        # (<course>/<subdirectory>/*.md) and warn about loose files or unlisted subfolders.
        # If [subdirectories] is empty, allow free-form arbitrary-depth recursive walking
        # for personal knowledge bases / LTK vaults.
        if cfg.subdirectories:
            # Mode A: Enforce two-step hierarchy (<course>/<subdirectory>/*.md)
            for sub_dir in _subdirs(course_dir):
                if sub_dir.name in cfg.ignore:
                    continue
                sub_tag = cfg.subdirectories.get(sub_dir.name)
                if sub_tag is None:
                    count = len(list(sub_dir.rglob("*.md")))
                    if count:
                        diagnostics.append(Diagnostic(sub_dir, 0, LEVEL_WARNING,
                                                      f"skipped {count} note(s) under '{sub_dir.name}': not in "
                                                      f"[subdirectories] (notes must be <course>/<subdirectory>/*.md)"))
                    continue

                for root, dirs, files in os.walk(sub_dir):
                    dirs[:] = [d for d in dirs if not d.startswith(".") and d not in cfg.ignore]
                    dirs.sort()
                    rel = os.path.relpath(root, sub_dir)
                    parts = [] if rel == "." else rel.split(os.sep)
                    tag_parts = [cfg.base_tag, subject_tag, sub_tag] + [sanitize_tag(p) for p in parts]
                    base_tag = "::".join(t for t in tag_parts if t)
                    for file in sorted(files):
                        if file.endswith(".md"):
                            sources.append(SourceFile(Path(root) / file, name, sub_dir.name, base_tag, deck=deck))

            loose = list(course_dir.glob("*.md"))
            if loose:
                diagnostics.append(Diagnostic(course_dir, 0, LEVEL_WARNING,
                                              f"skipped {len(loose)} note(s) directly in the course folder; notes must "
                                              f"be inside a subdirectory such as 'Anki - Lectures'"))
        else:
            # Mode B: Recursive walking for arbitrary depth
            for root, dirs, files in os.walk(course_dir):
                dirs[:] = [d for d in dirs if not d.startswith(".") and d not in cfg.ignore]
                dirs.sort()
                rel = os.path.relpath(root, course_dir)
                parts = [] if rel == "." else rel.split(os.sep)
                tag_parts = [cfg.base_tag, subject_tag] + [sanitize_tag(p) for p in parts]
                base_tag = "::".join(t for t in tag_parts if t)
                sub_name = parts[0] if parts else "(root)"
                for file in sorted(files):
                    if file.endswith(".md"):
                        sources.append(SourceFile(Path(root) / file, name or "(vault)", sub_name, base_tag, deck=deck))

    return sources


def _subdirs(path: Path) -> list[Path]:
    return sorted(p for p in path.iterdir() if p.is_dir() and not p.name.startswith("."))


def _matches(pattern: str, *candidates: str) -> bool:
    pattern = pattern.lower()
    return any(fnmatch.fnmatch(c.lower(), pattern) or pattern in c.lower() for c in candidates)
