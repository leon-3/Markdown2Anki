import random
import warnings

import genanki

from .notes import Note, Cloze
from .helpers.tag_handler import handle_tags, merge_tags
from .helpers.text_formatting import get_preprocessors
from .helpers.image_processor import ImageProcessor
from .helpers.processors import apply_processors

FORMAT_WARNING_STRING = ("Field contained the following invalid HTML tags. Make sure you are calling html.escape() if "
                         "your field data isn't already HTML-encoded:")


def file_to_preprocessed_cards(input_lines: list, file_name: str, base_tag: str) -> list:
    """
    Given a list of lines from a markdown file, parse the lines and add them to the Anki package that will be exported.
    :param input_lines: list of lines from the input file
    :param file_name: name of the input file (will be used as the last part of the tag - e.g. "Python::FileName")
    :param base_tag: base tag for the package (e.g. "Python")
    :return: list of cards that need to be processed into different note types
    """

    # List is required since tags change dynamically with the handle_tags function, also cut the .md file extension
    tags = [base_tag, file_name[:-3]]
    new_question = False  # Indicates that "---" is found, and it is likely that a new question will be following
    latest_question = ""
    latest_answer = ""
    card_list = []

    def add_card_if_not_empty():
        if latest_question:
            note = Note(latest_question, latest_answer, [merge_tags(tags)])
            apply_processors(note, get_preprocessors())
            card_list.append(note)

    for line in input_lines:
        # Case 1: Line starts with a tag (Heading in a markdown file) -> Update Tags and reset card
        if line.startswith("#"):
            add_card_if_not_empty()
            latest_question = ""
            latest_answer = ""
            tags = handle_tags(line, tags)

        # Case 2: Line starts with a "---" -> Reset card and process the previous card
        elif line.startswith("---"):
            add_card_if_not_empty()
            latest_question = ""
            latest_answer = ""
            new_question = True

        # Case 3: The line before was "---" -> store the line as a question
        elif new_question:
            new_question = False
            # If the line starts with "ADDED: ", it is already added to the card so it should be skipped
            if line.startswith("ADDED: "):
                continue
            latest_question = line

        # Case 4: The line indicates by the prefix "EQL: " that this line should also be included in the question
        # -> add the line to the question variable
        elif line.startswith("EQL: ") and latest_question:
            latest_question += "<br>" + line[5:]

        # Else-Case: If the line is neither a tag nor a question, it will be added to the answer
        else:
            latest_answer += line + "\n"

    # Add the last card to the deck, since it's not covered by the for-loop
    add_card_if_not_empty()

    return card_list


def create_cards(card_list: list, image_processor: ImageProcessor) -> list:
    stored_notes = []
    for card in card_list:
        card: Note
        if "cloze" in card.get_initial_front().lower():
            if "image" in card.get_initial_front().lower():
                image_processor.process_image_occlusion(card.back, card.tags[0])
            else:
                cloze: Cloze = card.convert_to_cloze()
                image_processor.apply(cloze)
                stored_notes.append(cloze.get_basic_note_type())
        else:
            # Handle images
            image_processor.apply(card)

            # Create a new note with the question and answer
            if "#CODE#" in card.get_initial_front() or "#CODE#" in card.get_initial_back():
                card.tags.append("TODO_PROCESS_CODE")

            stored_notes.append(card.get_basic_note_type())

    return stored_notes


def create_package(note_list: list, image_processor: ImageProcessor, package_title: str, output: bool = True) -> None:
    """
    Create a new Anki package with the given cards and media files
    :param note_list: list of notes to be added to the package
    :param image_processor: ImageProcessor instance to handle images
    :param package_title: title of the package
    :param output: boolean to indicate if the output should be printed
    :return: None
    """
    # Create a new deck with given title
    deck = genanki.Deck(random.randrange(1 << 30, 1 << 31), package_title)

    for note in note_list:
        deck.add_note(note)

    package = genanki.Package(deck)
    package.media_files = image_processor.media_files

    with warnings.catch_warnings(record=True) as warning_list:
        package.write_to_file(f'{package_title}.apkg')

    # Output stats
    if output:
        print(f"PACKAGE SUMMARY")
        print(f"- Added {len(deck.notes)} notes to the deck")
        print(f"- Added {len(image_processor.media_files)} media files to the deck")
        if image_processor.tags_mapped_to_images.keys():
            print("\nIMAGE OCCLUSIONS:")

            for key in image_processor.tags_mapped_to_images.keys():
                print(f"{key}")
                for image in image_processor.tags_mapped_to_images[key]:
                    print(f"- {image}")
        else:
            print("- No image occlusions available")

        if warning_list:
            print("")
            print("WARNINGS:")
            for warning in warning_list:
                if issubclass(warning.category, UserWarning) and str(warning.message).startswith(FORMAT_WARNING_STRING):
                    print(f"- Formatting Warning:{str(warning.message).replace(FORMAT_WARNING_STRING, '')}")
                else:
                    print(f"- Warning: {warning.message}")
