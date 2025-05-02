import unittest
import os
from markdown2anki import add_added_flags_to_each_valid_card

SAMPLE_FILE_1 = r"""
---
Cloze
**Definitionen zu Linearkombinationen**:
1. seien $v_{1}, \dots, v_{n} \in V$ **Vektoren**, ein Vektor $v \in V$ heißt **Linearkombination** von $v_{1}, \dots, v_{n}$, falls es Skalare $a_{1}, \dots, a_{n} \in K$ gibt mit $$v = a_{1}v_{1} + \dots + a_{n}v_{n}$$
2. sei $S \subseteq V$ eine **Teilmenge**, ein Vektor $v \in V$ heißt **Linearkombination** von $S$, falls es $n \in \mathbb{N}$ und $v_{1}, \dots, v_{n} \in S$ gibt, sodass $v$ eine **Linearkombination** von $v_{1}, \dots, v_{n}$ ist.
3. falls $S = \emptyset$, so sagen wir, dass der **Nullvektor** 0 (die einzige) **Linearkombination** von $S$ ist (0 wird als leere Summe aufgefasst)

Bemerkungen:
- in Fall 2. kann $S$ **unendlich viele Elemente** enthalten
- aber: $v_{1}, \dots, v_{n}$ sind **endlich viele Vektoren**.

---
**Nennen** Sie einen **Satz** zum von $S \subseteq V$ **induzierten Unterraum** im Bezug auf **Linearkombinationen**.
Für eine Teilmenge $S \subseteq V$ ist der **erzeugte Unterraum** $\langle S \rangle$ die **Menge aller Linearkombinationen** von $S$:
$$
\langle S \rangle = \{  v \in V ~|~ v \text{ ist Linearkombination von } S \}
$$
**Insbesondere** gilt für $v_{1}, \dots, v_{n} \in V$:
$$
\langle v_{1}, \dots, v_{n} \rangle = \left\{ \sum_{i = 1}^n a_{i} v_{i} ~ \colon ~a_{1}, \dots, a_{n} \in K \right\}
$$

---
Image Cloze
![[Pasted image 20250426161407.png]]

---



---



---



---"""

EXPECTED_FILE_2 = r"""
---
ADDED: Cloze
**Definitionen zu Linearkombinationen**:
1. seien $v_{1}, \dots, v_{n} \in V$ **Vektoren**, ein Vektor $v \in V$ heißt **Linearkombination** von $v_{1}, \dots, v_{n}$, falls es Skalare $a_{1}, \dots, a_{n} \in K$ gibt mit $$v = a_{1}v_{1} + \dots + a_{n}v_{n}$$
2. sei $S \subseteq V$ eine **Teilmenge**, ein Vektor $v \in V$ heißt **Linearkombination** von $S$, falls es $n \in \mathbb{N}$ und $v_{1}, \dots, v_{n} \in S$ gibt, sodass $v$ eine **Linearkombination** von $v_{1}, \dots, v_{n}$ ist.
3. falls $S = \emptyset$, so sagen wir, dass der **Nullvektor** 0 (die einzige) **Linearkombination** von $S$ ist (0 wird als leere Summe aufgefasst)

Bemerkungen:
- in Fall 2. kann $S$ **unendlich viele Elemente** enthalten
- aber: $v_{1}, \dots, v_{n}$ sind **endlich viele Vektoren**.

---
ADDED: **Nennen** Sie einen **Satz** zum von $S \subseteq V$ **induzierten Unterraum** im Bezug auf **Linearkombinationen**.
Für eine Teilmenge $S \subseteq V$ ist der **erzeugte Unterraum** $\langle S \rangle$ die **Menge aller Linearkombinationen** von $S$:
$$
\langle S \rangle = \{  v \in V ~|~ v \text{ ist Linearkombination von } S \}
$$
**Insbesondere** gilt für $v_{1}, \dots, v_{n} \in V$:
$$
\langle v_{1}, \dots, v_{n} \rangle = \left\{ \sum_{i = 1}^n a_{i} v_{i} ~ \colon ~a_{1}, \dots, a_{n} \in K \right\}
$$

---
ADDED: Image Cloze
![[Pasted image 20250426161407.png]]

---



---



---



---"""

SAMPLES = [SAMPLE_FILE_1]
EXPECTED_FILES = [EXPECTED_FILE_2]


class TestFilePostProcessor(unittest.TestCase):

    def test_add_added_flags_to_each_valid_card(self):
        for sample, expected in zip(SAMPLES, EXPECTED_FILES):
                modified_content = test_add_added_flags_to_each_valid_card(sample)
                self.assertEqual(modified_content, expected)


def test_add_added_flags_to_each_valid_card(sample):
    # Create a temporary file with the sample content
    with open("test_file.md", "w") as f:
        f.write(sample)

    # Get the absolute path to the file including home directory
    file_name = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_file.md")

    # Call the function to be tested
    add_added_flags_to_each_valid_card(file_name)

    # Read the modified file content
    with open(file_name, "r") as f:
        modified_content = f.read()

    # Clean up the temporary file
    os.remove(file_name)

    return modified_content