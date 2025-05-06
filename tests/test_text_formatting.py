from markdown2anki.helpers.text_formatting import (format_bullet_points, replace_symbols, convert_to_mathjax,
                                                   html_new_line_processor, remove_trailing_new_lines, standardize_html,
                                                   remove_trailing_br_tags, ignore_image_resizing_in_html,
                                                   cloze_safe_math_jax)
from unittest import TestCase


class TestTextFormatting(TestCase):
    def test_cloze_safe_math_jax(self):
        # Test with a simple math expression
        text = r"$$F_{M} = \{ S \subseteq Q ~|~ S \cap F \neq \emptyset\}$$"
        expected = r"$$F_{M} = \{ S \subseteq Q ~|~ S \cap F \neq \emptyset\}$$"
        self.assertEqual(cloze_safe_math_jax(text), expected)

        text = r"$\overline{z_{1} + z_{2}} = \overline{z_{1}} + \overline{z_{2}}$"
        expected = r"$\overline{z_{1} + z_{2} } = \overline{z_{1} } + \overline{z_{2} }$"
        self.assertEqual(cloze_safe_math_jax(text), expected)

        text = r"$$G/e = \left(V - \{w\}, \left(E \cap {{V - \{w\}} \choose 2} \right) \cup \{\{u, x\} ~|~ \{w, x\} \in E\} \right)$$"
        expected = r"$$G/e = \left(V - \{w\}, \left(E \cap { {V - \{w\} } \choose 2} \right) \cup \{\{u, x\} ~|~ \{w, x\} \in E\} \right)$$"
        self.assertEqual(cloze_safe_math_jax(text), expected)

        text = r"$\chi(G) \coloneqq \{|c(V)| ~|~ c \colon V \to \mathbb{N} \quad \text{Knotenfärbung von } G\}$"
        expected = r"$\chi(G) \coloneqq \{|c(V)| ~|~ c \colon V \to \mathbb{N} \quad \text{Knotenfärbung von } G\}$"
        self.assertEqual(cloze_safe_math_jax(text), expected)

        text = r"$$\frac{n!}{(1!)^{\lambda_{1}} \dots (n!)^{\lambda_{n}} \cdot \lambda_{1}! \dots \lambda_{n}!}$$"
        expected = r"$$\frac{n!}{(1!)^{\lambda_{1} } \dots (n!)^{\lambda_{n} } \cdot \lambda_{1}! \dots \lambda_{n}!}$$"
        self.assertEqual(cloze_safe_math_jax(text), expected)

        text = r"blib blob {{}}}}}}}{{{ $$\frac{n!}{(1!)^{\lambda_{1}} \dots (n!)^{\lambda_{n}} \cdot \lambda_{1}! \dots \lambda_{n}!}$$"
        expected = r"blib blob {{}}}}}}}{{{ $$\frac{n!}{(1!)^{\lambda_{1} } \dots (n!)^{\lambda_{n} } \cdot \lambda_{1}! \dots \lambda_{n}!}$$"
        self.assertEqual(cloze_safe_math_jax(text), expected)