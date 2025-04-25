from .NoteTypes.note_types import BasicNoteType, get_basic_model

base_model = get_basic_model()


class Note:

    def __init__(self, front: str, back: str, tags: list, initial_front: str = None,
                 initial_back: str = None) -> None:
        self.__initial_front = front if initial_front is None else initial_front
        self.__initial_back = back if initial_back is None else initial_back

        self.front = front
        self.back = back
        self.tags = tags

    def get_initial_front(self) -> str:
        return self.__initial_front

    def get_initial_back(self) -> str:
        return self.__initial_back

    def get_basic_note_type(self) -> BasicNoteType:
        return BasicNoteType(model=base_model, fields=[self.front, self.back], tags=self.tags)

    def convert_to_cloze(self):
        return Cloze(self.back, self.tags, self.__initial_front, self.__initial_back)


class Cloze(Note):

    def __init__(self, cloze_text: str, tags: list, initial_front: str = None,
                 initial_back: str = None):
        super().__init__("CLOZE", cloze_text, tags, initial_front, initial_back)
        self.cloze_text = cloze_text

        self.tags.append("TODO_PROCESS_CLOZES")

        if "#CODE#" in cloze_text:
            self.tags.append("TODO_PROCESS_CODE")

    def update_cloze_text(self, cloze_text: str):
        self.cloze_text = cloze_text
        self.back = cloze_text

    def get_basic_note_type(self):
        return BasicNoteType(model=base_model, fields=[self.cloze_text, ""], tags=self.tags)
