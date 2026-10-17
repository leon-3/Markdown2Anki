"""Discover and parse notes in the vault."""
from __future__ import annotations

import fnmatch
import logging
import os
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .config import Config
from .parser import (
    LEVEL_ERROR,
    LEVEL_INFO,
    Card,
    Diagnostic,
    format_tag_segment,
    parse_file,
)

logger = logging.getLogger("markdown2anki.vault")


@dataclass
class SourceFile:
    path: Path
    course: str  # top folder name or (vault)
    subdirectory: str  # immediate subfolder or (root)
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


def normalize_rel_parts(path_str: str | Path | None) -> tuple[str, ...]:
    """Canonical relative folder parts helper (NFC normalized, POSIX separators).

    Returns () for vault root, empty paths, or '.' paths.
    """
    if not path_str:
        return ()
    norm = unicodedata.normalize("NFC", str(path_str)).replace("\\", "/")
    segments = [s.strip() for s in norm.split("/") if s.strip() and s.strip() != "."]
    return tuple(segments)


def resolve_deck_for_parts(parts: tuple[str, ...], rules: dict[str, str], default_deck: str) -> str:
    """Longest Prefix Match (LPM) on folder parts against deck_routing rules."""
    if not rules:
        return default_deck

    best_match_deck: str | None = None
    best_match_len: int = -1

    for rule_key, deck_name in rules.items():
        rule_parts = normalize_rel_parts(rule_key)
        # Match only on folder segment boundaries
        if len(rule_parts) <= len(parts) and parts[:len(rule_parts)] == rule_parts:
            if len(rule_parts) > best_match_len:
                best_match_len = len(rule_parts)
                best_match_deck = deck_name

    return best_match_deck if best_match_deck is not None else default_deck


def resolve_tags_for_parts(
    parts: tuple[str, ...],
    base_tag: str,
    tag_aliases: dict[str, str],
    pad_single_digits: bool = True,
) -> str:
    """Single-pass greedy token resolution for hierarchical Anki tags."""
    alias_map: dict[tuple[str, ...], str] = {
        normalize_rel_parts(k): v for k, v in tag_aliases.items()
    }

    out_segments: list[str] = []
    i = 0
    n = len(parts)

    while i < n:
        matched = False
        for k in range(n - i, 0, -1):
            sub_tuple = parts[i : i + k]
            if sub_tuple in alias_map:
                replacement = alias_map[sub_tuple]
                matched = True
                i += k
                if replacement == "":
                    # Suppressed segment
                    break
                # An explicit alias can be hierarchical (using :: or /)
                # Explicit alias tokens are authoritative and exempt from automatic digit padding
                norm_repl = replacement.replace("/", "::")
                for token in norm_repl.split("::"):
                    token = token.strip()
                    if token:
                        out_segments.append(token)
                break

        if not matched:
            seg = format_tag_segment(parts[i], pad_single_digits=pad_single_digits)
            if seg:
                out_segments.append(seg)
            i += 1

    all_segments: list[str] = []
    if base_tag:
        for b in base_tag.split("::"):
            b = b.strip()
            if b:
                all_segments.append(b)
    all_segments.extend(out_segments)

    return "::".join(all_segments)


def _is_ignored(rel_parts: tuple[str, ...], name: str, ignore_patterns: list[str]) -> bool:
    if name.startswith("."):
        return True
    rel_str = "/".join(rel_parts)
    for pat in ignore_patterns:
        pat_norm = pat.strip().replace("\\", "/").rstrip("/")
        if fnmatch.fnmatch(name, pat_norm) or fnmatch.fnmatch(rel_str, pat_norm):
            return True
        if pat_norm in (name, rel_str):
            return True
    return False


def collect(
    cfg: Config,
    course_filter: str | None = None,
    trace_fn: Callable[[str], None] | None = None,
) -> Collected:
    """Discover every note (optionally filtered by path/course) and parse it into cards."""
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
        result.cards.extend(
            parse_file(
                source.path,
                source.base_tag,
                result.diagnostics,
                deck=source.deck,
                pad_single_digits=cfg.pad_single_digit_tags,
            )
        )
    _trace(f"{len(result.cards)} card(s)")
    return result


def discover(
    cfg: Config,
    course_filter: str | None = None,
    diagnostics: list[Diagnostic] | None = None,
) -> list[SourceFile]:
    """Find note files to parse based on vault configuration using unified recursive traversal."""
    if not cfg.vault.is_dir():
        raise FileNotFoundError(f"vault directory not found: {cfg.vault}")

    diagnostics = diagnostics if diagnostics is not None else []
    sources: list[SourceFile] = []

    for root, dirs, files in os.walk(cfg.vault, topdown=True):
        rel_root = os.path.relpath(root, cfg.vault)
        root_parts = normalize_rel_parts(rel_root)

        # In-place directory pruning
        dirs[:] = [
            d for d in sorted(dirs)
            if not _is_ignored(root_parts + (d,), d, cfg.ignore)
        ]

        # Process markdown files deterministically
        for file in sorted(files):
            if not file.endswith(".md") or file.startswith("."):
                continue

            file_rel_parts = root_parts + (file,)
            if _is_ignored(file_rel_parts, file, cfg.ignore):
                continue

            note_path = Path(root) / file
            deck = resolve_deck_for_parts(root_parts, cfg.deck_routing, cfg.deck)
            base_tag = resolve_tags_for_parts(
                root_parts,
                cfg.base_tag,
                cfg.tag_aliases,
                pad_single_digits=cfg.pad_single_digit_tags,
            )

            course_name = root_parts[0] if root_parts else "(vault)"
            sub_name = root_parts[1] if len(root_parts) > 1 else "(root)"

            if course_filter and not _matches(course_filter, course_name, *root_parts):
                continue

            sources.append(
                SourceFile(
                    path=note_path,
                    course=course_name,
                    subdirectory=sub_name,
                    base_tag=base_tag,
                    deck=deck,
                )
            )

    return sources


def _matches(pattern: str, *candidates: str) -> bool:
    pattern = pattern.lower()
    return any(fnmatch.fnmatch(c.lower(), pattern) or pattern in c.lower() for c in candidates)
