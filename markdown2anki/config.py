"""The ``m2a.toml`` configuration: where it lives, how it is loaded and how ``m2a init`` writes it."""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field, fields
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    import tomli as tomllib

CONFIG_FILE_NAME = "m2a.toml"


class Target(str, Enum):
    anki = "anki"  # push into a running Anki via AnkiConnect
    apkg = "apkg"  # write a package file


TARGETS = tuple(t.value for t in Target)

DEFAULT_SUBDIRECTORIES = {"Anki - Lectures": "Lectures", "Anki - Exercises": "Exercises"}
DEFAULT_IGNORE = [".git", ".obsidian", "Archive", "templates"]


def user_config_dir() -> Path:
    """``$XDG_CONFIG_HOME/m2a`` (default ``~/.config/m2a``)."""
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return Path(base) / "m2a"


def user_config_path() -> Path:
    return user_config_dir() / CONFIG_FILE_NAME


def user_templates_dir() -> Path:
    return user_config_dir() / "templates"


@dataclass
class Config:
    vault: Path
    deck: str = "Anki"  # Anki deck; "::" separates subdecks
    package_name: str = ""  # file name of the .apkg export; defaults to the deck name
    base_tag: str = ""  # tag hierarchy root prepended to every card; may be empty
    output_dir: Path = Path(".")
    target: str = "anki"  # default for `m2a sync`
    anki_connect_url: str = "http://127.0.0.1:8765"
    anki_basic_model: str = "M2A Basic"  # note type names used by the AnkiConnect target
    anki_cloze_model: str = "M2A Cloze"
    cloze_notes: bool = False  # True: 'Cloze' cards with {{c1::}} markers become real cloze notes
    templates_dir: Path = field(default_factory=user_templates_dir)  # personal card templates
    ignore: List[str] = field(default_factory=lambda: list(DEFAULT_IGNORE))
    subjects: Dict[str, str] = field(default_factory=dict)  # course folder -> tag; empty = every folder
    subdirectories: Dict[str, str] = field(default_factory=lambda: dict(DEFAULT_SUBDIRECTORIES))
    display: Dict[str, str] = field(default_factory=dict)  # tag -> title shown on the card
    source: Optional[Path] = None  # where the config was loaded from

    def __post_init__(self) -> None:
        self.vault = Path(self.vault).expanduser()
        self.output_dir = Path(self.output_dir).expanduser()
        self.templates_dir = Path(self.templates_dir).expanduser()
        if not self.package_name:
            self.package_name = self.deck.replace("::", "-")
        if self.target not in TARGETS:
            raise ValueError(f"target must be one of {', '.join(TARGETS)}, not {self.target!r}")

    @property
    def apkg_path(self) -> Path:
        return self.output_dir / f"{self.package_name}.apkg"

    def subject_tag(self, folder_name: str) -> Optional[str]:
        """Tag for a top-level vault folder, or None if the folder is not a course."""
        if folder_name in self.ignore:
            return None
        if self.subjects:
            return self.subjects.get(folder_name)
        return sanitize_tag(folder_name)

    @classmethod
    def from_dict(cls, data: Dict[str, Any], source: Path) -> "Config":
        """Build a Config from parsed TOML. Relative paths are taken relative to the config file."""
        if not data.get("vault"):
            raise ValueError(f"{source}: 'vault' is required")
        known = {f.name for f in fields(cls)} - {"source"}
        unknown = sorted(set(data) - known)
        if unknown:
            raise ValueError(f"{source}: unknown setting(s): {', '.join(unknown)}")
        values = dict(data)
        for key in ("vault", "output_dir", "templates_dir"):
            if key in values:
                values[key] = _resolve_relative(Path(values[key]).expanduser(), source.parent)
        return cls(source=source, **values)


def _resolve_relative(path: Path, base: Path) -> Path:
    return path if path.is_absolute() else (base / path).resolve()


def sanitize_tag(name: str) -> str:
    """Make a folder or heading name usable as (part of) an Anki tag."""
    tag = name.strip().replace(". ", "_").replace(" ", "_")
    return re.sub(r"_+", "_", tag)


def find_config(start: Optional[Path] = None) -> Optional[Path]:
    """Walk up from ``start`` (default: cwd) looking for m2a.toml, then fall back to the user config."""
    current = Path(start or os.getcwd()).resolve()
    for candidate in [current, *current.parents]:
        path = candidate / CONFIG_FILE_NAME
        if path.is_file():
            return path
    user = user_config_path()
    return user if user.is_file() else None


