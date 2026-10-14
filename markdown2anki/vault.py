"""Discover and parse notes in the vault: ``<vault>/<course>/<subdirectory>/*.md``."""
from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from . import ui
from .config import Config
from .parser import LEVEL_ERROR, LEVEL_INFO, LEVEL_WARNING, Card, Diagnostic, parse_file


@dataclass
class SourceFile:
    path: Path
    course: str  # folder name
    subdirectory: str  # folder name
    base_tag: str  # tag hierarchy above the file

    @property
    def group(self) -> str:
        return f"{self.course} / {self.subdirectory}"


@dataclass
class Collected:
    sources: List[SourceFile] = field(default_factory=list)
    cards: List[Card] = field(default_factory=list)
    diagnostics: List[Diagnostic] = field(default_factory=list)

    @property
    def pending(self) -> List[Card]:
        return [c for c in self.cards if c.pending]

    @property
    def added(self) -> List[Card]:
        return [c for c in self.cards if c.added]

    @property
    def problems(self) -> List[Diagnostic]:
        return [d for d in self.diagnostics if d.level != LEVEL_INFO]

    @property
    def has_errors(self) -> bool:
        return any(d.level == LEVEL_ERROR for d in self.diagnostics)


def collect(cfg: Config, course_filter: Optional[str] = None) -> Collected:
    """Discover every note (optionally only one course) and parse it into cards."""
    result = Collected()
    ui.trace("discovering notes")
    result.sources = discover(cfg, course_filter, result.diagnostics)
    ui.trace(f"parsing {len(result.sources)} note(s)")
    for source in result.sources:
        ui.trace(f"  {source.path}")
        result.cards.extend(parse_file(source.path, source.base_tag, result.diagnostics))
    ui.trace(f"{len(result.cards)} card(s)")
    return result


def discover(cfg: Config, course_filter: Optional[str], diagnostics: List[Diagnostic]) -> List[SourceFile]:
    if not cfg.vault.is_dir():
        raise FileNotFoundError(f"vault directory not found: {cfg.vault}")

    sources: List[SourceFile] = []
    for course_dir in _subdirs(cfg.vault):
        name = course_dir.name
        subject_tag = cfg.subject_tag(name)
        if subject_tag is None:
            if name not in cfg.ignore:
                diagnostics.append(Diagnostic(course_dir, 0, LEVEL_INFO, "skipped folder (not in [subjects])"))
            continue
        if course_filter and not _matches(course_filter, name, subject_tag):
            continue

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
            base_tag = "::".join(t for t in [cfg.base_tag, subject_tag, sub_tag] if t)
            sources.extend(SourceFile(note, name, sub_dir.name, base_tag) for note in sorted(sub_dir.glob("*.md")))

        loose = list(course_dir.glob("*.md"))
        if loose:
            diagnostics.append(Diagnostic(course_dir, 0, LEVEL_WARNING,
                                          f"skipped {len(loose)} note(s) directly in the course folder; notes must "
                                          f"be inside a subdirectory such as 'Anki - Lectures'"))
    return sources


def _subdirs(path: Path) -> List[Path]:
    return sorted(p for p in path.iterdir() if p.is_dir() and not p.name.startswith("."))


def _matches(pattern: str, *candidates: str) -> bool:
    pattern = pattern.lower()
    return any(fnmatch.fnmatch(c.lower(), pattern) or pattern in c.lower() for c in candidates)
