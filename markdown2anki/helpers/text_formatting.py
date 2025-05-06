import re
import markdown

from .processors import Processor, BinaryProcessor


def format_bullet_points(text: str) -> str:
    """
    Format the bullet points and enumerations in the Markdown text to ensure good html processing
    :param text: given Markdown text
    :return: processed text
    """

    # Add a new line between two lines if the first does not start with a bullet point and the second does
    lines = text.split("\n")
    new_text = ""

    # Check for two lines, if the first does not start with a bullet point and the second does add a new line in between
    for i in range(len(lines) - 1):
        new_text += lines[i] + "\n"
        # Insert new line before bullet points
        if lines[i + 1].startswith("- ") and not lines[i].startswith("- "):
            new_text += "\n"
        # Insert new line before numbered points
        if lines[i + 1].startswith("1. "):
            new_text += "\n"

        # Insert new line after bullet points
        if lines[i].lstrip().startswith("- ") and not lines[i + 1].lstrip().startswith("- "):
            new_text += "\n"

        # Insert new line after numbered points
        # Check if current line starts with digits and a dot and next line does not
        if re.match(r"^\d+\.", lines[i].lstrip()) and not re.match(r"^\d+\.", lines[i + 1].lstrip()):
            new_text += "\n"

    new_text += lines[-1]  # Add the last line without a new line
    return new_text


def replace_symbols(text: str) -> str:
    """
    Replace the symbols in the text with unicode symbols
    :param text: Given text
    :return: Text with replacements
    """

    # Dictionary with mappings from text to unicode symbols
    mappings = {
        "->": "→",
        "=>": "⇒"
    }

    for replace_key in mappings.keys():
        text = text.replace(replace_key, mappings[replace_key])

    return text


def convert_to_mathjax(text_html: str, text_org: str) -> str:
    """
    Convert the mathjax in the text to Anki-tags (\(\) or \[\])
    :param text_html: the processed html text
    :param text_org: the original unprocessed text
    :return: text with appropriate mathjax tags
    """

    # Match LaTeX math expressions enclosed in single ($...$) or double ($$...$$) dollar signs
    mathjax_pattern = r"\$\$.*?\$\$|\$.*?\$"

    original_mathjax = re.findall(mathjax_pattern, text_org, re.MULTILINE | re.DOTALL)
    for i, match in enumerate(re.findall(mathjax_pattern, text_html, re.MULTILINE | re.DOTALL)):
        start_tag = r"\("
        end_tag = r"\)"

        if match.startswith("$$"):
            start_tag = r"\["
            end_tag = r"\]"

        chars_to_remove = 2 if match.startswith("$$") else 1

        text_html = text_html.replace(match,
                                      start_tag + original_mathjax[i][chars_to_remove:-chars_to_remove] + end_tag)

    return text_html


def html_new_line_processor(text: str) -> str:
    """
    Replace all new lines with <br> tags if they are not already in a html tag
    :param text:
    :return:
    """

    new_html = ""
    html_tag_list = ["<ul>", "</ul>", "<li>", "</li>", "<ol>", "</ol>", "</p>"]

    for line in text.split("\n"):
        for html_tag in html_tag_list:
            if html_tag in line:
                new_html += line + "\n"
                break
        else:
            new_html += line + "<br>\n"

    return new_html


def remove_trailing_new_lines(text: str) -> str:
    """
    Remove all trailing newlines from the answer
    :param text: given text
    :return: text with removed newlines
    """

    while text.endswith("\n"):
        text = text[:-1]
    return text


def standardize_html(text: str) -> str:
    """
    Ensure standardized formatting of the html string (remove single paragraph tags and replace strong with b)
    :param text: html string
    :return: formatted html
    """
    if "\n" not in text:
        text = text.replace("<p>", "").replace("</p>", "")

    text = text.replace("<strong>", "<b>").replace("</strong>", "</b>")
    return text


def remove_trailing_br_tags(text: str) -> str:
    """
    Remove all trailing <br> tags from the text
    :param text:
    :return:
    """

    text = remove_trailing_new_lines(text)

    while text.endswith("<br>"):
        text = text[:-4]

    return text


def ignore_image_resizing_in_html(text: str) -> str:
    """
    Ignore the image resizing in the markdown text
    :param text: markdown text
    :return: processed text
    """

    # Find all occurences of a string that starts with |, followed by some digits and then ]] and replace it with ]]
    text = re.sub(r"\|[0-9]+]]", "]]", text)

    return text


def cloze_safe_math_jax(text: str) -> str:
    mathjax_pattern = r"(\$\$.*?\$\$|\$.*?\$)"
    def replace_brackets(match):
        return match.group(0).replace("{{", "{ {").replace("}}", "} }")
    return re.sub(mathjax_pattern, replace_brackets, text)


def get_preprocessors() -> list:
    return [Processor(cloze_safe_math_jax), Processor(remove_trailing_new_lines), Processor(format_bullet_points),
            Processor(replace_symbols), Processor(markdown.markdown), BinaryProcessor(convert_to_mathjax),
            Processor(html_new_line_processor), Processor(remove_trailing_new_lines), Processor(standardize_html),
            Processor(remove_trailing_br_tags), Processor(ignore_image_resizing_in_html)]
