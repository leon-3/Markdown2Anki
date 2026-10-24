# Markdown2Anki

**Markdown2Anki** is a fast, modular parser and synchronization engine that converts flashcard notes written in Obsidian or standard Markdown into Anki cards.

It provides both an interactive command-line interface (`m2a`) and a decoupled Python library API. It parses Markdown notes, tracks flashcards with lightweight persistent IDs, routes cards across multiple decks using Longest-Prefix Matching (LPM), generates hierarchical tags with configurable folder aliasing, deterministically hashes media attachments, and updates existing cards in Anki in-place—retaining review schedules, intervals, and ease factors.

> [!TIP]
> **Prefer a graphical desktop interface?**
> Check out the companion Anki Desktop add-on [**Anki-VaultSync**](../Anki-VaultSync), which embeds this engine directly inside Anki Desktop with a visual dashboard, live status bar indicator, rich HTML diff inspector, safety backups, and tabbed configuration.

---

## Key Features

- **Dual Target Modes**:
  - **AnkiConnect** (`target = "anki"`): Directly syncs notes into a running Anki instance via HTTP API (`http://127.0.0.1:8765`).
  - **Anki Package** (`target = "apkg"`): Generates standalone `.apkg` files with bundled media for offline sharing or manual import without requiring AnkiConnect.
- **In-Place Card Updates**:
  - Tags cards with compact 6-character IDs embedded in Markdown (`ADDED: Question %%k3f9qz%%`) and Anki (`<!--m2a:id-->`).
  - Run `m2a sync --update` to push edits into Anki in place—retaining review intervals, ease factors, and card learning history.
- **Deck Rules & Longest-Prefix Routing (`[deck_routing]`)**:
  - Map vault folders and nested subdirectories directly to target Anki decks. More specific nested rules automatically override parent folder rules (e.g. `courses/cs101` overrides `courses`).
- **Tag Rules & Folder Aliasing (`[tag_aliases]`)**:
  - Automatically converts vault directory hierarchies into natural hierarchical tags (e.g. `Folder::Subfolder`).
  - Custom replacements or tag suppression via `[tag_aliases]` (e.g. mapping `"archive" = ""` suppresses that folder level from generated tags).
  - Optional single-digit padding (`pad_single_digit_tags = true`) transforms `'1. Topic'` into `'01_Topic'` for clean alphabetical sorting, while protecting alphanumeric terms like `MP3`, `ISO9001`, or `2D Geometry`.
- **Native Image Occlusions & Offline Staging**:
  - **Native Mode** (`image_occlusion_mode = "native"`): Directly creates Anki 23.10+ / 24+ Image Occlusion notes with `TODO_PROCESS_OCCLUSION` tags, suspending new cards until masks are drawn in Anki.
  - **Auto-Unflagging**: Automatically unsuspends cards and removes the `TODO_PROCESS_OCCLUSION` tag once masks are drawn (`m2a sync --unflag-occlusions`).
  - **Staging Mode** (`image_occlusion_mode = "stage"`): Copies image assets into an `occlusions/` staging folder alongside an `index.md` mapping file for manual card creation.
- **Deterministic Media Hashing & Path Containment**:
  - Embedded images and media attachments are renamed to deterministic lowercase SHA-256 hashes (`<8hex>_01.ext`) with collision-safe counters.
  - Strictly enforces path boundary containment to prevent directory traversal outside the vault root.
- **Two-Way Drift & Deletion Detection (`m2a deleted`)**:
  - Detects notes deleted from your Obsidian vault (orphaned cards in Anki) and allows suspending or deleting them.
  - Detects notes deleted in Anki that still have sync IDs in Markdown, allowing you to mark them as `DELETED:` in Obsidian or re-export them into Anki.
- **Rich Card Formatting**:
  - Standard Q&A, multi-line questions (`EQL:`), and native Cloze deletions (`{{c1::...}}`).
  - Inline (`$x$`) and block (`$$...$$`) LaTeX math with prose currency symbol protection.
  - Fenced code block syntax highlighting with `#CODE#` tag processing.
