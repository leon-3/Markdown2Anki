"""Markdown -> Anki HTML.

Code (fenced and inline) and math (``$...$`` / ``$$...$$``) are lifted out of the text before any other
processing, so symbol replacement and the markdown parser can never touch them, and put back afterwards.
This replaces the old index-aligned regex swap that broke as soon as markdown changed the number of ``$``.
"""
from __future__ import annotations

import html
import re
from typing import Dict, List, Tuple

import markdown

from .formatting import (
    format_bullet_points,
    html_new_line_processor,
    ignore_image_resizing_in_html,
    remove_trailing_br_tags,
    remove_trailing_new_lines,
    replace_symbols,
    standardize_bullet_indentation,
    standardize_html,
)

FENCED_CODE_RE = re.compile(r"^[ \t]*```([\w+-]*)[ \t]*\n(.*?)^[ \t]*```[ \t]*$", re.MULTILINE | re.DOTALL)
INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
DISPLAY_MATH_RE = re.compile(r"\$\$(.+?)\$\$", re.DOTALL)
# Pandoc-style inline math: no space right after the opening $ or before the closing one, and the closing
# $ must not be followed by a digit -> "$5 and $10" is prose, "$x$" is math. No newlines inside.
INLINE_MATH_RE = re.compile(r"(?<![\\$])\$(?=\S)((?:[^$\n\\]|\\.)+?)(?<=\S)\$(?![\d$])")

TOKEN_FMT = "M2ASTASH{}X"
TOKEN_RE = re.compile(r"M2ASTASH(\d+)X")


class _Stash:
    def __init__(self) -> None:
        self.items: List[Tuple[str, str, bool]] = []  # (kind, replacement html, is_block)

    def put(self, kind: str, replacement: str, block: bool) -> str:
        self.items.append((kind, replacement, block))
        return TOKEN_FMT.format(len(self.items) - 1)


def _math(text: str) -> str:
    """Math content as HTML text: escape ``<``/``&`` (MathJax reads the rendered DOM text, so ``&lt;`` is
    fine) and split ``}}`` which would collide with Anki's cloze syntax."""
    return html.escape(text, quote=False).replace("{{", "{ {").replace("}}", "} }")


def _stash_code_and_math(text: str, stash: _Stash) -> str:
    def fenced(match: "re.Match[str]") -> str:
        lang, code = match.group(1), match.group(2)
        cls = f' class="language-{lang}"' if lang else ""
        body = html.escape(code.rstrip("\n"))
        return stash.put("code", f"<pre><code{cls}>{body}</code></pre>", block=True)

    text = FENCED_CODE_RE.sub(fenced, text)
    text = INLINE_CODE_RE.sub(lambda m: stash.put("code", f"<code>{html.escape(m.group(1))}</code>", False), text)
    text = DISPLAY_MATH_RE.sub(lambda m: stash.put("math", "\\[" + _math(m.group(1).strip().strip("$")) + "\\]", True),
                               text)
    text = INLINE_MATH_RE.sub(lambda m: stash.put("math", "\\(" + _math(m.group(1)) + "\\)", False), text)
    return text


def _restore(html_text: str, stash: _Stash) -> str:
    for index, (_, replacement, block) in enumerate(stash.items):
        token = TOKEN_FMT.format(index)
        if block:
            # A block that stood on its own line was wrapped in <p> and given a <br>; neither belongs.
            html_text = html_text.replace(f"<p>{token}</p>", replacement)
            html_text = html_text.replace(token + "<br>", replacement)
        html_text = html_text.replace(token, replacement)
    return html_text


def render_markdown(text: str) -> str:
    """Render one card field (question or answer) from markdown to Anki-ready HTML."""
    stash = _Stash()
    text = _stash_code_and_math(text, stash)
    text = replace_symbols(text)
    text = remove_trailing_new_lines(text)
    text = standardize_bullet_indentation(text)
    text = format_bullet_points(text)
    html_text = markdown.markdown(text, extensions=["tables"])
    html_text = html_new_line_processor(html_text)
    html_text = remove_trailing_new_lines(html_text)
    html_text = standardize_html(html_text)
    html_text = remove_trailing_br_tags(html_text)
    html_text = _restore(html_text, stash)
    html_text = ignore_image_resizing_in_html(html_text)
    return html_text


def strip_keyword_lines(text: str, keywords: List[str]) -> str:
    """Remove lines that consist only of a keyword such as ``#CODE#`` (markdown, before rendering)."""
    kept = [line for line in text.split("\n") if line.strip() not in keywords]
    return "\n".join(kept)
