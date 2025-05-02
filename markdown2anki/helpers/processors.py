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
        """
        Apply the processor to a given note.
        This method processes the content of a `Note` object by applying the processor function
        to its text fields. The behavior differs depending on whether the note is a `Cloze` type
        or a regular `Note`.

        :param note: The note to be processed. It can be a `Cloze` or a regular `Note`.
        """
        if isinstance(note, Cloze):
            note.update_cloze_text(self.processor(note.cloze_text))
        else:
            note.front = self.processor(note.front)
            note.back = self.processor(note.back)


class BinaryProcessor(Processor):
    """Difference to processor is that the apply method also passes the initial text to the processor function."""

    def __init__(self, processor):
        super().__init__(processor)

    def apply(self, note: Note) -> None:
        """
        Apply the processor to a given note.
        This method processes the content of a `Note` object by applying the processor function
        to its text fields. The behavior differs depending on whether the note is a `Cloze` type
        or a regular `Note`.

        :param note: The note to be processed. It can be a `Cloze` or a regular `Note`.
        """
        if isinstance(note, Cloze):
            note.update_cloze_text(self.processor(note.cloze_text, note.get_initial_back()))
        else:
            note.front = self.processor(note.front, note.get_initial_front())
            note.back = self.processor(note.back, note.get_initial_back())
