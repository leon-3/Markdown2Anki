import unittest
from markdown2anki.notes import Note, Cloze

class TestNote(unittest.TestCase):
    def setUp(self):
        self.note = Note("Front", "Back", ["tag1", "tag2"])

    def test_initial_front(self):
        self.assertEqual(self.note.get_initial_front(), "Front")

    def test_initial_back(self):
        self.assertEqual(self.note.get_initial_back(), "Back")

    def test_basic_note_type(self):
        basic_note_type = self.note.get_basic_note_type()
        self.assertEqual(basic_note_type.fields, ["Front", "Back"])
        self.assertEqual(basic_note_type.tags, ["tag1", "tag2"])

    def test_convert_to_cloze(self):
        cloze_note = self.note.convert_to_cloze()
        self.assertIsInstance(cloze_note, Cloze)
        self.assertEqual(cloze_note.cloze_text, "Back")
        cloze_note.update_cloze_text("Back2")
        self.assertEqual(cloze_note.cloze_text, "Back2")
        self.assertEqual(cloze_note.tags, ["tag1", "tag2", "TODO_PROCESS_CLOZES"])


class TestCloze(unittest.TestCase):
    def setUp(self):
        self.note_1 = Note("Front", "Back #CODE#", ["tag1", "tag2"])
        self.cloze_note_1 = self.note_1.convert_to_cloze()

        self.note_2 = Note("Front", "Back", ["tag1", "tag2"])
        self.cloze_note_2 = self.note_2.convert_to_cloze()

    def test_code_tags(self):
        self.assertEqual(self.cloze_note_1.tags, ["tag1", "tag2", "TODO_PROCESS_CLOZES", "TODO_PROCESS_CODE"])

        self.assertEqual(self.cloze_note_2.tags, ["tag1", "tag2", "TODO_PROCESS_CLOZES"])

    def test_basic_note_type(self):
        basic_note_type = self.note_1.get_basic_note_type()
        self.assertEqual(basic_note_type.fields, ["Front", "Back #CODE#"])
        self.assertEqual(basic_note_type.tags, ["tag1", "tag2", "TODO_PROCESS_CLOZES", "TODO_PROCESS_CODE"])