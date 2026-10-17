from markdown2anki.render import render_markdown


def test_fenced_code_keeps_arrows_and_language():
    html = render_markdown("```cpp\nauto x = ptr->value; // a => b\n```")
    assert html == '<pre><code class="language-cpp">auto x = ptr-&gt;value; // a =&gt; b</code></pre>'


def test_fenced_code_supports_languages_with_special_chars():
    html = render_markdown("```c#\nint x = 1;\n```")
    assert html == '<pre><code class="language-c#">int x = 1;</code></pre>'


def test_inline_code_is_untouched():
    html = render_markdown("Use `a -> b` here -> there")
    assert "<code>a -&gt; b</code>" in html
    assert "here → there" in html


def test_prices_are_not_math():
    assert render_markdown("Paid $5 for coffee and $10 for lunch") == "Paid $5 for coffee and $10 for lunch"


def test_inline_and_display_math():
    html = render_markdown("Let $a_{1} \\to b$ and\n$$\nx^2 + y^2\n$$\nend")
    assert "\\(a_{1} \\to b\\)" in html
    assert "\\[x^2 + y^2\\]" in html
    assert "<em>" not in html  # underscores inside math never become emphasis


def test_math_is_cloze_safe():
    assert render_markdown("$\\frac{a}{b_{1}}$") == "\\(\\frac{a}{b_{1} }\\)"


def test_bold_and_lists():
    html = render_markdown("**Key** point\n- one\n- two")
    assert "<b>Key</b>" in html
    assert "<li>one</li>" in html and "<li>two</li>" in html


def test_arrows_in_prose():
    assert render_markdown("a -> b => c") == "a → b ⇒ c"


def test_math_escapes_html_characters():
    assert render_markdown("$a < b$") == "\\(a &lt; b\\)"


def test_math_glued_to_a_word_and_stray_dollar():
    assert render_markdown("Sind$\\sum a_k$ und") == "Sind\\(\\sum a_k\\) und"
    assert render_markdown("$$$x$$") == "\\[x\\]"


def test_bare_url_autolinking():
    html = render_markdown("Visit https://example.com and http://test.org/path?a=1&b=2 for info.")
    assert '<a href="https://example.com">https://example.com</a>' in html
    assert '<a href="http://test.org/path?a=1&amp;b=2">http://test.org/path?a=1&amp;b=2</a>' in html


def test_bare_url_punctuation_handling():
    html = render_markdown("See (https://example.com/foo), or https://example.com/bar! Also https://en.wikipedia.org/wiki/Function_(mathematics).")
    assert '(<a href="https://example.com/foo">https://example.com/foo</a>),' in html
    assert '<a href="https://example.com/bar">https://example.com/bar</a>!' in html
    assert '<a href="https://en.wikipedia.org/wiki/Function_(mathematics)">https://en.wikipedia.org/wiki/Function_(mathematics)</a>.' in html


def test_markdown_link_preserved_and_not_double_linked():
    html = render_markdown("Check [Google](https://google.com) and https://bare.com")
    assert '<a href="https://google.com">Google</a>' in html
    assert '<a href="https://bare.com">https://bare.com</a>' in html


def test_urls_in_code_and_math_not_autolinked():
    html = render_markdown("`https://code.example.com` and\n```python\n# https://fenced.example.com\n```\nand $https://math.example.com$")
    assert "<code>https://code.example.com</code>" in html
    assert "# https://fenced.example.com" in html
    assert "\\(https://math.example.com\\)" in html
    assert '<a href="https://code.example.com">' not in html
    assert '<a href="https://fenced.example.com">' not in html
    assert '<a href="https://math.example.com">' not in html


def test_wikilinks_untouched():
    html = render_markdown("See [[Some Note]] and [[Other Note|Alias]]")
    assert "[[Some Note]]" in html
    assert "[[Other Note|Alias]]" in html


def test_math_three_consecutive_braces():
    html = render_markdown("$\\frac{1}{\\sqrt{a_{i}}}$")
    assert "}}" not in html
    assert "\\(\\frac{1}{\\sqrt{a_{i} } }\\)" == html


def test_cloze_inside_math_preserved():
    html = render_markdown("Formula: $x = {{c1::5}}$ and $\\frac{1}{ {{c2::y}} }$")
    assert "{{c1::5}}" in html
    assert "{{c2::y}}" in html


def test_math_nested_stash_with_backticks():
    # Backticks inside math must not leak M2ASTASH tokens into HTML
    html = render_markdown("$$\n\\text{`quote'}\n$$")
    assert "M2ASTASH" not in html
    assert "\\[\\text{`quote'}\\]" in html


def test_fenced_code_tildes_and_four_backticks():
    html_tilde = render_markdown("~~~python\nprint(1)\n~~~")
    assert '<pre><code class="language-python">print(1)</code></pre>' == html_tilde

    nested_md = "````markdown\n```python\nx = 1\n```\n````"
    html_nested = render_markdown(nested_md)
    assert '<pre><code class="language-markdown">```python\nx = 1\n```</code></pre>' == html_nested


def test_bare_url_adjacent_to_inline_code():
    html = render_markdown("https://example.com/`code`")
    assert '<a href="https://example.com/">https://example.com/</a>' in html
    assert "<code>code</code>" in html
    assert "M2ASTASH" not in html
