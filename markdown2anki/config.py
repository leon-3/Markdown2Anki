"""Read, validate, and write m2a.toml."""
from __future__ import annotations

import json
import os
import re
import tomllib
from dataclasses import dataclass, field, fields
from enum import Enum
from pathlib import Path
from typing import Any

import tomlkit

CONFIG_FILE_NAME = "m2a.toml"


class Target(str, Enum):
    anki = "anki"  # push into a running Anki via AnkiConnect
    apkg = "apkg"  # write a package file


TARGETS = tuple(t.value for t in Target)

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
    deck: str = "Anki"  # default target Anki deck; "::" separates subdecks
    package_name: str = ""  # file name of the .apkg export; defaults to the deck name
    base_tag: str = ""  # tag hierarchy root prepended to every card; may be empty
    pad_single_digit_tags: bool = True  # True: zero-pad single-digit numbers in tags (1 -> 01)
    output_dir: Path = Path(".")
    target: str = "anki"  # default for `m2a sync`
    anki_connect_url: str = "http://127.0.0.1:8765"
    anki_basic_model: str = "M2A Basic"  # note type names used by the AnkiConnect target
    anki_cloze_model: str = "M2A Cloze"
    cloze_notes: bool = False  # True: 'Cloze' cards with {{c1::}} markers become real cloze notes
    hash_media: bool = True  # True: rename embedded images to deterministic 8-hex hashes (e.g. 472d6b17_01.png)
    templates_dir: Path = field(default_factory=user_templates_dir)  # personal card templates
    ignore: list[str] = field(default_factory=lambda: list(DEFAULT_IGNORE))
    deck_routing: dict[str, str] = field(default_factory=dict)  # relative folder path prefix -> target deck
    tag_aliases: dict[str, str] = field(default_factory=dict)  # relative folder path prefix / segment -> tag replacement
    display: dict[str, str] = field(default_factory=dict)  # tag -> title shown on the card (deprecated)
    re_stage_occlusions: bool = False
    source: Path | None = None  # where the config was loaded from

    def __post_init__(self) -> None:
        self.vault = Path(self.vault).expanduser()
        self.output_dir = Path(self.output_dir).expanduser()
        self.templates_dir = Path(self.templates_dir).expanduser()
        if not self.package_name:
            self.package_name = self.deck.replace("::", "-")
        if self.target not in TARGETS:
            raise ValueError(f"target must be one of {', '.join(TARGETS)}, not {self.target!r}")

    @property
    def decks(self) -> dict[str, str]:
        """Compatibility property mapping to deck_routing."""
        return self.deck_routing

    @decks.setter
    def decks(self, value: dict[str, str]) -> None:
        self.deck_routing = value

    @property
    def apkg_path(self) -> Path:
        return self.output_dir / f"{self.package_name}.apkg"

    def subject_tag(self, folder_name: str) -> str | None:
        """Tag for a folder, or None if the folder is ignored."""
        if folder_name in self.ignore:
            return None
        if folder_name in self.tag_aliases:
            return self.tag_aliases[folder_name] or None
        return sanitize_tag(folder_name)

    def resolve_deck(self, folder_path: str = "") -> str:
        """Resolve deck name from deck_routing rules (or fallback to default deck)."""
        from .vault import normalize_rel_parts, resolve_deck_for_parts
        parts = normalize_rel_parts(folder_path)
        return resolve_deck_for_parts(parts, self.deck_routing, self.deck)

    @classmethod
    def load(cls, path: Path | None = None) -> Config:
        """Load m2a.toml from ``path`` or from the usual lookup places."""
        return load_config(path)

    @classmethod
    def from_dict(cls, data: dict[str, Any], source: Path) -> Config:
        """Build a Config from parsed TOML. Relative paths are taken relative to the config file."""
        if not data.get("vault"):
            raise ValueError(f"{source}: 'vault' is required")

        values = dict(data)
        # Migrate or support legacy 'decks' key
        if "decks" in values and "deck_routing" not in values:
            values["deck_routing"] = values.pop("decks")

        # Migrate or support legacy 'subjects' key as tag_aliases
        if "subjects" in values and "tag_aliases" not in values:
            values["tag_aliases"] = values.pop("subjects")

        # Clean legacy keys
        values.pop("decks", None)
        values.pop("subjects", None)
        values.pop("subdirectories", None)

        known = {f.name for f in fields(cls)} - {"source"}
        unknown = sorted(set(values) - known)
        if unknown:
            raise ValueError(f"{source}: unknown setting(s): {', '.join(unknown)}")

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


def find_config(start: Path | None = None) -> Path | None:
    """Walk up from ``start`` (default: cwd) looking for m2a.toml, then fall back to the user config."""
    current = Path(start or os.getcwd()).resolve()
    for candidate in [current, *current.parents]:
        path = candidate / CONFIG_FILE_NAME
        if path.is_file():
            return path
    user = user_config_path()
    return user if user.is_file() else None


def load_config(path: Path | None = None) -> Config:
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


def load_vault_config(vault_path: Path) -> Config:
    """Load Config from <vault_path>/m2a.toml if it exists, otherwise return default Config."""
    vault_path = Path(vault_path).expanduser().resolve()
    config_file = vault_path / CONFIG_FILE_NAME
    if not config_file.is_file():
        return Config(vault=vault_path)
    return load_config(config_file)


