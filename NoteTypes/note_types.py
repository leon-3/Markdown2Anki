import genanki


class BasicNote(genanki.Note):
    @property
    def guid(self):
        return genanki.guid_for(self.fields[0], self.fields[1])


def get_basic_model() -> genanki.Model:
    with open(f'NoteTypes/Basic/styling.css') as file:
        base_styling = file.read()
    with open(f'NoteTypes/Basic/front.html', encoding='utf-8') as file:
        base_front = file.read()
    with open(f'NoteTypes/Basic/back.html', encoding='utf-8') as file:
        base_back = file.read()

    base_type = genanki.Model(
        1937157822, f'Basic (genanki)',
        fields=[
            {
                'name': 'Front',
                'font': 'Arial',
            },
            {
                'name': 'Back',
                'font': 'Arial',
            },
        ],
        templates=[
            {
                'name': f'Base-Card-Genanki',
                'qfmt': base_front,
                'afmt': base_back,
            },
        ],
        css=base_styling,
    )

    return base_type
