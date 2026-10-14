from markdown2anki.formatting import (format_bullet_points, html_new_line_processor, ignore_image_resizing_in_html,
                                      remove_trailing_br_tags, remove_trailing_new_lines, replace_symbols,
                                      standardize_bullet_indentation, standardize_html)


def test_replace_symbols():
    assert replace_symbols("a -> b => c • d") == "a → b ⇒ c - d"


def test_bullet_indentation_uses_tabs_per_four_spaces():
    assert standardize_bullet_indentation("- a\n    - b\n\t- c\n  - d\ntext") == "- a\n\t- b\n\t- c\n- d\ntext"


def test_format_bullet_points_separates_lists_from_text():
    assert format_bullet_points("intro\n- a\n- b\nend") == "intro\n\n- a\n- b\n\nend"
    assert format_bullet_points("intro\n1. a\n2. b\nend") == "intro\n\n1. a\n2. b\n\nend"


def test_html_line_breaks_skip_block_tags():
    assert html_new_line_processor("a\n<ul>\n<li>x</li>\n</ul>\nb") == "a<br>\n<ul>\n<li>x</li>\n</ul>\nb<br>\n"


def test_trailing_clean_up():
    assert remove_trailing_new_lines("a\n\n") == "a"
    assert remove_trailing_br_tags("a<br><br>\n") == "a"


def test_standardize_html():
    assert standardize_html("<p><strong>x</strong></p>") == "<b>x</b>"
    assert standardize_html("<p>a</p>\n<p>b</p>") == "<p>a</p>\n<p>b</p>"


def test_image_resizing_is_dropped():
    assert ignore_image_resizing_in_html("![[a.png|300]]") == "![[a.png]]"
