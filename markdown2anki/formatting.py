"""Line-level markdown and HTML clean-up steps used by :mod:`markdown2anki.render`."""
from __future__ import annotations

import re

SYMBOLS = {"->": "→", "=>": "⇒", "• ": "- "}
HTML_BLOCK_TAGS = ("<ul>", "</ul>", "<li>", "</li>", "<ol>", "</ol>", "</p>")
NUMBERED_RE = re.compile(r"^\d+\.")


def replace_symbols(text: str) -> str:
    for source, target in SYMBOLS.items():
        text = text.replace(source, target)
    return text


def standardize_bullet_indentation(text: str) -> str:
    """Normalise the indentation of bullet lines to one tab per four leading spaces."""
    out = []
    for line in text.split("\n"):
        if not line.lstrip().startswith("-"):
            out.append(line)
            continue
        line = line.replace("\t", "    ")
        depth = (len(line) - len(line.lstrip())) // 4
        out.append("\t" * depth + line.lstrip())
    return "\n".join(out)


def format_bullet_points(text: str) -> str:
    """Insert the blank lines the markdown parser needs around bullet and numbered lists."""
    lines = text.split("\n")
    out = []
    for current, following in zip(lines, lines[1:]):
        out.append(current)
        if following.startswith("- ") and not current.startswith("- "):
            out.append("")
        if following.startswith("1. "):
            out.append("")
        if current.lstrip().startswith("- ") and not following.lstrip().startswith("- "):
            out.append("")
        if NUMBERED_RE.match(current.lstrip()) and not NUMBERED_RE.match(following.lstrip()):
            out.append("")
    out.append(lines[-1])
    return "\n".join(out)


def html_new_line_processor(text: str) -> str:
    """Turn newlines into ``<br>`` except on lines that already carry block-level tags."""
    out = []
    for line in text.split("\n"):
        out.append(line if any(tag in line for tag in HTML_BLOCK_TAGS) else line + "<br>")
    return "\n".join(out) + "\n"


def remove_trailing_new_lines(text: str) -> str:
    return text.rstrip("\n")


def standardize_html(text: str) -> str:
    """Drop the paragraph wrapper around single-line fields and prefer ``<b>`` over ``<strong>``."""
    if "\n" not in text:
        text = text.replace("<p>", "").replace("</p>", "")
    return text.replace("<strong>", "<b>").replace("</strong>", "</b>")


def remove_trailing_br_tags(text: str) -> str:
    text = remove_trailing_new_lines(text)
    while text.endswith("<br>"):
        text = text[:-4]
    return text


def ignore_image_resizing_in_html(text: str) -> str:
    """Strip Obsidian's ``|300`` size suffix from image links."""
    return re.sub(r"\|[0-9]+]]", "]]", text)
