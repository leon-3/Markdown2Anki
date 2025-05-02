import os
import random
import re
from collections import defaultdict
import string

from .processors import Processor


class ImageProcessor(Processor):

    def __init__(self):
        super().__init__(self.replace_md_image_with_html)

        self.media_files = [] # Store all media files that will be added to the exported anki package
        self.tags_mapped_to_images = defaultdict(list)  # key: tag, value: list of images
        self.image_occlusion_count = 0
        self.used_images_mapped_to_unique_name = dict() # key: original image name, value: unique name
        self.unique_image_name = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8)) + "_image_"
        self.input_directory = "input/"

        if os.path.exists("output"):
            for file in os.listdir("output"):
                os.remove(f"output/{file}")
            os.rmdir("output")
            print("Output folder deleted (Reason: new ImageProcessor instance)")


    def replace_md_image_with_html(self, text: str) -> str:
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
            if self.input_directory + image[3:-2] not in self.media_files:
                self.media_files.append(self.input_directory + image[3:-2])
        return text

    def process_image_occlusion(self, cloze_text: str, tag: str) -> None:
        """
        Process image occlusion by saving the images to the output folder and mapping them to the tags, since image
        occlusion have to be handled by the user manually there is no need to add them to the package.
        :param cloze_text: The text where the exact file name of the image is
        :param tag: The tag that should be added to the image
        :return: None
        """

        images = re.findall(r"!\[\[.+\]\]", cloze_text)
        if not images:
            print("Error: No image found for image occlusion (tag: " + tag + ")")
            return

        for image in images:
            if not os.path.exists("output"):
                os.makedirs("output")
                print("Output folder created (Reason: new ImageProcessor instance)")

            # get file extension of image
            extension = "." + image[3:-2].split(".")[-1]
            if image[3:-2] not in self.used_images_mapped_to_unique_name:
                self.used_images_mapped_to_unique_name[image[3:-2]] = self.unique_image_name + str(
                    self.image_occlusion_count) + extension

                with open(self.input_directory + image[3:-2], "rb") as f:
                    with open("output/" + self.unique_image_name + str(self.image_occlusion_count) + extension,
                              "wb") as f1:
                        f1.write(f.read())

                self.tags_mapped_to_images[tag].append(
                    self.unique_image_name + str(self.image_occlusion_count) + extension)
                self.image_occlusion_count += 1
            else:
                self.tags_mapped_to_images[tag].append(self.used_images_mapped_to_unique_name[image[3:-2]])

    def set_input_directory(self, input_directory: str) -> None:
        """
        Set the input directory for the image processor
        :param input_directory: The input directory
        :return: None
        """
        self.input_directory = input_directory