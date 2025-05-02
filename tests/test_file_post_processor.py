import unittest
import os
from markdown2anki import add_added_flags_to_each_valid_card

with open("sample_1.md", "r", encoding="utf-8") as f:
    SAMPLE_FILE_1 = f.read()

with open("expected_1.md", "r", encoding="utf-8") as f:
    EXPECTED_FILE_1 = f.read()

with open("sample_2.md", "r", encoding="utf-8") as f:
    SAMPLE_FILE_2 = f.read()

with open("expected_2.md", "r", encoding="utf-8") as f:
    EXPECTED_FILE_2 = f.read()

SAMPLES = [SAMPLE_FILE_1, SAMPLE_FILE_2]
EXPECTED_FILES = [EXPECTED_FILE_1, EXPECTED_FILE_2]


class TestFilePostProcessor(unittest.TestCase):

    def test_add_added_flags_to_each_valid_card(self):
        for sample, expected in zip(SAMPLES, EXPECTED_FILES):
            modified_content = test_add_added_flags_to_each_valid_card(sample)
            self.assertEqual(modified_content, expected)


def test_add_added_flags_to_each_valid_card(sample):
    # Create a temporary file with the sample content
    with open("test_file.md", "w", encoding="utf-8") as f:
        f.write(sample)

    # Get the absolute path to the file including home directory
    file_name = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_file.md")

    # Call the function to be tested
    add_added_flags_to_each_valid_card(file_name)

    # Read the modified file content
    with open(file_name, "r", encoding="utf-8") as f:
        modified_content = f.read()

    # Clean up the temporary file
    os.remove(file_name)

    return modified_content
