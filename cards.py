from helpers.text_formatting import format_bullet_points, replace_symbols, convert_to_mathjax, html_new_line_processor, \
    standardize_html, remove_trailing_br_tags, remove_trailing_new_lines
import markdown

class BasicCard:

    def __init__(self, front: str, back: str, tag: str):
        self.tag = tag
        back = remove_trailing_new_lines(back)

        # Preprocessing for bullet points and enumerations (otherwise html converter will not work)
        self.unprocessed_front = format_bullet_points(front)
        self.unprocessed_back = format_bullet_points(back)

        # Replace symbols with unicode symbols
        self.unprocessed_front = replace_symbols(self.unprocessed_front)
        self.unprocessed_back = replace_symbols(self.unprocessed_back)

        # Convert markdown to html with markdown module
        self.processed_front = markdown.markdown(self.unprocessed_front)
        self.processed_back = markdown.markdown(self.unprocessed_back)

        # Convert mathjax to html
        self.processed_front = convert_to_mathjax(self.processed_front, self.unprocessed_front)
        self.processed_back = convert_to_mathjax(self.processed_back, self.unprocessed_back)

        # Process new lines
        self.processed_front = html_new_line_processor(self.processed_front)
        self.processed_back = html_new_line_processor(self.processed_back)

        # Remove trailing new lines
        self.processed_front = remove_trailing_new_lines(self.processed_front)
        self.processed_back = remove_trailing_new_lines(self.processed_back)

        # Format the html strings for Anki usage
        self.processed_front = standardize_html(self.processed_front)
        self.processed_back = standardize_html(self.processed_back)

        # Remove trailing <br> tags
        self.processed_front = remove_trailing_br_tags(self.processed_front)
        self.processed_back = remove_trailing_br_tags(self.processed_back)