from ..notes import Cloze

class Processor:

    def __init__(self, processor):
        self.processor = processor

    def apply(self, note) -> None:
        if isinstance(note, Cloze):
            note.update_cloze_text(self.processor(note.cloze_text))
        else:
            note.front = self.processor(note.front)
            note.back = self.processor(note.back)