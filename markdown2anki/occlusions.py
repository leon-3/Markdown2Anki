"""Staging and exporting image occlusions."""
from __future__ import annotations

import re
import secrets
import shutil
from pathlib import Path

from .build import ImageOcclusion
from .ids import new_card_id
from .parser import CLOZE_MARKER_RE, Card

Flags = list[tuple[Card, str]]

OCCLUSION_SHAPES_RE = re.compile(
    r"image-occlusion:|{{c\d+::image-occlusion:|<(?:rect|circle|ellipse|path|polygon)\b|data-cloze=",
    re.IGNORECASE,
)


def is_occlusion_completed(occlusion_field: str | None) -> bool:
    """Check if the Occlusion field of an Image Occlusion note contains drawn masks.

    Returns True if native image occlusion markers or shapes are present.
    Returns False if empty, whitespace, or empty container without shapes.
    """
    if not occlusion_field or not occlusion_field.strip():
        return False
    return bool(OCCLUSION_SHAPES_RE.search(occlusion_field))


def is_cloze_completed(text_field: str | None) -> bool:
    """Check if a Cloze note text field contains cloze deletions ({{c1::...}})."""
    if not text_field or not text_field.strip():
        return False
    return bool(CLOZE_MARKER_RE.search(text_field))


def export_occlusions(
    occlusions: list[ImageOcclusion],
    base_dir: Path,
    prefix: str | None = None,
) -> tuple[Path, Flags, dict[str, list[str]]]:
    """Copy image occlusion images into base_dir/occlusions/ with randomized sequential names.

    Returns (occlusion_dir, flags, staged_by_tag).
    """
    occlusion_dir = base_dir / "occlusions"
    occlusion_dir.mkdir(parents=True, exist_ok=True)
    if prefix is None:
        prefix = secrets.token_hex(4).upper()

    by_tag: dict[str, list[ImageOcclusion]] = {}
    for occ in occlusions:
        by_tag.setdefault(occ.tag or "(no tag)", []).append(occ)

    flags: Flags = []
    staged_by_tag: dict[str, list[str]] = {}
    counter = 1

    for tag, occ_list in by_tag.items():
        staged_by_tag[tag] = []
        for occlusion in occ_list:
            for image in occlusion.images:
                ext = image.suffix or ".png"
                new_name = f"{prefix}_{counter:02d}{ext}"
                counter += 1
                shutil.copy2(image, occlusion_dir / new_name)
                staged_by_tag[tag].append(new_name)
            flags.append((occlusion.card, occlusion.card.card_id or new_card_id()))

    return occlusion_dir, flags, staged_by_tag