def load_config(path: Optional[Path] = None) -> Config:
    """Load m2a.toml from ``path`` or from the usual lookup places."""
    if path is None:
        path = find_config()
    if path is None:
        raise FileNotFoundError(f"no {CONFIG_FILE_NAME} found here, above, or at {user_config_path()} "
                                f"- run `m2a init`")
    if not path.is_file():
        raise FileNotFoundError(f"config not found: {path}")
    with open(path, "rb") as f:
        data = tomllib.load(f)
    return Config.from_dict(data, path)


def config_from_env(path: Path) -> Config:
    """Read the pre-CLI ``.env`` format (KEY=VALUE with JSON blobs); used by ``m2a init`` for migration."""
    values: Dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and not key.startswith("#"):
            values[key.strip()] = value.strip()

    def as_json(key: str, default: Any) -> Any:
        return json.loads(values[key]) if values.get(key) else default

    subdirectories = as_json("SUB_DIRECTORY_TAG_DICTIONARY", DEFAULT_SUBDIRECTORIES)
    # The old script consulted IGNORE before the subdirectory map and silently dropped those cards.
    ignore = [d for d in as_json("IGNORE_DIRECTORIES", DEFAULT_IGNORE)
              if d not in subdirectories and d not in subdirectories.values()]
    deck = values.get("PACKAGE_NAME", "Anki")
    return Config(vault=Path(values.get("OBSIDIAN_VAULT_DIRECTORY", ".")), deck=deck, package_name=deck,
                  base_tag=values.get("BASE_TAG", ""), subjects=as_json("SUBJECT_TAG_DICTIONARY", {}),
                  subdirectories=subdirectories, ignore=ignore, source=path)


def render_toml(cfg: Config) -> str:
    """Serialise a Config as commented m2a.toml text."""

    def quote(value: Any) -> str:
        return json.dumps(str(value), ensure_ascii=False)

    def table(name: str, mapping: Dict[str, str], comment: str) -> List[str]:
        return [f"# {comment}", f"[{name}]", *(f"{quote(k)} = {quote(v)}" for k, v in mapping.items()), ""]

    lines = [
        "# Markdown2Anki configuration. Paths may use ~; relative paths are relative to this file.",
        f"vault = {quote(cfg.vault)}",
        "",
        "# Anki deck the cards go into; use :: for subdecks.",
        f"deck = {quote(cfg.deck)}",
        "# File name of the .apkg export.",
        f"package_name = {quote(cfg.package_name)}",
        "# Tag prepended to every card (may be empty).",
        f"base_tag = {quote(cfg.base_tag)}",
        "# Where .apkg files and image-occlusion sources are written.",
        f"output_dir = {quote(cfg.output_dir)}",
        "",
        "# Default for `m2a sync`: \"anki\" pushes into a running Anki via AnkiConnect, \"apkg\" writes a package file.",
        f"target = {quote(cfg.target)}",
        f"anki_connect_url = {quote(cfg.anki_connect_url)}",
        "# Note type names used by the AnkiConnect target; created from the templates when missing.",
        f"anki_basic_model = {quote(cfg.anki_basic_model)}",
        f"anki_cloze_model = {quote(cfg.anki_cloze_model)}",
        "",
        "# false: 'Cloze' cards are exported as basic notes tagged TODO_PROCESS_CLOZES.",
        "# true: a 'Cloze' card whose answer contains {{c1::...}} becomes a real cloze note.",
        f"cloze_notes = {'true' if cfg.cloze_notes else 'false'}",
        "# Personal card templates: <templates_dir>/{Basic,Cloze}/{front.html,back.html,styling.css}.",
        f"templates_dir = {quote(cfg.templates_dir)}",
        "",
        "# Top-level vault folders that are not courses.",
        "ignore = " + json.dumps(cfg.ignore, ensure_ascii=False),
        "",
        *table("subjects", cfg.subjects,
               "Course folder -> tag. An empty table exports every non-ignored folder with the folder name as tag."),
        *table("subdirectories", cfg.subdirectories,
               "Folder inside a course -> tag. Notes in any other subfolder are reported and skipped."),
        *table("display", cfg.display,
               "Tag -> title shown in the corner of the card. First match wins; list specific tags first."),
    ]
    return "\n".join(lines)
