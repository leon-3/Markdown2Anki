from ..notes import Cloze, Note

class Processor:

    def __init__(self, processor):
        """
        Initialize the processor with a function that will be used to process the text.
        :param processor: A function that takes a string and returns a string, the apply method will use this message
        to apply the processor to a given note
        """
        self.processor = processor

    def apply(self, note: Note) -> None:
        if isinstance(note, Cloze):
            note.update_cloze_text(self.processor(note.cloze_text))
        else:
            note.front = self.processor(note.front)
            note.back = self.processor(note.back)