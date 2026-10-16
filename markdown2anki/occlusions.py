"""Staging and exporting image occlusions."""
from __future__ import annotations

import secrets
import shutil
from pathlib import Path

from .build import ImageOcclusion
from .ids import new_card_id
from .parser import Card

Flags = list[tuple[Card, str]]


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
