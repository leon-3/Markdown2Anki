from cards import BasicCard


class MarkdownCardFile:
    card_list = []

    def __init__(self, input_lines: list, file_name: str, base_tag: str):
        """
        Given a list of lines from a markdown file, parse the lines and add them to the Anki package that will be exported.
        :param input_lines: list of lines from the input file
        :param file_name: name of the input file (will be used as the last part of the tag - e.g. "Python::FileName")
        :param base_tag: base tag for the package (e.g. "Python")
        :return: None, since the function will call the add_card_to_deck function which adds the cards to the package
        """

        # List is required since tags change dynamically with the handle_tags function, also cut the .md file extension
        tags = [base_tag, file_name[:-3]]
        new_question = False  # Indicates that "---" is found, and it is likely that a new question will be following
        latest_question = ""
        latest_answer = ""

        def add_card_if_not_empty():
            if latest_question:
                self.card_list.append(BasicCard(latest_question, latest_answer, self.merge_tags(tags)))

        for line in input_lines:
            # Case 1: Line starts with a tag (Heading in a markdown file) -> Update Tags and reset card
            if line.startswith("#"):
                add_card_if_not_empty()
                latest_question = ""
                latest_answer = ""
                tags = self.handle_tags(line, tags)

            # Case 2: Line starts with a "---" -> Reset card and process the previous card
            elif line.startswith("---"):
                add_card_if_not_empty()
                latest_question = ""
                latest_answer = ""
                new_question = True

            # Case 3: The line before was "---" -> store the line as a question
            elif new_question:
                latest_question = line
                new_question = False

            # Case 4: The line indicates by the prefix "EQL: " that this line should also be included in the question
            # -> add the line to the question variable
            elif line.startswith("EQL: "):
                latest_question += "<br>" + line[5:]

            # Else-Case: If the line is neither a tag nor a question, it will be added to the answer
            else:
                latest_answer += line + "\n"

        # Add the last card to the deck, since it's not covered by the for-loop
        add_card_if_not_empty()

    @staticmethod
    def handle_tags(new_heading: str, tags: list) -> list:
        """
        Given a new heading and a list of tags, this function updates the list of tags based on the structure of the new
        heading.
        :param new_heading: line of the new heading
        :param tags: existing tags
        :return: updated list of tags
        """

        # Remove the leading # with its whitespace and any other # characters
        stripped_heading = new_heading.replace("# ", "").replace("#", "")

        # Tag list consists of base tag and file name and is extended by each new heading
        # If you subtract 1 from the length of tag it should match if the new heading if it is a subheading
        if new_heading.count("#") == len(tags) - 1:
            tags.append(stripped_heading)
        elif new_heading.count("#") < len(tags) - 1:
            while new_heading.count("#") < len(tags) - 1:
                tags.pop()
            tags.append(stripped_heading)
        else:
            print("Error: Wrong heading structure (Tag could not be created)")

        return tags

    @staticmethod
    def merge_tags(tags: list) -> str:
        """
        Merge tags into a single string and apply tag formatting (replace spaces with underscores, have leading zeros
        (09 instead of 9) add "::" between tags).
        :param tags: list of tags
        :return: merged tags
        """

        merged_tag = ""
        for tag in tags:
            if tag != "":
                if tag[0].isdigit() and tag[0] != "0" and not tag[1].isdigit():
                    tag = "0" + tag

                merged_tag += tag.replace(". ", "_").replace(" ", "_") + "::"
        return merged_tag[:-2] if tags else ""