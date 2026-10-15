# Markdown2Anki

Turn flashcard notes written in Obsidian or standard Markdown into Anki cards.

Markdown2Anki provides both a powerful CLI (`m2a`) and a clean Python library API. It exports new flashcards, tracks them with stable IDs, routes cards across multiple decks, resolves image attachments automatically, and updates cards in place when edited without resetting review histories.

---

## Table of Contents

- [Key Features](#key-features)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Note Format & Syntax Guide](#note-format--syntax-guide)
- [Vault Organization & Tagging](#vault-organization--tagging)
- [Multi-Deck Configuration](#multi-deck-configuration)
- [Configuration Reference (`m2a.toml`)](#configuration-reference-m2atoml)
- [CLI Commands Reference](#cli-commands-reference)
- [Public Python API](#public-python-api)
- [Bundled Scripts](#bundled-scripts)
- [Card Templates & Styling](#card-templates--styling)
- [Development & Testing](#development--testing)

---

## Key Features

- **Two Export Targets**:
  - **AnkiConnect** (`target = "anki"`): Pushes cards directly into a running Anki instance via HTTP. No manual `.apkg` import needed.
  - **Anki Package** (`target = "apkg"`): Generates standalone `.apkg` files with bundled media and image occlusions.
- **Stable In-Note Card Tracking**:
  - Appends lightweight in-note flags: `ADDED[abc123]: Question`.
  - Cards updated in Obsidian can be refreshed in Anki with `m2a sync --update` without losing review schedules, ease factors, or intervals.
  - Recognizes and automatically migrates legacy flags (`ADDED: ` or `ADDED: [n12345]`).
- **Flexible Directory Traversal**:
  - Supports arbitrary folder depths, nested categories, and loose notes.
  - Optional strict subfolder category filters (e.g., `Anki - Lectures`, `Anki - Exercises`).
- **Multi-Deck Support**:
  - Route different courses or folders to distinct Anki decks declaratively via `[decks]` in `m2a.toml` or programmatically via the library.
  - Automatically packages multiple decks into a single `.apkg` file and ensures decks are created in Anki via AnkiConnect.
- **Robust Image Attachment Resolution**:
  - Discovers images referenced as `![[image.png]]` next to notes, inside local `attachments/`, `assets/`, or `media/` folders, or in a centralized vault attachment folder.
- **Rich Card Types & Formatting**:
  - Standard Q&A, Cloze deletions (`{{c1::...}}`), and Image Occlusion staging.
  - Inline math (`$x^2$`) and display math (`$$\sum_{i=1}^n i$$`) protected from markdown mangling.
  - Code syntax highlighting with `#CODE#` tag integration.
- **Decoupled Architecture**:
  - Use either the interactive CLI (`m2a`) or import functions directly in your own Python scripts (`from markdown2anki import parse_file, build, export_apkg`).

---

## Installation

### Requirements
- Python 3.9+
- Anki (if pushing cards directly, install the [AnkiConnect](https://ankiweb.net/shared/info/2055492159) add-on, code `2055492159`).

### Local Development Install
Clone this repository and install in editable mode:

```bash
git clone https://github.com/Hookyhook/Markdown2Anki.git
cd Markdown2Anki
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

### Making `m2a` Available Globally
To use the `m2a` command from any terminal window without activating the virtual environment:

```bash
ln -s /path/to/Markdown2Anki/.venv/bin/m2a ~/.local/bin/m2a
```
*(Make sure `~/.local/bin` is in your shell `$PATH`.)*

---

## Quick Start

### 1. Initialize Configuration
Run `m2a init` to configure your vault interactively:
```bash
m2a init
```
This prompts for your vault path, course folders, target deck, and export mode, saving the result to `~/.config/m2a/m2a.toml` (or use `m2a init --here` to create `./m2a.toml`).

### 2. Check Your Vault
Parse all notes and verify there are no syntax errors or duplicate image names:
```bash
m2a check
m2a status
```

### 3. Preview and Sync
Preview pending notes without modifying any files:
```bash
m2a sync --dry-run
```
Export pending cards into Anki:
```bash
m2a sync
```
`m2a sync` pushes the cards to Anki (or writes `.apkg`), then prompts to mark the exported cards with `ADDED[id]:` in your notes.

---

## Note Format & Syntax Guide

Cards are defined inside Markdown files using a horizontal rule (`---`) to separate cards:

````markdown
# Cryptography
## Block Ciphers
---
What is the primary security goal of a block cipher?
It provides confidentiality by transforming fixed-length blocks of plaintext into ciphertext indistinguishable from random bits under a secret key.

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
1. **Card Separator**: A line starting with `---` starts a card.
2. **Question**: The first non-empty line after `---` is the question.
3. **Multi-line Questions**: Use `EQL: extra question line` immediately following the question.
4. **Answer**: Everything between the question and the next `---` or `# Heading`.
5. **Cloze Cards**:
   - Start the question with `Cloze`.
   - When `cloze_notes = true` in config, markers like `{{c1::answer}}` become native Anki Cloze notes.
   - When `cloze_notes = false`, exported as a basic card tagged with `TODO_PROCESS_CLOZES`.
6. **Image Occlusion**:
   - Start the question with `Image Cloze` and place `![[diagram.png]]` in the answer.
   - Source images are staged into `<output_dir>/occlusions/` with sequential IDs, and a summary grouped by tag is printed to the terminal.
7. **Code**: Code blocks containing `#CODE#` are automatically tagged with `TODO_PROCESS_CODE`, and the marker is stripped.
8. **Math**: Single dollar `$x$` produces inline KaTeX math; `$$...$$` produces display math. Literal currency amounts like `$5 and $10` are recognized as prose and untouched.

---

## Vault Organization & Tagging

Markdown2Anki tags cards hierarchically based on your directory structure and Markdown headings:

```text
base_tag::course_tag::folder::note_name::Heading::Subheading
```

### Flexible Directory Structure (Recommended)
When `[subdirectories]` is left empty in `m2a.toml`, Markdown2Anki recursively scans folders at any depth:

```text
My Vault/
├── Computer Science/                 -> Top-level course
│   ├── Algorithms/                   -> Subfolder
│   │   ├── Sorting.md                -> Flashcard note
│   │   └── attachments/              -> Local image folder
│   │       └── tree.png
│   └── Loose Note.md                 -> Loose file in course folder
└── Mathematics/
    └── Probability.md
```

### Strict Category Filtering (Fixed Categories Style)
If you define `[subdirectories]`, only matching category folders are scanned:

```toml
[subdirectories]
"Anki - Lectures" = "Lectures"
"Anki - Exercises" = "Exercises"
```

Notes placed outside these subfolders will be reported as skipped by `m2a check`.

---

## Multi-Deck Configuration

Markdown2Anki allows routing cards from different folders to different Anki decks.

### 1. Explicit Deck Mapping (`[decks]` table)
In `m2a.toml`:
```toml
deck = "University"  # Default fallback deck

[decks]
"Computer Science" = "University::CompSci"
"Mathematics" = "University::Math"
"Languages" = "General::Languages"
"Personal Projects" = "General::Projects"
```

### 2. Dynamic Deck Template (`{course}` placeholder)
```toml
deck = "University::{course}"
```
This automatically routes cards in each course folder to a subdeck named after that course.

---

## Configuration Reference (`m2a.toml`)

```toml
# Path to your Obsidian vault (absolute or relative to this file; ~ supported)
vault = "~/Documents/ObsidianVault"

# Default Anki deck (use :: for subdecks; supports {course} placeholder)
deck = "University"

# File name for .apkg exports (defaults to deck name)
package_name = "University"

# Root tag prepended to all cards (may be empty)
base_tag = "University"

# Directory where .apkg files and occlusions are written
output_dir = "."

# Export target: "anki" (AnkiConnect) or "apkg" (.apkg file)
target = "anki"
anki_connect_url = "http://127.0.0.1:8765"

# Note type names used in Anki
anki_basic_model = "M2A Basic"
anki_cloze_model = "M2A Cloze"

# Convert Cloze cards with {{c1::}} into native Anki Cloze notes
cloze_notes = true

# Personal template directory (overrides bundled templates)
templates_dir = "~/.config/m2a/templates"

# Folders to ignore during scanning
ignore = [".git", ".obsidian", "Archive", "templates", "Slides"]

# Course folder -> Subject tag mapping (empty table exports all folders)
[subjects]
"Computer Science" = "CompSci"
"Mathematics" = "Math"

# Subdirectory filter (leave empty for recursive arbitrary depth traversal)
[subdirectories]

# Folder -> specific target Anki deck
[decks]
"Computer Science" = "University::CompSci"
"Mathematics" = "University::Math"

# Tag -> Title displayed in card corner badge
[display]
"CompSci" = "Computer Science"
"Math" = "Mathematics"
```

---

## CLI Commands Reference

| Command | Description |
| :--- | :--- |
| `m2a init` | Create configuration interactively (`--here` writes `./m2a.toml`, `--yes` accepts defaults). |
| `m2a config` | Display the active configuration file and its contents. |
| `m2a check` | Parse all notes in the vault and report syntax errors/warnings without changing files. |
| `m2a status` | Display a breakdown of total, added, and pending cards per folder. |
| `m2a sync` | Export pending cards and flag them in Obsidian notes. |
| `m2a unflag` | Remove `ADDED[id]:` flags so cards can be re-exported as new notes. |
| `m2a templates` | Compare local templates with Anki note types and push changes via AnkiConnect. |

### Global CLI Flags
- `-c, --config PATH`: Specify a custom config file (e.g. `m2a -c ~/other_vault.toml sync`).
- `--vault PATH`: Override the vault path from configuration.
- `--course PATTERN`: Restrict command execution to courses matching a substring or glob.
- `--trace`: Enable verbose step-by-step diagnostic logging (or set `M2A_TRACE=1`).

---

## Public Python API

Markdown2Anki exposes a modular Python API for automation scripts and custom pipelines:

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
    deck="CS::Crypto"
)

# 2. Filter pending (unflagged) cards
pending_cards = [c for c in cards if c.pending]

# 3. Build and render HTML / media / tags
result = build(pending_cards, vault_root=Path("notes"))

# 4A. Export to Anki via AnkiConnect
try:
    export = export_ankiconnect(result, deck="CS::Crypto")
    flagged, errors = write_flags(export.flags)
    print(f"Pushed {export.added} notes, flagged {flagged} cards.")
except AnkiConnectError:
    # 4B. Fallback to .apkg export
    export = export_apkg(result, output_path=Path("output/crypto.apkg"), deck="CS::Crypto")
    flagged, errors = write_flags(export.flags)
    print(f"Wrote {export.note_count} notes to .apkg.")
```

---

## Bundled Scripts

- **`basic_adding_from_input.py`**:
  Simple scratchpad script. Place any markdown files in `input/` and run `python basic_adding_from_input.py` to produce `output/output.apkg`.
- **`add_files_from_university_vault.py`**:
  Convenience script that wraps `m2a sync` using [`m2a.toml`](file:///home/leon/Coding/Markdown2Anki/m2a.toml).

---

## Card Templates & Styling

The note types (`M2A Basic` and `M2A Cloze`) are built from HTML/CSS templates in `markdown2anki/templates/`.

### Customizing Templates
To customize your card styling, copy the template files into your personal templates directory (`~/.config/m2a/templates/`):
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

### Corner Subject Badges (`subject_script.html`)
Templates contain `<div class="subject" id="subject"></div>` and `__M2A_SUBJECT_SCRIPT__`.
During build, Markdown2Anki replaces this with a script that evaluates the card's `{{Tags}}` against your `[display]` table and sets the title in the corner badge.

To push template or CSS updates to existing note types in Anki:
```bash
m2a templates
```

---

## Development & Testing

Run the test suite using `pytest`:

```bash
pytest
```

All 69 unit and integration tests cover CLI commands, parsing, build rendering, image resolution, multi-deck packaging, AnkiConnect interaction, and script execution.
