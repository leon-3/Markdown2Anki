"""Process markdown notes from the input/ directory and export an Anki package."""
from pathlib import Path

from markdown2anki import build, export_apkg, parse_file, write_flags

if __name__ == "__main__":
    input_dir = Path("input")
    input_dir.mkdir(exist_ok=True)

    md_files = sorted(input_dir.glob("*.md"))
    if not md_files:
        print("No .md files found in 'input/'. Place .md files in 'input/' to generate cards.")
        exit(0)

    try:
        base_tag = input("Enter base tag (leave empty for none): ").strip()
    except EOFError:
        base_tag = ""

    all_cards = []
    for file_path in md_files:
        print(f"Processing file: '{file_path.name}'")
        all_cards.extend(parse_file(file_path, base_tag=base_tag))

    pending_cards = [c for c in all_cards if c.pending]
    if not pending_cards:
        print("No pending cards found in 'input/'.")
        exit(0)

    result = build(pending_cards, vault_root=input_dir)
    out_file = Path("output.apkg")
    export = export_apkg(result, output_path=out_file, deck="output")
    print(f"\nCreated package '{out_file}' with {export.note_count} notes and {export.media_count} media files.")
    if export.occlusion_dir and result.occlusions:
        print(f"Staged {len(result.occlusions)} image occlusion(s) to '{export.occlusion_dir}'.")
        for tag, filenames in export.staged_occlusions.items():
            print(f"\n{tag}")
            for fname in filenames:
                print(f"- {fname}")
    if export.flags:
        flagged, problems = write_flags(export.flags)
        if flagged:
            print(f"Flagged {flagged} card(s) as ADDED.")
        if problems:
            for prob in problems:
                print(f"  Warning: {prob}")
