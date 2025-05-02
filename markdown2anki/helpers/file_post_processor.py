def add_added_flags_to_each_valid_card(file_name: str) -> None:
    """
    Processes a file containing card data and adds an "ADDED: " flag to each valid card question.

    :param file_name: The path to the file to be processed.

    The function performs the following steps:
    1. Reads the file line by line.
    2. Identifies sections of the file based on specific markers:
        - Lines starting with "#" or "---" reset the current question and answer.
        - A new question is detected after "---".
    3. Adds an "ADDED: " prefix to valid card questions that do not already have it.
    4. Appends additional content to the latest question if the line starts with "EQL: ".
    5. Writes the modified content back to the file.
    """

    # Open file and read it
    with open(file_name, "r", encoding="utf-8") as f:
        lines = f.read().split("\n")

    new_question = False
    latest_question = ""

    for i, line in enumerate(lines):
        if line.startswith("#"):
            latest_question = ""
        elif line.startswith("---"):
            latest_question = ""
            new_question = True
        elif new_question:
            new_question = False
            if line.startswith("ADDED: "):
                continue
            latest_question = line
            if latest_question:
                lines[i] = "ADDED: " + line
        elif line.startswith("EQL: "):
            latest_question += "<br>" + line[5:]

    # Write the modified content back to the file
    with open(file_name, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))