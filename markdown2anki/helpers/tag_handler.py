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