- **Comment-Preserving Configuration**:
  - `m2a.toml` is read and written using `tomlkit`, preserving all comments, indentation, and structure when settings are modified.

---

## Installation

### Requirements
- **Python 3.11+**
- **Anki Desktop** (if syncing directly via AnkiConnect, ensure the [AnkiConnect](https://ankiweb.net/shared/info/2055492159) add-on is installed, code `2055492159`).

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
Parse notes, validate formatting, and review card counts without modifying any files:
```bash
m2a status
m2a status -v
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

Sync vault and automatically unsuspend completed Image Occlusions:
```bash
m2a sync --update --unflag-occlusions
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

### Syntax Rules & Conventions
1. **Card Separator**: A line starting with `---` starts a flashcard.
2. **Question**: The first non-empty line after `---`.
3. **Multi-line Questions**: Use `EQL: <additional line>` directly following the question.
4. **Answer**: Everything between the question and the next card separator or heading.
5. **Cloze Deletions**: Question line begins with `Cloze`. With `cloze_notes = true`, `{{c1::answer}}` generates native Anki cloze notes.
6. **Image Occlusions**: Question line begins with `Image Cloze` and references `![[image.png]]`.
   - In `native` mode, creates an Image Occlusion note in Anki ready for masking.
   - In `stage` mode, copies images into `<output_dir>/occlusions/` with an `index.md` mapping file.
7. **Code Blocks**: Code blocks containing `#CODE#` or `PCL` are automatically tagged with `TODO_PROCESS_CODE`.
8. **Math**: `$x$` produces inline math `\(x\)`; `$$...$$` produces display math `\[...\]`. Literal currency amounts (e.g. `$5 and $10`) are preserved.

---

## Configuration Reference (`m2a.toml`)

`m2a.toml` sits at the root of your Obsidian vault or in `~/.config/m2a/m2a.toml`:

```toml
# Path to your Obsidian vault (~ and relative paths supported)
vault = "~/Documents/ObsidianVault"

# Default Target Deck: fallback Anki deck for cards without explicit folder rule
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

# Convert Cloze cards with {{c1::...}} syntax into native Anki Cloze notes
cloze_notes = true

# Image Occlusion mode: "native" (creates native Anki IO notes) or "stage" (offline folder staging)
image_occlusion_mode = "native"

# Suspend newly synced Image Occlusion cards until masks are drawn in Anki
suspend_new_occlusions = true

# Suspend newly synced unmasked Cloze cards until clozes are added in Anki
suspend_new_clozes = true

# Freeze Image Occlusion notes so subsequent syncs do not overwrite drawn masks
freeze_image_occlusions = false

# Automatically unsuspend and unflag completed image occlusions and text clozes during sync
auto_unflag_occlusions = true

# Rename media to deterministic lowercase SHA-256 hashes (e.g. 472d6b17_01.png)
hash_media = true

# Format single-digit folder numbers with leading zeros (e.g. '1. Topic' -> '01_Topic')
pad_single_digit_tags = true

# Folders and glob patterns to ignore during scanning
ignore = [".git", ".obsidian", "templates", "archive/*", "ai"]

# Deck Rules & Folder Mapping (Longest-Prefix Matching)
[deck_routing]
"courses" = "01. University"
"courses/cs101" = "01. University::CS101"
"work" = "02. Professional"

# Tag Rules & Folder Aliases (map folder paths to custom tags, or "" to suppress)
[tag_aliases]
"courses" = "01_uni"
"work" = "02_work"
"templates" = ""  # suppresses tag generation for this folder level
```

> [!NOTE]
> **Backward Compatibility:** Legacy configuration files using `[decks]`, `[subjects]`, or `[subdirectories]` are automatically migrated to `[deck_routing]` and `[tag_aliases]` on load.

---

## CLI Reference

### Core Workflow Commands

| Command | Description |
| :--- | :--- |
| `m2a status` | Display card counts (pending, added, total) per folder and perform vault health checks. |
| `m2a status -v` | Display detailed card list with line numbers, IDs, and diagnostics. |
| `m2a status --course <name>` | Filter status overview by course or folder. |
| `m2a status -f <file>` | Inspect a single Markdown note file. |
| `m2a sync` | Export new cards to Anki and write `ADDED: ... %%id%%` flags to Markdown notes. |
| `m2a sync -u`, `--update` | Update previously exported cards in Anki in place. |
| `m2a sync -n`, `--dry-run` | Preview pending card creations and updates without modifying files or Anki. |
| `m2a sync --target apkg` | Export offline `.apkg` package with bundled media files. |
| `m2a sync --unflag-occlusions` | Sync vault and unsuspend completed Image Occlusion cards in Anki. |
| `m2a sync --unflag-occlusions-only` | Only unsuspend completed Image Occlusion cards in Anki (skips vault scan). |

### Setup & Maintenance Commands

| Command | Description |
| :--- | :--- |
| `m2a init` | Interactive wizard to create `~/.config/m2a/m2a.toml` (`--here` writes `./m2a.toml`, `-y` accepts defaults). |
| `m2a config` | Inspect active configuration (`--validate` checks semantics, `--raw` prints TOML, `--edit` opens in `$EDITOR`). |
| `m2a deleted` | Detect drift between vault and Anki (removed vault notes or deleted Anki cards). |
| `m2a deleted --suspend` | Suspend orphaned Anki cards whose source notes were removed from vault (preserves history). |
| `m2a deleted --delete` | Permanently delete orphaned notes from Anki. |
| `m2a deleted --mark-deleted` | Mark notes deleted in Anki as `DELETED: ... %%id%%` in Markdown vault. |
| `m2a deleted --recreate` | Re-export notes deleted in Anki back into Anki. |
| `m2a unflag` | Remove `ADDED` and `DELETED` flags from notes so they can be re-exported as new cards (`-n` dry-run). |

---

## Architecture & Integration

Markdown2Anki is designed with strict separation between pure parsing/rendering logic and external side effects:

```
Markdown Files (.md)
       │
       ▼
┌───────────────────────────────┐
│   markdown2anki Core Engine   │
│   - vault.py (LPM routing)    │
│   - parser.py (Card models)   │
│   - render.py (HTML / Math)   │
│   - ids.py & flags.py         │
│   - build.py (Media hashing)  │
└───────┬───────────────┬───────┘
        │               │
        │ Pure Python   │ CLI dependencies
        │ Vendored      │ (typer, rich, questionary)
        ▼               ▼
┌──────────────┐ ┌──────────────┐
│Anki-VaultSync│ │   m2a CLI    │
│(Anki Add-on) │ │  (Standalone)│
└──────────────┘ └──────────────┘
```

The core package (`markdown2anki`) does not depend on CLI libraries (`typer`, `rich`, `questionary`) or `genanki`. This enables **Anki-VaultSync** to vendor the pure-Python core directly into Anki Desktop with zero dependency conflicts and near-instant load times.

---

## Python API

You can embed Markdown2Anki into your own Python scripts or automated pipelines:

```python
from pathlib import Path
from markdown2anki.config import load_vault_config
from markdown2anki.vault import collect
from markdown2anki.build import build
from markdown2anki.export.ankiconnect import export_ankiconnect

# Load vault configuration
vault_path = Path("~/Documents/ObsidianVault").expanduser()
cfg = load_vault_config(vault_path)

# Discover and parse all flashcards
collected = collect(cfg)
print(f"Discovered {len(collected.cards)} card(s)")

# Render pending cards and export via AnkiConnect
pending_cards = [c for c in collected.cards if c.pending]
if pending_cards:
    diagnostics = []
    result = build(
        pending_cards,
        diagnostics,
        cloze_notes=cfg.cloze_notes,
        vault_root=cfg.vault,
        hash_media=cfg.hash_media,
        image_occlusion_mode=cfg.image_occlusion_mode,
    )
    report = export_ankiconnect(result, cfg=cfg)
    print(f"Exported: {report.added} added, {report.updated} updated")
```

---

## Running Tests

Run the full pytest suite:

```bash
pytest
```
