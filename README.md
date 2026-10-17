# Markdown2Anki

Turn flashcard notes written in Obsidian or standard Markdown into Anki cards.

**Markdown2Anki** provides both a standalone command-line interface (`m2a`) and a decoupled Python library API. It parses Markdown notes, tracks flashcards with lightweight stable IDs, routes cards across multiple decks using longest-prefix matching, generates natural hierarchical tags, deterministically hashes image attachments, and updates cards in place in Anki without resetting review histories or ease factors.

> [!TIP]
> Prefer a graphical desktop interface? Check out the companion Anki add-on [**Anki-VaultSync**](../Anki-VaultSync), which embeds this engine directly inside Anki Desktop with a visual dashboard, diff inspector, and tabbed configuration.

---

## Key Features

- **Direct Push or Standalone Package**:
  - **AnkiConnect** (`target = "anki"`): Directly syncs notes into a running Anki instance via HTTP (`http://127.0.0.1:8765`).
  - **Anki Package** (`target = "apkg"`): Generates standalone `.apkg` files with bundled media for manual import or offline sharing.
- **In-Place Card Updates**:
  - Tags cards with compact 6-character IDs embedded in Markdown (`ADDED: Question %%k3f9qz%%`) and Anki (`<!--m2a:id-->`).
  - Run `m2a sync --update` to push edits into Anki in place—retaining card intervals, ease factors, and review logs.
- **Longest-Prefix Deck Routing**:
  - Map vault folders and nested subdirectories directly to target Anki decks via `[deck_routing]`. More specific nested paths automatically override parent folder rules.
- **Hierarchical Tagging & Aliasing**:
  - Generates tags matching vault folder structure.
  - Custom replacements or tag suppression via `[tag_aliases]` (e.g. mapping `"archive" = ""` omits that folder from tags).
  - Optional single-digit padding (`pad_single_digit_tags = true`) transforms `'1. Topic'` into `'01_Topic'` for natural alphabetical sorting, while protecting alphanumeric terms like `MP3` or `ISO9001`.
- **Deterministic Media Hashing**:
  - Embedded images and media attachments are renamed to lowercase SHA-256 hashes (`<8hex>_01.ext`) with collision-safe counters, preventing file clashes.
- **Rich Card Formatting**:
  - Standard Q&A, multi-line questions (`EQL:`), native Cloze deletions (`{{c1::...}}`), and Image Occlusion staging.
  - Inline (`$x$`) and block (`$$...$$`) LaTeX math with prose currency symbol protection.
  - Code syntax highlighting with `#CODE#` tag processing.
- **Comment-Preserving Configuration**:
  - `m2a.toml` uses `tomlkit`, keeping all your comments and formatting intact when settings are updated.

---

## Installation

