# Markdown2Anki

Turn flashcard notes written in Obsidian or standard Markdown into Anki cards.

Markdown2Anki provides both a CLI (`m2a`) and a Python library API. It exports flashcards, tracks them with stable IDs, routes cards across multiple decks, resolves image attachments automatically, and updates cards in place in Anki without resetting review histories or ease factors.

---

## Features

- **Direct Push or Standalone Package**:
  - **AnkiConnect** (`target = "anki"`): Pushes cards directly into a running Anki instance via HTTP.
  - **Anki Package** (`target = "apkg"`): Generates standalone `.apkg` files with bundled media.
- **In-Place Updates**:
  - Tags cards with lightweight markers: `ADDED: Question <!-- m2a:id -->`.
  - Re-sync cards with `m2a sync --update` to refresh content and tags in Anki without losing review schedules.
- **Deterministic Media Hashing**:
  - Embedded images are renamed to lowercase SHA-256 hashes (`<8hex>_01.ext`) with collision-safe counters, preventing media name clashes.
- **Flexible Directory Structure**:
  - Scans notes recursively at any folder depth, or optionally filters by specific category subdirectories.
- **Multi-Deck Routing**:
  - Map courses/folders to distinct decks declaratively via `[decks]` in `m2a.toml` or dynamically using `{course}` templates.
- **Rich Card Types**:
  - Standard Q&A, multi-line questions (`EQL:`), native Cloze deletions (`{{c1::...}}`), and Image Occlusion staging.
  - Inline (`$x$`) and display (`$$...$$`) math with prose currency protection.
  - Code syntax highlighting with `#CODE#` marker stripping.

---

## Installation

