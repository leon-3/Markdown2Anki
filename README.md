# Markdown2Anki

[![Release](https://img.shields.io/badge/version-1.0.0-blue?style=flat-square)](https://github.com/leon-3/Markdown2Anki/releases)
[![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)](https://github.com/leon-3/Markdown2Anki/blob/main/LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11%2B-informational?style=flat-square)](https://www.python.org)

Markdown2Anki is a command-line tool and Python engine that turns flashcards in Obsidian or Markdown files into Anki cards. It lets you write flashcards in plain Markdown, routes cards to different decks using folder rules, handles hierarchical tags with aliases, and updates existing cards in Anki without resetting your review progress.

It also serves as the core parser inside [Anki-VaultSync](https://github.com/leon-3/Anki-VaultSync) for native sync in Anki Desktop, and pairs with two companion Obsidian plugins:
- [Anki Card Styling](https://github.com/leon-3/Obsidian-Anki-Card-Highlighting): Renders visual cloze badges, card types, Extra Question Line (`EQL:`) tags, and status bars in Obsidian.
- [Anki Cloze Deletion](https://github.com/leon-3/Obsidian-Anki-Cloze): Gives you quick shortcuts (`Ctrl+Shift+C` and `Ctrl+Alt+C`) to create clozes scoped to each card block.
- [Anki-VaultSync](https://github.com/leon-3/Anki-VaultSync): Native Anki Desktop add-on for direct GUI synchronization without external tools.

---

## Highlights & Key Features

- Two sync modes: Sync directly into a running Anki profile via AnkiConnect (`target = "anki"`), or compile standalone `.apkg` packages with bundled media files (`target = "apkg"`).
- Updates cards in place: Uses lightweight IDs in Markdown (`ADDED: ... %%id%%`) to update existing cards without resetting review intervals, ease factors, or card history.
- Smart deck routing: Maps folders to specific Anki decks using Longest Prefix Matching, so subfolder rules automatically override parent rules.
- Flexible tag aliases: Builds hierarchical Anki tags from your folders, with full control to rename or hide specific path segments.
- Automatic media bundling: Detects, hashes, and copies linked images, audio files, and image occlusions without missing attachments.
- Clean CLI commands: Includes an interactive setup wizard (`m2a init`), vault health checks (`m2a status`), drift detection (`m2a deleted`), and dry-run previews.

---

## Installation & Quickstart

### Installation from Source
Clone the repository and install Markdown2Anki into your Python environment:

```bash
git clone https://github.com/leon-3/Markdown2Anki.git
cd Markdown2Anki
pip install .
```

Verify that the CLI is installed:

```bash
m2a --version
```

### Quickstart Setup
1. Create a configuration file in your vault or project folder:
   ```bash
   m2a init
   ```
2. Follow the setup prompt to choose your vault folder, default deck, and target mode (`anki` for AnkiConnect or `apkg` for offline packages).
3. Check your notes for card statistics and formatting issues:
   ```bash
   m2a status
   ```
4. Sync new cards to Anki:
   ```bash
   m2a sync
   ```
5. Update existing modified cards:
   ```bash
   m2a sync -u
   ```

---

## Documentation

### 1. Card Syntax & Identifiers

#### Card Delimiters (`---`)
Cards are enclosed between standard horizontal rules (`---`). Any content outside these delimiters (regular notes, lecture summaries, outlines) is completely ignored by the parser.

#### Basic Q&A Cards
The question is placed on the line directly below `---`. All following lines before the next `---` become the answer:

```markdown
---
Where does cellular respiration occur?
It takes place primarily in the mitochondria of eukaryotic cells.

---
```

#### Sync Status & Card IDs (`ADDED:` / `%%id%%`)
When a card is synced for the first time, Markdown2Anki marks the question line with `ADDED:` and appends a unique 6-character ID (`%%id%%`):

```markdown
---
ADDED: Where does cellular respiration occur? %%k8f2a1%%
It takes place primarily in the mitochondria of eukaryotic cells.

---
```

- **Editing Synced Cards:** You can freely update the question or answer in Markdown. As long as `%%id%%` remains intact, running `m2a sync -u` updates the existing Anki note in place without resetting review statistics or scheduling.
- **Safety Guarantee:** The unique ID ties the Markdown note to the Anki note ID, preventing duplicate card creation across multiple sync runs.

#### Deleting Cards (`DELETED:`)
To remove a card from Anki, replace `ADDED:` with `DELETED:`:

```markdown
---
DELETED: Where does cellular respiration occur? %%k8f2a1%%
It takes place primarily in the mitochondria of eukaryotic cells.

---
```
Running `m2a sync` removes the note from Anki and cleans up the card block in your Markdown note. You can also run `m2a deleted` to detect any removed cards or drift between your vault and Anki.

#### Extra Question Lines (`EQL:`)
If a basic Q&A card needs an extra subtitle, context, or prompt on the front of the card, add `EQL:` on the line directly below the question:

```markdown
---
Where does cellular respiration occur?
EQL: Mention both the organelle and the energy molecule produced.
It takes place in the mitochondria and produces ATP.

---
```
The line with `EQL:` is rendered as a distinct subtitle beneath the main question on the front of the Anki card.

---

### 2. Cloze Deletion & Image Occlusion

#### Text Cloze Cards (`Cloze`)
To create a Cloze card, write `Cloze` on the line directly after `---`, followed by your text containing standard cloze markers `{{c1::answer}}` or `{{c1::answer::hint}}`:

```markdown
---
Cloze
Glycolysis occurs in the {{c1::cytoplasm}} and produces a net yield of {{c2::2 ATP}} molecules.

---
```

Once synced, `ADDED:` and the card ID are placed directly on the `Cloze` header line:

```markdown
---
ADDED: Cloze %%d4f8k2%%
Glycolysis occurs in the {{c1::cytoplasm}} and produces a net yield of {{c2::2 ATP}} molecules.

---
```

- **Unmasked Clozes & Tagging:** If you create a `Cloze` card that does not yet contain any `{{c1::...}}` deletions, the card is exported as a Cloze note and tagged with `TODO_PROCESS_CLOZES`.
- **Automatic Suspend & Unsuspend:** When `suspend_new_clozes = true`, unmasked cloze cards are suspended in Anki so empty placeholders do not appear in your study queue. Once deletions are added in Markdown or Anki, running `m2a sync` with unflagging enabled detects the completed note, automatically unsuspends it, and removes the `TODO_PROCESS_CLOZES` tag.

#### Image Occlusion Cards (`Image Cloze`)
To create an image occlusion card, write `Image Cloze` on the line directly after `---`, followed by a linked image:

```markdown
---
Image Cloze
![[Synapse-Diagram.png]]

---
```

Synced state:

```markdown
---
ADDED: Image Cloze %%o4fj5k3%%
![[Synapse-Diagram.png]]

---
```

Images linked inside cards are automatically hashed and copied to your Anki media folder or bundled directly into exported `.apkg` files.

- **Native vs. Legacy Mode (`image_occlusion_mode`):**
  - **Native Mode (`image_occlusion_mode = "native"`):** Creates native Anki Image Occlusion notes directly in Anki. Newly synced cards are tagged with `TODO_PROCESS_OCCLUSION` and suspended (`suspend_new_occlusions = true`) until you open Anki and draw your occlusion masks using Anki's native editor.
  - **Legacy Staging Mode (`image_occlusion_mode = "stage"`):** Exports the raw image to an external staging directory for manual external mask preparation without native Anki occlusion notes.
- **Automatic Unsuspend on Completion:** Once you draw masks on the card in Anki, running `m2a sync --unflag-occlusions` automatically verifies that masks exist, unsuspends the card for study, and removes the `TODO_PROCESS_OCCLUSION` tag.

---

### 3. Tag Generation & Heading Hierarchy

Tags in Anki are generated automatically from the note's folder location and the Markdown headings (`#`, `##`, `###`) placed above the card:

```markdown
# Biology
## Biochemistry

---
What is the function of ATP synthase?
Synthesizes ATP from ADP and inorganic phosphate.

---
```

This card is assigned the hierarchical Anki tag: `Biology::Biochemistry`.

#### Numbered Tag Padding (`pad_single_digit_tags`)
When enabled in `m2a.toml`, single-digit numbers followed by a space or punctuation in folder names and headings (e.g. `1. Anatomy` or `2-Biochemistry`) are automatically padded with a leading zero (`01_Anatomy::02_Biochemistry`). This ensures tags sort in natural numerical order in Anki's sidebar.

---

### 4. Tag & Deck Routing

You can customize where cards are placed and how tags are named based on their folder in your vault:

#### Deck Routing (Where cards go)
Deck routing in `[deck_routing]` maps vault folders to specific Anki decks using Longest Prefix Matching (LPM):

| Vault Folder Path | Target Deck in Anki |
| :--- | :--- |
| `Medicine` | `University::Medicine` |
| `Medicine/Cardiology` | `University::Medicine::Cardiology` |

- A card in `Medicine/Cardiology/Notes.md` goes to `University::Medicine::Cardiology`.
- A card in `Medicine/Anatomy/Notes.md` falls back to `University::Medicine`.
- Cards outside configured folders go to your default `deck`.

#### Tag Aliases (What tags get replaced)
Tag rules in `[tag_aliases]` let you shorten, rename, or hide specific folder segments in the generated Anki tags:

| Vault Folder Path | Tag Alias | Result in Anki Tag |
| :--- | :--- | :--- |
| `Courses/Semester_1` | `Sem1` | Folder segment `Courses/Semester_1` becomes `Sem1` |
| `Drafts` | `""` | Segment `Drafts` is completely removed from the tag |

---

### 5. Configuration Reference (`m2a.toml`)

```toml
[general]
vault_path = "/path/to/obsidian/vault"
deck = "University::Default"
target = "anki" # "anki" (via AnkiConnect) or "apkg" (standalone file)
pad_single_digit_tags = true
image_occlusion_mode = "native" # "native" or "stage"
suspend_new_occlusions = true
suspend_new_clozes = true
auto_unflag_occlusions = true

[deck_routing]
"Physics" = "University::Physics"
"Physics/Thermodynamics" = "University::Physics::Thermodynamics"
"Biology" = "University::Biology"

[tag_aliases]
"Physics/Thermodynamics" = "Thermo"
"Drafts" = "" # Excludes this folder from generated tags
```

- `vault_path`: Path to your Obsidian vault root.
- `deck`: Default destination deck when no specific folder rule matches (subdecks separated by `::`).
- `target`: `anki` to send cards to Anki via AnkiConnect HTTP API (`http://127.0.0.1:8765`), or `apkg` to generate an export package file.
- `pad_single_digit_tags`: When `true`, single numbers in headings/folders (like `1. Chapter` or `2-Lecture`) are zero-padded to `01_Chapter`, keeping tags sorted alphabetically in Anki.
- `image_occlusion_mode`: `"native"` to create Anki Image Occlusion notes, or `"stage"` for external legacy staging.
- `suspend_new_occlusions` / `suspend_new_clozes`: Suspends incomplete cards until masks or clozes are drawn.
- `auto_unflag_occlusions`: Automatically removes `TODO_PROCESS` tags and unsuspends completed notes.
- `[deck_routing]`: Maps folder prefixes to Anki decks using Longest Prefix Matching.
- `[tag_aliases]`: Replaces path segments in tags or hides them when mapped to `""`.

---

### 6. CLI Command Reference

For detailed options and flags for any command, run `m2a --help` or `m2a <command> --help`.

| Command | Key Flags | Description |
| :--- | :--- | :--- |
| `m2a init` | | Interactive setup wizard to generate `m2a.toml`. |
| `m2a status` | `-v`, `--course <name>`, `-f <file>` | Shows card overview per course/folder and runs vault health checks. |
| `m2a sync` | `-n` | Dry run: preview newly discovered cards without modifying files or Anki. |
| `m2a sync` | | Exports new cards to Anki and writes `ADDED:` flags with unique IDs. |
| `m2a sync` | `-u`, `--update` | Exports new cards and updates modified existing cards in Anki in place. |
| `m2a sync` | `--target apkg`, `-o <file>` | Exports cards and bundled media to an offline `.apkg` file. |
| `m2a sync` | `--unflag-occlusions` | Syncs vault and automatically unsuspends completed occlusions in Anki. |
| `m2a deleted` | `--suspend`, `--delete` | Detects drift and suspends or permanently deletes orphaned notes from Anki. |
| `m2a unflag` | | Removes `ADDED:` / `DELETED:` flags so cards can be re-exported as new. |
| `m2a config` | | Inspects or edits the active configuration file. |

---

## Development & Building

### Requirements
- Python 3.11+
- Virtual environment (`venv`)

### Setting Up Development
```bash
git clone https://github.com/leon-3/Markdown2Anki.git
cd Markdown2Anki
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Running Tests
Run the test suite (170 tests):

```bash
pytest tests
```

### Building the Package
```bash
python -m pip install build
python -m build
```