### Requirements
- **Python 3.11+**
- Anki Desktop (if syncing directly via AnkiConnect, ensure the [AnkiConnect](https://ankiweb.net/shared/info/2055492159) add-on is installed, code `2055492159`).

### Setup
```bash
git clone https://github.com/leon-3/Markdown2Anki.git
cd Markdown2Anki
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

---

## Quick Start

### 1. Initialize Configuration
Generate an `m2a.toml` configuration interactively:
```bash
m2a init
```
Or create one in the current directory:
```bash
m2a init --here
```

### 2. Check Vault Status
Parse notes, validate formatting, and check card counts without modifying any files:
```bash
m2a check
m2a status
```

### 3. Sync to Anki
Preview pending changes without making modifications:
```bash
m2a sync --dry-run
```

Export new cards into Anki:
```bash
m2a sync
```

Update previously exported cards that were modified in Obsidian:
```bash
m2a sync --update
```

---

## Note Format & Syntax

Cards are defined inside Markdown files delimited by horizontal rules (`---`):

````markdown
# Cryptography
## Block Ciphers
---
What is the primary security goal of a block cipher?
It provides confidentiality by transforming fixed-length plaintext blocks into ciphertext under a secret key.

---
What is a Key Schedule?
EQL: and why is it needed?
A key schedule expands a master key into round keys to prevent identical keys across rounds.

---
Cloze
{{c1::AES}} operates on fixed blocks of {{c2::128}} bits using key lengths of 128, 192, or 256 bits.

---
Image Cloze
![[feistel_network.png]]

---
How do you implement quicksort in C?
```c
#CODE#
void quicksort(int *arr, int low, int high) { ... }
```
````

### Rules & Conventions
1. **Card Separator**: A line starting with `---` starts a flashcard.
2. **Question**: The first non-empty line after `---`.
3. **Multi-line Questions**: Use `EQL: <additional line>` directly following the question.
4. **Answer**: Everything between the question and the next card separator or heading.
5. **Cloze Deletions**: Question line begins with `Cloze`. With `cloze_notes = true`, `{{c1::answer}}` generates native Anki cloze notes.
6. **Image Occlusions**: Question line begins with `Image Cloze` and references `![[image.png]]`. Media is staged into `<output_dir>/occlusions/` with an `index.md` mapping file.
7. **Code Blocks**: Code blocks containing `#CODE#` are automatically tagged with `TODO_PROCESS_CODE`.
8. **Math**: `$x$` produces inline math; `$$...$$` produces display math. Literal currency amounts (e.g. `$5 and $10`) are preserved.

---

## Configuration Reference (`m2a.toml`)

`m2a.toml` sits at the root of your Obsidian vault or in `~/.config/m2a/m2a.toml`:

```toml
# Path to your Obsidian vault (~ and relative paths supported)
vault = "~/Documents/ObsidianVault"

# Default fallback Anki deck
deck = "Default"
package_name = "default-package"

# Base tag prepended to all cards (optional)
base_tag = ""

# Output directory for standalone .apkg exports and occlusions
output_dir = "."

# Target: "anki" pushes via AnkiConnect; "apkg" writes a package file
target = "anki"
anki_connect_url = "http://127.0.0.1:8765"
anki_basic_model = "M2A Basic"
anki_cloze_model = "M2A Cloze"

# Convert Cloze cards with {{c1::}} into native Anki Cloze notes
cloze_notes = false

# Rename media to deterministic lowercase SHA-256 hashes
hash_media = true

# Re-stage previously flagged image occlusions on --update
re_stage_occlusions = false

# Format single-digit folder numbers with leading zeros (e.g. '1. Topic' -> '01_Topic')
pad_single_digit_tags = true

# Folders and glob patterns to ignore during scanning
ignore = [".git", ".obsidian", "templates", "archive/*", "ai"]

# Deck routing rules (longest-prefix match)
[deck_routing]
"everyday" = "01. everyday (focus)"
"everyday/work" = "01. everyday (focus)::02. work"
"pen and paper" = "02. pen and paper (work)"

# Tag path aliases (map folder paths to custom tags, or "" to omit)
[tag_aliases]
"everyday" = "01_everyday"
"pen and paper" = "02_pen_and_paper"
"templates" = ""  # suppresses tag generation for this folder level
```

> [!NOTE]
> **Backward Compatibility:** Legacy configuration files containing `[decks]`, `[subjects]`, or `[subdirectories]` are automatically migrated to `[deck_routing]` and `[tag_aliases]` on load.

---

## CLI Reference

| Command | Description |
| :--- | :--- |
| `m2a init` | Create configuration interactively (`--here` writes `./m2a.toml`, `--yes` accepts defaults). |
| `m2a config` | Inspect current configuration settings. |
| `m2a check` | Parse vault notes and report formatting warnings without modifying files. |
| `m2a status` | Display card counts (pending, added, total) per folder. |
| `m2a sync` | Export pending cards into Anki (`--update` updates existing cards, `--dry-run` previews). |
| `m2a unflag` | Remove `ADDED` flags from Markdown files to re-export cards as new notes. |
| `m2a templates` | Inspect and sync note type templates with Anki. |

---

## Python API

The core engine can be integrated into custom scripts or applications:

```python
from pathlib import Path
from markdown2anki.config import load_vault_config
from markdown2anki.vault import collect
from markdown2anki.build import build
from markdown2anki.export.ankiconnect import export_ankiconnect

vault_path = Path("~/Documents/ObsidianVault").expanduser()
cfg = load_vault_config(vault_path)

# Collect and parse all cards according to routing and ignore rules
collected = collect(cfg)
print(f"Discovered {len(collected.cards)} card(s)")

# Build and export pending cards to Anki
pending_cards = [c for c in collected.cards if c.pending]
if pending_cards:
    diagnostics = []
    result = build(pending_cards, diagnostics, vault_root=cfg.vault, hash_media=cfg.hash_media)
    report = export_ankiconnect(result, cfg=cfg)
    print(f"Exported: {report.added} added, {report.updated} updated")
```

---

## Running Tests

Run the full pytest suite:

```bash
pytest
```
