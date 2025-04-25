from ..notes import Cloze, Note


def apply_processors(note: Note, processors: list) -> None:
    """
    Apply a list of processors to a note. The processors are applied in the order they are given.
    :param note: The note to be processed
    :param processors: A list of processors to be applied to the note
    """
    for processor in processors:
        processor.apply(note)


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


class BinaryProcessor(Processor):

    def __init__(self, processor):
        super().__init__(processor)

    def apply(self, note: Note) -> None:
        if isinstance(note, Cloze):
            note.update_cloze_text(self.processor(note.cloze_text, note.get_initial_back()))
        else:
            note.front = self.processor(note.front, note.get_initial_front())
            note.back = self.processor(note.back, note.get_initial_back())