### Requirements
- **Python 3.11+**
- Anki (if syncing directly, install the [AnkiConnect](https://ankiweb.net/shared/info/2055492159) add-on, code `2055492159`).

### Install
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
Run `m2a init` to configure your vault interactively:
```bash
m2a init
```
This prompts for your vault path, course folders, target deck, and export mode, writing to `~/.config/m2a/m2a.toml` (or use `m2a init --here` for `./m2a.toml`).

### 2. Check Vault Status
Parse all notes and verify formatting without modifying any files:
```bash
m2a check
m2a status
```

### 3. Sync to Anki
Preview pending cards:
```bash
m2a sync --dry-run
```

Export pending cards into Anki:
```bash
m2a sync
```

To update already exported cards that you modified in your notes:
```bash
m2a sync --update
```

---

## Note Format & Syntax

Cards are separated inside Markdown files with a horizontal rule (`---`):

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

### Conventions
1. **Card Separator**: A line starting with `---` starts a card.
2. **Question**: The first non-empty line after `---`.
3. **Multi-line Questions**: Use `EQL: additional question line` immediately following the question.
4. **Answer**: Everything between the question and the next separator or heading.
5. **Cloze Deletions**: Question starts with `Cloze`. When `cloze_notes = true` in config, `{{c1::answer}}` generates native Anki Cloze notes.
6. **Image Occlusion**: Question starts with `Image Cloze` and references `![[image.png]]`. Source images are staged into `<output_dir>/occlusions/` with sequential IDs and a tag summary. Once flagged, occlusions are skipped during routine `--update` syncs (use `--stage-occlusions` to force re-staging).
7. **Code**: Code blocks containing `#CODE#` are automatically tagged with `TODO_PROCESS_CODE`.
8. **Math**: `$x$` produces inline math; `$$...$$` produces display math. Literal currency amounts (e.g. `$5 and $10`) are preserved as text.

---

## Vault Organization & Tagging

Markdown2Anki generates hierarchical tags from folder paths and Markdown headings:

```text
base_tag::course_tag::folder::note_name::Heading::Subheading
```

### Multi-Deck Routing
Configure deck targets in `m2a.toml`:
```toml
# Default fallback deck
deck = "University"

# Route specific courses to dedicated decks
[decks]
"Computer Science" = "University::CompSci"
"Mathematics" = "University::Math"
```
Or use dynamic deck naming:
```toml
deck = "University::{course}"
```

---

## Configuration Reference (`m2a.toml`)

```toml
# Path to your Obsidian vault (~ and relative paths supported)
vault = "~/Documents/ObsidianVault"

# Default Anki deck (use :: for subdecks; supports {course} placeholder)
deck = "University"

# File name for .apkg exports
package_name = "University"

# Root tag prepended to all cards (optional)
base_tag = "University"

# Directory where .apkg files and occlusions are written
output_dir = "."

# Export target: "anki" (AnkiConnect) or "apkg" (.apkg file)
target = "anki"
anki_connect_url = "http://127.0.0.1:8765"

# Note type names in Anki
anki_basic_model = "M2A Basic"
anki_cloze_model = "M2A Cloze"

# Convert Cloze cards with {{c1::}} into native Anki Cloze notes
cloze_notes = true

# Rename images to deterministic 8-hex lowercase hashes
hash_media = true

# Personal template directory (overrides bundled templates)
templates_dir = "~/.config/m2a/templates"

# Folders to ignore during scanning
ignore = [".git", ".obsidian", "Archive", "templates", "Slides"]

# Course folder -> Subject tag mapping (empty table exports all folders)
[subjects]
"Computer Science" = "CompSci"
"Mathematics" = "Math"

# Subdirectory filter (leave empty for recursive traversal at any depth)
[subdirectories]

# Course folder -> Target Anki deck mapping
[decks]
"Computer Science" = "University::CompSci"
"Mathematics" = "University::Math"

# Tag -> Title shown in card corner badge
[display]
"CompSci" = "Computer Science"
"Math" = "Mathematics"
```

---

## CLI Commands

| Command | Description |
| :--- | :--- |
| `m2a init` | Create configuration interactively (`--here` writes `./m2a.toml`, `--yes` accepts defaults). |
| `m2a config` | Display active configuration settings. |
| `m2a check` | Parse vault notes and report syntax errors or warnings without writing files. |
| `m2a status` | Display card counts (pending, added, total) per course folder. |
| `m2a sync` | Export pending cards and flag them in Markdown files (`--update` updates existing cards, `--dry-run` previews). |
| `m2a unflag` | Remove `ADDED` flags to re-export cards as new notes. |
| `m2a templates` | Compare local templates with Anki note types and push updates via AnkiConnect. |

### Common Flags
- `-c, --config PATH`: Use a specific configuration file.
- `--update`: Re-sync previously exported cards to update fields/tags in Anki.
- `--stage-occlusions`: Re-stage already-flagged image occlusions when running with `--update`.
- `--course PATTERN`: Limit operation to courses matching a substring or glob.
- `-n, --dry-run`: Preview actions without modifying cards or writing files.
- `-y, --yes`: Run without confirmation prompts.

---

## Public Python API

```python
from pathlib import Path
from markdown2anki import (
    parse_file,
    build,
    export_apkg,
    export_ankiconnect,
    write_flags,
    AnkiConnectError,
)

# 1. Parse markdown file into Card objects
cards = parse_file(
    Path("notes/crypto.md"),
    base_tag="ComputerScience",
    deck="CS::Crypto",
)

# 2. Build and render HTML / media / tags
result = build([c for c in cards if c.pending], vault_root=Path("notes"))

# 3. Export to Anki via AnkiConnect (or fallback to .apkg)
try:
    export = export_ankiconnect(result, deck="CS::Crypto")
    write_flags(export.flags)
except AnkiConnectError:
    export = export_apkg(result, output_path=Path("output/crypto.apkg"), deck="CS::Crypto")
    write_flags(export.flags)
```

---

## Card Templates & Styling

Note types (`M2A Basic` and `M2A Cloze`) use HTML/CSS templates in `markdown2anki/templates/`.

To customize styling, copy templates to your personal template directory (`~/.config/m2a/templates/`):
```text
~/.config/m2a/templates/
├── Basic/
│   ├── front.html
│   ├── back.html
│   └── styling.css
└── Cloze/
    ├── front.html
    ├── back.html
    └── styling.css
```

Push template or styling changes to Anki:
```bash
m2a templates
```

---

## Development & Testing

Run the test suite with `pytest`:

```bash
pytest
```

Unit and integration tests cover CLI commands, parsing, HTML/markdown rendering, media handling, multi-deck packaging, and AnkiConnect interactions.
