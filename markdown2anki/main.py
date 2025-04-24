from notes import Note
from helpers.tag_handler import handle_tags, merge_tags
from NoteTypes.note_types import BasicNoteType, get_basic_model
from helpers.text_formatting import format_bullet_points, replace_symbols, convert_to_mathjax, html_new_line_processor, \
    standardize_html, remove_trailing_br_tags, remove_trailing_new_lines
import markdown

base_model = get_basic_model()


def file_to_preprocessed_cards(input_lines: list, file_name: str, base_tag: str):
    """
    Given a list of lines from a markdown file, parse the lines and add them to the Anki package that will be exported.
    :param input_lines: list of lines from the input file
    :param file_name: name of the input file (will be used as the last part of the tag - e.g. "Python::FileName")
    :param base_tag: base tag for the package (e.g. "Python")
    :return: None, since the function will call the add_card_to_deck function which adds the cards to the package
    """

    # List is required since tags change dynamically with the handle_tags function, also cut the .md file extension
    tags = [base_tag, file_name[:-3]]
    new_question = False  # Indicates that "---" is found, and it is likely that a new question will be following
    latest_question = ""
    latest_answer = ""
    card_list = []

    def add_card_if_not_empty():
        if latest_question:
            card_list.append(apply_processors(latest_question, latest_answer, merge_tags(tags)))

    for line in input_lines:
        # Case 1: Line starts with a tag (Heading in a markdown file) -> Update Tags and reset card
        if line.startswith("#"):
            add_card_if_not_empty()
            latest_question = ""
            latest_answer = ""
            tags = handle_tags(line, tags)

        # Case 2: Line starts with a "---" -> Reset card and process the previous card
        elif line.startswith("---"):
            add_card_if_not_empty()
            latest_question = ""
            latest_answer = ""
            new_question = True

        # Case 3: The line before was "---" -> store the line as a question
        elif new_question:
            latest_question = line
            new_question = False

        # Case 4: The line indicates by the prefix "EQL: " that this line should also be included in the question
        # -> add the line to the question variable
        elif line.startswith("EQL: "):
            latest_question += "<br>" + line[5:]

        # Else-Case: If the line is neither a tag nor a question, it will be added to the answer
        else:
            latest_answer += line + "\n"

    # Add the last card to the deck, since it's not covered by the for-loop
    add_card_if_not_empty()


def apply_processors(front: str, back: str, tag: str) -> Note:
    back = remove_trailing_new_lines(back)

    # Preprocessing for bullet points and enumerations (otherwise html converter will not work)
    unprocessed_front = format_bullet_points(front)
    unprocessed_back = format_bullet_points(back)

    # Replace symbols with unicode symbols
    unprocessed_front = replace_symbols(unprocessed_front)
    unprocessed_back = replace_symbols(unprocessed_back)

    # Convert markdown to html with markdown module
    processed_front = markdown.markdown(unprocessed_front)
    processed_back = markdown.markdown(unprocessed_back)

    # Convert mathjax to html
    processed_front = convert_to_mathjax(processed_front, unprocessed_front)
    processed_back = convert_to_mathjax(processed_back, unprocessed_back)

    # Process new lines
    processed_front = html_new_line_processor(processed_front)
    processed_back = html_new_line_processor(processed_back)

    # Remove trailing new lines
    processed_front = remove_trailing_new_lines(processed_front)
    processed_back = remove_trailing_new_lines(processed_back)

    # Format the html strings for Anki usage
    processed_front = standardize_html(processed_front)
    processed_back = standardize_html(processed_back)

    # Remove trailing <br> tags
    processed_front = remove_trailing_br_tags(processed_front)
    processed_back = remove_trailing_br_tags(processed_back)

    return Note(processed_front, processed_back, list(tag))


