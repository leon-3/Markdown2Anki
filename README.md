# Markdown2Anki

Turn flashcard notes written in Obsidian into Anki cards. `m2a sync` exports everything that is new,
marks it as added in the notes, and can update cards later when you fix them.

- [Getting started](#getting-started)
- [How the vault is read](#how-the-vault-is-read)
- [Note format](#note-format)
- [Commands](#commands)
- [What `sync` does](#what-sync-does)
- [Configuration](#configuration)
- [Card templates](#card-templates)
- [Development](#development)

## Getting started

Requirements: Python 3.9+, Anki. For the default export target you also need the
[AnkiConnect](https://ankiweb.net/shared/info/2055492159) add-on (code `2055492159`) and Anki open.

```bash
pipx install git+https://github.com/<you>/Markdown2Anki   # or: pip install -e . in a clone
m2a init                                                   # asks about your vault, courses, deck, target
m2a check                                                  # parses every note, reports problems, changes nothing
m2a sync --dry-run                                         # shows what the first export would contain
m2a sync                                                   # exports, then asks before flagging the notes
```

`m2a init` walks you through the configuration and writes it to `~/.config/m2a/m2a.toml`: where the
vault is, which top-level folders are courses (a checkbox list) and which tag each gets, which subfolders
hold notes, the deck, the export target, and so on. Every answer has a sensible default, so Enter through
it works. `m2a init --yes` skips the questions and uses options and defaults; a pre-CLI `.env` in the
current directory is picked up automatically.

Two ways to get cards into Anki:

- **AnkiConnect** (`target = "anki"`, the default): `m2a sync` pushes cards straight into the deck of a
  running Anki. Updates find the existing note; no import step.
- **Package file** (`target = "apkg"`): `m2a sync` writes `<output_dir>/<package_name>.apkg`; import it in Anki
  with File → Import. Re-importing a package with changed cards updates them (Anki matches the GUID).

Both targets embed the same id in the note, so a card can be updated through either one later.

**Trying it on a throw-away Anki profile first?** Run `m2a sync --no-flag`. Flags written against a test
profile carry ids that mean nothing in your real one.

## How the vault is read

```
<vault>/
├── 50.054 Compiler Design and Program Analysis/     course  -> subject tag
│   ├── Anki - Lectures/                             folder  -> category tag
│   │   ├── W01 Introduction.md                      note    -> tag, one card per block
│   │   └── Pasted image 2026....png                 images live next to the note
│   └── Anki - Exercises/
├── Archive/                                         ignored
└── templates/                                       ignored
```

Exactly two levels: `<course>/<subdirectory>/*.md`. Courses are the folders listed in `[subjects]` (or every
top-level folder not in `ignore` when the table is empty); every subfolder that holds notes must be in
`[subdirectories]`, anything else is reported by `m2a check`. Cards are tagged
`base_tag::subject::category::note::heading::subheading`.

## Note format

````markdown
# Heading                        -> extra tag; ## nests below it
---
A question on the first line
EQL: an extra question line
The answer: any markdown - **bold**, lists, `code`, $x^2$, $$display math$$, ![[image.png]]

---
Cloze
Exported as a basic note tagged TODO_PROCESS_CLOZES, deletions added by hand in Anki.
With `cloze_notes = true` in the config, {{c1::deletions}} here become a real cloze note.

---
Image Cloze
![[diagram.png]]                 -> image copied to <output_dir>/occlusions/<tag>/ for manual occlusion

---
Question about code?
```c
#CODE#                           -> tagged TODO_PROCESS_CODE; the marker line is removed
int x = 1;
```
````

Rules: a line of `---` starts a card; the next non-empty line is the question; everything up to the next
separator or heading is the answer. Blank slots (`---` followed by blank lines) are ignored. Fenced code,
inline code and math are never touched by symbol replacement or the markdown parser; `->` and `=>` in
prose become `→` and `⇒`. `$5 and $10` is prose, `$x$` is math.

Images are referenced by file name in Anki, so two different images with the same name in different
folders would overwrite each other. `m2a check` reports such clashes; rename one of the files.

## Commands

| Command | What it does |
| --- | --- |
| `m2a init` | Create the config interactively. `--yes` for no questions, `--here` for `./m2a.toml`, `--force` to replace (keeps a `.bak`). |
| `m2a config` | Show which config file is in use and its contents. |
| `m2a check [-v]` | Parse every note and report problems. Exit code 1 if there are errors. `-v` lists every card. |
| `m2a status` | Cards total / added / pending per course folder. |
| `m2a sync` | Export pending cards, then flag them in the notes. See below. |
| `m2a unflag` | Remove `ADDED` flags so cards go out again as new notes. Filters: `--course`, `--file`, `--legacy`. |
| `m2a templates` | Compare the local card templates with the note types in Anki and push them. `--diff` only compares. |

Global options: `-c PATH` picks a config file, `--vault PATH` overrides the vault, `--trace` logs each phase
to stderr (also `M2A_TRACE=1`), `--version`. `--course NAME` on `check`, `status`, `sync` and `unflag`
restricts to one course by folder name or tag (glob or substring). Colours are off when stdout is not a
terminal or `NO_COLOR` is set.

## What `sync` does

1. Parse all notes, build the pending cards (and, with `--update`, the already-added ones that have an id).
2. Export them via AnkiConnect or as an `.apkg`, depending on `target` in the config or `--target`.
3. Ask, then flag each exported question: `ADDED: <question> %%k3f9qz%%`. The `%%…%%` part is an Obsidian
   comment (hidden in reading view) holding a short id; the same id is embedded invisibly in the Anki note.

```
m2a sync --dry-run            # list what would be exported
m2a sync --course compiler    # only courses whose folder or tag matches
m2a sync --no-flag            # export without touching the notes
m2a sync --update             # re-export flagged cards too -> updates them in Anki
m2a sync --target apkg -o x.apkg
m2a sync -y                   # do not ask before flagging
```

Flags are written only after the export succeeded, and only if the question line is still what was
parsed. Cards flagged by an older version (`ADDED: ` without id) are skipped and cannot be updated.

Updates work through either target: an `.apkg` re-import matches the note by GUID (derived from the id),
AnkiConnect finds it by the embedded `<!--m2a:id-->` marker. A card that is not in Anki any more (deleted,
other profile) is skipped with a warning.

To export a card **again as a new note** - after a test on a throw-away profile, after deleting it in
Anki, or to move old `ADDED:` cards to the new flow - remove its flag with `m2a unflag`. It lists the cards
and asks before touching the notes.

## Configuration

`m2a.toml` lives in `~/.config/m2a/` (`$XDG_CONFIG_HOME/m2a/`) so `m2a` works from any directory.
`m2a init --here` writes it to the current directory instead. Lookup order: `-c PATH`, then `m2a.toml` in
the current directory or any parent, then the user config. `m2a config` shows which one is in use.

```toml
vault = "~/Documents/obsidian"

deck = "SUTD"                 # use :: for subdecks
package_name = "SUTD"         # file name of the .apkg export
base_tag = "SUTD"             # prepended to every card; may be empty
output_dir = "~/Downloads/Markdown2Anki"

target = "anki"               # default for `m2a sync`; "apkg" writes a package file instead
anki_connect_url = "http://127.0.0.1:8765"
anki_basic_model = "M2A Basic"   # note type names used by the AnkiConnect target
anki_cloze_model = "M2A Cloze"

cloze_notes = false           # true: {{c1::}} markers in a Cloze card -> real cloze note
templates_dir = "~/.config/m2a/templates"

ignore = [".git", ".obsidian", "Archive", "templates"]

[subjects]                    # course folder -> tag; empty table = every folder, tag = folder name
"50.054 Compiler Design and Program Analysis" = "50.054_Compiler"

[subdirectories]              # folder inside a course -> tag
"Anki - Lectures" = "Lectures"
"Anki - Exercises" = "Exercises"

[display]                     # tag -> title shown in the corner of the card; first match wins
"50.054_Compiler" = "Compiler Design and Program Analysis"
```

Relative paths are relative to the config file. Unknown keys are rejected so typos do not pass silently.

## Card templates

The bundled templates under `markdown2anki/templates/{Basic,Cloze}/` define the two note types. To use
your own, put files with the same names into `<templates_dir>/{Basic,Cloze}/` (`front.html`,
`back.html`, `styling.css`); each file overrides the bundled one individually. `m2a config` shows the
directory in use.

A template may contain `__M2A_SUBJECT_SCRIPT__`; it is replaced with a script that shows the `[display]`
title matching the card's tag. Without the placeholder nothing is injected.

`sync` never modifies a note type that already exists in Anki. To bring changed templates into Anki, run
`m2a templates`: it shows what differs and asks before replacing the note type's card template and
styling. Cards and review history are untouched.

The AnkiConnect target first looks for the note types that earlier `.apkg` imports created (by their ids,
so a stock note type with the same name is never picked by mistake); otherwise it uses the names in
`anki_basic_model` / `anki_cloze_model`, creating them from the templates if missing.

## Development

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
pytest
```

Dependencies: [genanki](https://github.com/kerrickstaley/genanki) and Markdown for the cards,
[Typer](https://typer.tiangolo.com/) for the command line, [Rich](https://github.com/Textualize/rich) for
output, [questionary](https://github.com/tmbo/questionary) for the `init` prompts.

Layout:

| Module | Role |
| --- | --- |
| `cli.py` | Argument parsing; dispatches to `commands/` |
| `commands/` | One module per subcommand; only place that prints |
| `config.py` | `Config` dataclass, lookup, loading, `.env` migration, TOML rendering |
| `vault.py` | Finds notes in the vault and parses them into cards |
| `parser.py` | Markdown note -> `Card` objects and diagnostics |
| `build.py` | `Card` -> `RenderedNote` (markdown to HTML, images, tags) |
| `render.py`, `formatting.py` | Markdown to Anki HTML, protecting code and math |
| `ids.py`, `flags.py` | Card ids, `ADDED` flags in the notes |
| `models.py`, `templates/` | Anki note types and the bundled card templates |
| `export/apkg.py`, `export/ankiconnect.py` | The two export targets |
