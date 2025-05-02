def add_added_flags_to_each_valid_card(file_name: str) -> None:
    # Open file and read it
    with open(file_name, "r", encoding="utf-8") as f:
        lines = f.read().split("\n")

    new_question = False
    latest_question = ""
    latest_answer = ""

    for i, line in enumerate(lines):
        if line.startswith("#"):
            latest_question = ""
            latest_answer = ""
        elif line.startswith("---"):
            latest_question = ""
            latest_answer = ""
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
        else:
            latest_answer += line + "\n"

    # Write the modified content back to the file
    with open(file_name, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))