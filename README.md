# Markdown2Anki - Converter

This project is a Python-based tool for converting markdown files into Anki-compatible packages. It processes markdown
files, extracts card data, and generates an Anki package that can be imported into the Anki flashcard application.

## Features

- Processes markdown files into different note types (basic cards, clozes and image occlusion cards)
- Supports image processing for cards.
- Plugin-Based - Easily extendable to support additional note types or features.

## Requirements

- Python 3.8 or higher
- The following Python libraries:
    - `markdown`
    - `genanki`

## Usage - Basic Adding from Input

1. Place your markdown files in a directory called `input`. If you reference any images place them in the same directory

2. Run the script:
   ```bash
   python basic_adding_from_input.py
   ```

3. The processed Anki package will be saved in the `output` directory.

## Expected Input Format
The markdown files should follow a specific format for the tool to process them correctly. Here are the expected formats for different note types:

In general the file should have the following format:

```markdown
# Headings (that will be used for tags)
## Subheadings
### Subsubheadings

---
A question in the first line
And the answer in the second line

---
Another question.
EQL: For an extra question line users can use the EQL (Extra-Question-Line) Prefix followed by a colon
And here the answer
with as much new lines as the user wanst
![[image.png]]
Images can be used as well
We also support enumerations and bullet poinst:
- first
  - sub point
- second

1. first
2. second

# Headings between questions are fine too
---
Cloze Image
![[image.png]]

---
Cloze
Here is text that will be added to a cloze card. All cloze cards will get an extra tag, so that the 
user can add the clozes in the Anki-Interface.

```

### Formatting Guidelines

- Each **question and answer** pair must be separated by a line with three dashes (`---`).
- **Questions and answers** can span multiple lines:
  - If a question needs multiple lines, prefix additional lines with `EQL:` (Extra-Question-Line).
  - Answers do **not** require any prefixes.
- **Markdown syntax** (e.g., images, bullet points, enumerations) is fully supported and will automatically be converted to HTML.

### Special Card Types

- **Cloze Cards**:  
  - To create a Cloze card, the question line must contain only the word `Cloze`.
  - The corresponding answer should include the text for the cloze deletion.  
  - Note: Clozes are not generated automatically — the user must manually insert the cloze formatting later. A special identifier tag will be added to help locate these cards.

- **Image Occlusions**:  
  - Referenced images will be saved to the output folder for further processing.
  - An additional output file will be created containing the corresponding tags.


### Additional Features

- **Headings as Tags**:  
  - Headings between questions are allowed and will be used as tags.
  - The first heading will be treated as the **main tag**, the second as a **subtag**, and so forth.


- **Code Blocks**:  
  - To mark code blocks for extra tagging, include the identifier `#CODE#` inside the code block.
  - This will ensure a special tag is added for easier later processing.

## Output

The output will be an Anki package file (`.apkg`) located in the `output` directory. The package will contain all the processed cards. 
- All Clozes will have an extra tag: "TODO_PROCESS_CLOZES"
- All Cards containing the `#CODE#` tag, will have an extra tag: "TODO_PROCESS_CODE"
- The output folder will contain all images that can be used for image occlusions

## Project Structure

```
.
├── input/                      # Directory for input markdown files
├── output/                     # Directory for generated Anki packages (automatically generated)
├── markdown2anki/              # Library code
├── basic_adding_from_input.py  # Example script for processing files
├── requirements.txt            # Python dependencies
└── README.md                   # Project documentation
```