def save_vault_config(vault_path: Path, cfg: Config) -> None:
    """Save configuration to <vault_path>/m2a.toml using tomlkit, preserving existing comments."""
    vault_path = Path(vault_path).expanduser().resolve()
    config_file = vault_path / CONFIG_FILE_NAME
    if config_file.is_file():
        content = config_file.read_text(encoding="utf-8")
        doc = tomlkit.parse(content)
    else:
        doc = tomlkit.document()

    # Update top-level keys
    doc["vault"] = str(cfg.vault)
    doc["deck"] = cfg.deck
    doc["package_name"] = cfg.package_name
    doc["base_tag"] = cfg.base_tag
    doc["pad_single_digit_tags"] = cfg.pad_single_digit_tags
    doc["output_dir"] = str(cfg.output_dir)
    doc["target"] = cfg.target
    doc["anki_connect_url"] = cfg.anki_connect_url
    doc["anki_basic_model"] = cfg.anki_basic_model
    doc["anki_cloze_model"] = cfg.anki_cloze_model
    doc["cloze_notes"] = cfg.cloze_notes
    doc["hash_media"] = cfg.hash_media
    doc["templates_dir"] = str(cfg.templates_dir)
    doc["ignore"] = list(cfg.ignore)
    doc["re_stage_occlusions"] = cfg.re_stage_occlusions

    # Update dictionary tables (deck_routing, tag_aliases)
    for table_name in ("deck_routing", "tag_aliases"):
        val: dict[str, str] = getattr(cfg, table_name, {})
        if val:
            if table_name in doc and isinstance(doc[table_name], dict):
                tbl = doc[table_name]
                for k in list(tbl.keys()):
                    if k not in val:
                        del tbl[k]
                for k, v in val.items():
                    tbl[k] = v
            else:
                table = tomlkit.table()
                for k, v in val.items():
                    table[k] = v
                doc[table_name] = table
        else:
            if table_name in doc:
                del doc[table_name]

    # Explicitly pop legacy tables if present in existing document
    for legacy_key in ("decks", "subjects", "subdirectories", "display"):
        if legacy_key in doc:
            del doc[legacy_key]

    # Atomically write back to disk
    vault_path.mkdir(parents=True, exist_ok=True)
    tmp_file = config_file.with_suffix(".tmp")
    tmp_file.write_text(tomlkit.dumps(doc), encoding="utf-8")
    tmp_file.replace(config_file)


def config_from_env(path: Path) -> Config:
    """Read the pre-CLI ``.env`` format (KEY=VALUE with JSON blobs); used by ``m2a init`` for migration."""
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and not key.startswith("#"):
            values[key.strip()] = value.strip()

    def as_json(key: str, default: Any) -> Any:
        return json.loads(values[key]) if values.get(key) else default

    subdirectories = as_json("SUB_DIRECTORY_TAG_DICTIONARY", {})
    ignore = [d for d in as_json("IGNORE_DIRECTORIES", DEFAULT_IGNORE)
              if d not in subdirectories and d not in subdirectories.values()]
    deck = values.get("PACKAGE_NAME", "Anki")
    tag_aliases = dict(as_json("SUBJECT_TAG_DICTIONARY", {}))
    return Config(
        vault=Path(values.get("OBSIDIAN_VAULT_DIRECTORY", ".")),
        deck=deck,
        package_name=deck,
        base_tag=values.get("BASE_TAG", ""),
        tag_aliases=tag_aliases,
        ignore=ignore,
        source=path,
    )


def render_toml(cfg: Config) -> str:
    """Serialise a Config as commented m2a.toml text."""

    def quote(value: Any) -> str:
        return json.dumps(str(value), ensure_ascii=False)

    def table(name: str, mapping: dict[str, str], comment: str) -> list[str]:
        if not mapping:
            return []
        return [f"# {comment}", f"[{name}]", *(f"{quote(k)} = {quote(v)}" for k, v in mapping.items()), ""]

    lines = [
        "# Markdown2Anki configuration. Paths may use ~; relative paths are relative to this file.",
        f"vault = {quote(cfg.vault)}",
        "",
        "# Default Anki deck the cards go into; use :: for subdecks.",
        f"deck = {quote(cfg.deck)}",
        "# File name of the .apkg export.",
        f"package_name = {quote(cfg.package_name)}",
        "# Tag prepended to every card (may be empty).",
        f"base_tag = {quote(cfg.base_tag)}",
        "# Automatically pad single-digit numbers with leading zero in tags (e.g. 1 -> 01).",
        f"pad_single_digit_tags = {'true' if cfg.pad_single_digit_tags else 'false'}",
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
        "# true: rename embedded images to deterministic 8-hex lowercase hashes (e.g. 472d6b17_01.png).",
        f"hash_media = {'true' if cfg.hash_media else 'false'}",
        "# Personal card templates: <templates_dir>/{Basic,Cloze}/{front.html,back.html,styling.css}.",
        f"templates_dir = {quote(cfg.templates_dir)}",
        "",
        "# Folders or glob patterns to ignore during vault traversal.",
        "ignore = " + json.dumps(cfg.ignore, ensure_ascii=False),
        "",
        *table("deck_routing", cfg.deck_routing,
               "Vault folder/path prefix -> target Anki deck name override (longest prefix match)."),
        *table("tag_aliases", cfg.tag_aliases,
               "Vault folder/path prefix -> tag replacement, alias, or '' to omit."),
    ]
    return "\n".join(lines)
