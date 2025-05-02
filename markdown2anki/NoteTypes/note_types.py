import genanki
import os

class BasicNoteType(genanki.Note):
    @property
    def guid(self):
        return genanki.guid_for(self.fields[0], self.fields[1])


def get_basic_model() -> genanki.Model:
    base_dir = os.path.dirname(os.path.abspath(__file__))

    with open(os.path.join(base_dir, 'Basic', 'styling.css')) as file:
        base_styling = file.read()
    with open(os.path.join(base_dir, 'Basic', 'front.html'), encoding='utf-8') as file:
        base_front = file.read()
    with open(os.path.join(base_dir, 'Basic', 'back.html'), encoding='utf-8') as file:
        base_back = file.read()

    base_type = genanki.Model(
        1633854805146, f'Basic',
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
