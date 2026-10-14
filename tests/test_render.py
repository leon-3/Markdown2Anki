from markdown2anki.render import render_markdown


def test_fenced_code_keeps_arrows_and_language():
    html = render_markdown("```cpp\nauto x = ptr->value; // a => b\n```")
    assert html == '<pre><code class="language-cpp">auto x = ptr-&gt;value; // a =&gt; b</code></pre>'


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
