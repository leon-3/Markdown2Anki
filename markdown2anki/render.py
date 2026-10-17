"""Markdown -> Anki HTML.

Code (fenced and inline) and math (``$...$`` / ``$$...$$``) are lifted out of the text before any other
processing, so symbol replacement and the markdown parser can never touch them, and put back afterwards.
This replaces the old index-aligned regex swap that broke as soon as markdown changed the number of ``$``.
"""
from __future__ import annotations

import html
import re

import markdown

from .formatting import (
    format_bullet_points,
    html_new_line_processor,
    remove_trailing_br_tags,
    remove_trailing_new_lines,
    replace_symbols,
    standardize_bullet_indentation,
    standardize_html,
)

FENCED_CODE_RE = re.compile(
    r"^[ \t]*(`{3,}|~{3,})([^\n]*)\n(.*?)^[ \t]*\1[ \t]*$",
    re.MULTILINE | re.DOTALL,
)
INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
DISPLAY_MATH_RE = re.compile(r"\$\$(.+?)\$\$", re.DOTALL)
# Pandoc-style inline math: no space right after the opening $ or before the closing one, and the closing
# $ must not be followed by a digit -> "$5 and $10" is prose, "$x$" is math. No newlines inside.
INLINE_MATH_RE = re.compile(r"(?<![\\$])\$(?=\S)((?:[^$\n\\]|\\.)+?)(?<=\S)\$(?![\d$])")

URL_RE = re.compile(r"https?://[^\s<>\"\'`\ue000\ue001]+", re.IGNORECASE)

TOKEN_FMT = "\ue000M2ASTASH{}X\ue001"
TOKEN_RE = re.compile(r"\ue000M2ASTASH(\d+)X\ue001")

_CLOZE_IN_MATH_RE = re.compile(r"\{\{(c\d+::)")


class _Stash:
    def __init__(self) -> None:
        self.items: list[tuple[str, str, bool]] = []  # (kind, replacement html, is_block)

    def put(self, kind: str, replacement: str, block: bool) -> str:
        self.items.append((kind, replacement, block))
        return TOKEN_FMT.format(len(self.items) - 1)


def _protect_clozes_in_math(text: str) -> str:
    """Protect Anki cloze syntax inside math from brace splitting."""
    result = []
    i = 0
    n = len(text)
    while i < n:
        m = _CLOZE_IN_MATH_RE.search(text, i)
        if not m:
            result.append(text[i:])
            break
        result.append(text[i:m.start()])
        cloze_num = m.group(1)
        result.append(f"\x01{cloze_num}")
        j = m.end()
        brace_depth = 0
        found_close = False
        while j < n:
            if text[j:j+2] == "}}" and brace_depth == 0:
                result.append(text[m.end():j])
                result.append("\x04")
                j += 2
                found_close = True
                break
            elif text[j] == "{":
                brace_depth += 1
                j += 1
            elif text[j] == "}":
                if brace_depth > 0:
                    brace_depth -= 1
                j += 1
            else:
                j += 1
        if found_close:
            i = j
        else:
            result.append(text[m.end():])
            break
    return "".join(result)


def _math(text: str) -> str:
    """Math content as HTML text: escape ``<``/``&`` (MathJax reads the rendered DOM text, so ``&lt;`` is
    fine) and split consecutive braces which would collide with Anki's cloze syntax, while protecting
    any real cloze deletions inside the math."""
    protected = _protect_clozes_in_math(text)
    escaped = html.escape(protected, quote=False)
    escaped = re.sub(r"\{(?=\{)", "{ ", escaped)
    escaped = re.sub(r"\}(?=\})", "} ", escaped)
    return escaped.replace("\x01", "{{").replace("\x04", "}}")


def _stash_code_and_math(text: str, stash: _Stash) -> str:
    def fenced(match: re.Match[str]) -> str:
        lang_str = match.group(2).strip()
        code = match.group(3)
        lang = lang_str.split()[0] if lang_str else ""
        cls = f' class="language-{lang}"' if lang else ""
        body = html.escape(code.rstrip("\n"))
        return stash.put("code", f"<pre><code{cls}>{body}</code></pre>", block=True)

    text = FENCED_CODE_RE.sub(fenced, text)
    text = DISPLAY_MATH_RE.sub(
        lambda m: stash.put("math", "\\[" + _math(m.group(1).strip().strip("$")) + "\\]", True),
        text,
    )
    text = INLINE_MATH_RE.sub(
        lambda m: stash.put("math", "\\(" + _math(m.group(1)) + "\\)", False),
        text,
    )
    text = INLINE_CODE_RE.sub(
        lambda m: stash.put("code", f"<code>{html.escape(m.group(1))}</code>", False),
        text,
    )
    return text


def autolink_bare_urls(html_text: str) -> str:
    """Turn bare http(s) URLs into <a href="..."> links outside of existing <a> tags and HTML markup."""
    def repl_text(chunk: str) -> str:
        def repl(m: re.Match[str]) -> str:
            url = m.group(0)
            trailing = ""
            while url and url[-1] in ".,;:!?)":
                if url[-1] == ")" and url.count("(") >= url.count(")"):
                    break
                trailing = url[-1] + trailing
                url = url[:-1]
            return f'<a href="{url}">{url}</a>{trailing}'
        return URL_RE.sub(repl, chunk)

    parts = re.split(r"(<[^>]+>)", html_text)
    in_a = False
    for i, part in enumerate(parts):
        if not part:
            continue
        if part.startswith("<"):
            lower = part.lower()
            if lower.startswith("<a ") or lower == "<a>":
                in_a = True
            elif lower.startswith("</a"):
                in_a = False
        else:
            if not in_a:
                parts[i] = repl_text(part)
    return "".join(parts)


def _restore(html_text: str, stash: _Stash) -> str:
    for index in range(len(stash.items) - 1, -1, -1):
        _, replacement, block = stash.items[index]
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
    html_text = autolink_bare_urls(html_text)
    html_text = _restore(html_text, stash)
    return html_text


def strip_keyword_lines(text: str, keywords: list[str]) -> str:
    """Remove lines that consist only of a keyword such as ``#CODE#`` (markdown, before rendering)."""
    kept = [line for line in text.split("\n") if line.strip() not in keywords]
    return "\n".join(kept)
