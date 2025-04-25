import os
import random
import re
from collections import defaultdict
import string


class ImageHandler:

    def __init__(self):
        self.media_files = []
        self.tags_mapped_to_images = defaultdict(list)  # key: tag, value: list of images
        self.image_occlusion_index = 0
        self.used_images_mapped_to_unique_name = dict()
        self.unique_image_name = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8)) + "_image_"

        if os.path.exists("output"):
            for file in os.listdir("output"):
                os.remove(f"output/{file}")
            os.rmdir("output")
        print("Output folder deleted (Cause: new ImageHandler instance)")

    def handle_images(self, text: str) -> str:
        """
        Find images in markdown syntax and replace them with HTML image tags, also add them to the media files for
        package handling
        :param text: Given text with markdown syntax
        :return: Updated html syntax
        """

        # Regex "!\[\[.+\]\]" find all images in the markdown file
        images = re.findall(r"!\[\[.+\]\]", text)
        for image in images:
            # 1. Replace string with the image tag
            text = text.replace(image, f'<img src="{image[3:-2]}">')
            # 2. add the attachment to the media files
            if "input/" + image[3:-2] not in self.media_files:
                self.media_files.append("input/" + image[3:-2])
        return text

    def process_image_occlusion(self, cloze_text: str, tag: str) -> None:
        images = re.findall(r"!\[\[.+\]\]", cloze_text)
        if not images:
            print("Error: No image found for image occlusion (tag: " + tag + ")")
            return
        for image in images:
            # 1. Save image to output folder
            if not os.path.exists("output"):
                os.makedirs("output")

            # get file extension of image
            extension = "." + image[3:-2].split(".")[-1]
            if image[3:-2] not in self.used_images_mapped_to_unique_name:
                self.used_images_mapped_to_unique_name[image[3:-2]] = self.unique_image_name + str(
                    self.image_occlusion_index) + extension

                with open("input/" + image[3:-2], "rb") as f:
                    with open("output/" + self.unique_image_name + str(self.image_occlusion_index) + extension,
                              "wb") as f1:
                        f1.write(f.read())

                # 2. Save message for further instructions
                self.tags_mapped_to_images[tag].append(
                    self.unique_image_name + str(self.image_occlusion_index) + extension)
                self.image_occlusion_index += 1
            else:
                self.tags_mapped_to_images[tag].append(self.used_images_mapped_to_unique_name[image[3:-2]])
