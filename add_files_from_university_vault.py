import os
from dotenv import load_dotenv
import json

from markdown2anki import file_to_preprocessed_cards, create_cards, create_package, ImageProcessor, \
    add_added_flags_to_each_valid_card

load_dotenv()

if __name__ == "__main__":
    # CONFIG VARIABLES

    BASE_TAG = os.getenv("BASE_TAG", "University")
    OBSIDIAN_VAULT_DIRECTORY = os.getenv("OBSIDIAN_VAULT_DIRECTORY", r"D:\2. Coding\[Markdown] TUM Anki\TUM-Anki")
    PACKAGE_NAME = os.getenv("PACKAGE_NAME", "TUM-Anki")
    SUBJECT_TAG_DICTIONARY = json.loads(os.getenv("SUBJECT_TAG_DICTIONARY", "{}"))
    SUB_DIRECTORY_TAG_DICTIONARY = json.loads(os.getenv("SUB_DIRECTORY_TAG_DICTIONARY", "{}"))
    IGNORE_DIRECTORIES = json.loads(os.getenv("IGNORE_DIRECTORIES", "[]"))

    # get all directories directly located on the first level of the obsidian vault
    image_processor = ImageProcessor(False)
    note_list = []
    directories = [d for d in os.listdir(OBSIDIAN_VAULT_DIRECTORY) if
                   os.path.isdir(os.path.join(OBSIDIAN_VAULT_DIRECTORY, d))]
    subject_base_tag = BASE_TAG
    skip_information = []
    processed_files = []

    # CHECK FOR VALID SUBJECTS
    for directory in directories:
        if directory in IGNORE_DIRECTORIES:
            continue
        elif directory not in SUBJECT_TAG_DICTIONARY:
            skip_information.append(f"Skipped directory '{directory}' (not a subject).")
            continue
        else:
            subject_base_tag = BASE_TAG + "::" + SUBJECT_TAG_DICTIONARY[directory]

        subject_directory_path = os.path.join(OBSIDIAN_VAULT_DIRECTORY, directory)
        sub_directories = [d for d in os.listdir(subject_directory_path) if
                           os.path.isdir(os.path.join(subject_directory_path, d))]
        used_base_tag = subject_base_tag

        # HANDLE SUB DIRECTORIES (e. g. "Lecture", "Exercises", "Tutorials")
        for sub_dir in sub_directories:
            if sub_dir not in SUB_DIRECTORY_TAG_DICTIONARY:
                skip_information.append(
                    f"Skipped sub-directory '{sub_dir}' (not a sub directory). Course name: {directory}")
                skip_information.append("PLEASE UPDATE THE CODE TO INCLUDE THIS SUBDIRECTORY")
                continue
            else:
                used_base_tag = subject_base_tag + "::" + SUB_DIRECTORY_TAG_DICTIONARY[sub_dir]

            sub_directory_path = os.path.join(subject_directory_path, sub_dir)
            image_processor.set_input_directory(sub_directory_path + "/")

            # HANDLE FILES
            for file in os.listdir(sub_directory_path):
                if file.endswith(".md"):
                    processed_files.append(os.path.join(sub_directory_path, file))
                    with open(os.path.join(sub_directory_path, file), encoding="utf-8") as f:
                        basic_cards = file_to_preprocessed_cards(f.read().split("\n"), file, used_base_tag)
                        note_list += create_cards(basic_cards, image_processor)

    # CREATE ANKI PACKAGE
    if skip_information:
        print("DIRECTORY INFORMATION")
        for info in skip_information:
            print(info)
        print("")

    create_package(note_list, image_processor, PACKAGE_NAME)

    for file in processed_files:
        add_added_flags_to_each_valid_card(file)
