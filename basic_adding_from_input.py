import os

from markdown2anki import file_to_preprocessed_cards, create_cards, create_package
from markdown2anki import ImageProcessor

if __name__ == "__main__":
    image_processor = ImageProcessor()
    base_tag = "University"
    note_list = []

    for file in os.listdir("input"):
        if file.endswith(".md"):
            print(f"Processing file '{file}'")
            with open(f"input/{file}", encoding="utf-8") as f:
                basic_cards = file_to_preprocessed_cards(f.read().split("\n"), file, base_tag)
                note_list += create_cards(basic_cards, image_processor)
        else:
            print(f"Skipped file '{file}' (not a markdown file)")

    create_package(note_list, image_processor, "output")