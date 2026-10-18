from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import urllib.parse


class DiagnosticLevel(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class DiagnosticCategory(str, Enum):
    SYNTAX = "syntax"          # Markdown structure, unclosed fences, boundary errors
    MEDIA = "media"            # Missing images, attachments
    CLOZE = "cloze"            # Cloze in basic card, image cloze without image
    SCHEMA = "schema"          # Unknown HTML tags, incompatible note types/fields
    CONFLICT = "conflict"      # External file changes, modified notes
    SYSTEM = "system"          # IO errors, file permissions, encoding, network


@dataclass(frozen=True, slots=True)
class Diagnostic:
    file: Path
    line: int | None = None
    level: DiagnosticLevel | str = DiagnosticLevel.ERROR
    message: str = ""
    category: DiagnosticCategory | str = DiagnosticCategory.SYNTAX
    column: int | None = None
    suggestion: str | None = None
    snippet: str | None = None
    card_identifier: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.level, str) and not isinstance(self.level, DiagnosticLevel):
            try:
                object.__setattr__(self, "level", DiagnosticLevel(self.level))
            except ValueError:
                pass
        if isinstance(self.category, str) and not isinstance(self.category, DiagnosticCategory):
            try:
                object.__setattr__(self, "category", DiagnosticCategory(self.category))
            except ValueError:
                pass

    @property
    def location_label(self) -> str:
        """Formats file name and optional line number safely for UI and CLI."""
        if self.line is not None and self.line > 0:
            return f"{self.file.name}:{self.line}"
        return self.file.name

    def to_obsidian_uri(self, vault_root: Path | None = None) -> str:
        """Generates a robust obsidian:// URI.

        Traverses upward to identify the true Obsidian vault root via the '.obsidian'
        directory. Falls back to absolute path (?path=...) if not found or outside.
        """
        resolved_file = self.file.resolve()

        # 1. Search upwards for .obsidian directory from the file's directory
        actual_vault_root = None
        for parent in [resolved_file] + list(resolved_file.parents):
            if (parent / ".obsidian").is_dir():
                actual_vault_root = parent
                break

        if actual_vault_root is None and vault_root is not None:
            resolved_root = vault_root.resolve()
            if (resolved_root / ".obsidian").is_dir():
                actual_vault_root = resolved_root

        # 2. Vault-based URI (safe="" ensures slashes are properly percent-encoded for query string)
        if actual_vault_root is not None:
            try:
                rel_posix = resolved_file.relative_to(actual_vault_root).as_posix()
                vault_name = urllib.parse.quote(actual_vault_root.name, safe="")
                file_param = urllib.parse.quote(rel_posix, safe="")
                return f"obsidian://open?vault={vault_name}&file={file_param}"
            except ValueError:
                pass

        # 3. Fallback: Absolute file path (natively resolved by Obsidian >= 0.15.6)
        encoded_abs = urllib.parse.quote(resolved_file.as_posix(), safe="")
        return f"obsidian://open?path={encoded_abs}"
