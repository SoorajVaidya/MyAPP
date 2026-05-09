import base64
import os
import io
import cv2
from matplotlib import pyplot as plt
import numpy as np
import requests
from dill._objects import a
from django.http import JsonResponse
import os
import uuid
import boto3
from storages.backends.s3boto3 import S3Boto3Storage
from global_utils.service_treatments_map import SERVICE_TREATMENT_MAP
from oohy_product import settings


class TreatmentResourceStorage(S3Boto3Storage):
    """Custom storage for TreatmentResource images in AWS S3 based on model field names."""

    def __init__(self, *args, **kwargs):
        self.bucket_name = os.getenv("AWS_STORAGE_BUCKET_NAME")
        region = os.getenv("AWS_S3_REGION_NAME", "ap-south-1")

        # AWS S3 Public URL
        self.custom_domain = f"{self.bucket_name}.s3.{region}.amazonaws.com"
        kwargs["access_key"] = os.getenv("AWS_ACCESS_KEY_ID")
        kwargs["secret_key"] = os.getenv("AWS_SECRET_ACCESS_KEY")

        # Remove "location" to avoid duplication if present
        kwargs.pop("location", None)

        super().__init__(*args, **kwargs)

        # Initialize S3 client
        self.s3_client = boto3.client(
            "s3",
            aws_access_key_id=kwargs["access_key"],
            aws_secret_access_key=kwargs["secret_key"],
            region_name=region,
        )

    def _save(self, name, content):
        # Extract field name from the upload path
        field_name = name.split("/")[-2]
        # Generate a unique file name
        unique_filename = f"{uuid.uuid4().hex}.png"  # Adjust the extension if needed
        # Construct new path based on model field name
        name = f"TreatmentResource/{field_name}/{unique_filename}"
        return super()._save(name, content)

    def url(self, name):
        """Generate the public URL for a file stored in the bucket."""
        return f"https://{self.custom_domain}/{name}"

    def delete(self, name):
        """Deletes an object from AWS S3."""
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=name)
        except self.s3_client.exceptions.NoSuchKey:
            pass  # File does not exist
        except Exception as e:
            print(f"Error deleting file {name}: {e}")
            raise


def image_url_to_base64(image_url):
    """
    Converts an image URL or a BytesIO object to a base64-encoded string.
    If the URL is already in base64 format (or starts with a common base64 signature),
    it returns it with a "data:image/png;base64," prefix.
    """
    
    if isinstance(image_url, io.BytesIO):
        image_url.seek(0)
        encoded_image = base64.b64encode(image_url.read()).decode("utf-8")
        return f"data:image/png;base64,{encoded_image}"

    # If the image_url string already appears to be base64 encoded (or starts with a known signature),
    # then add the prefix and return it.
    if isinstance(image_url, str) and image_url.startswith(
        ("data:image/png;base64,", "data:image/jpeg;base64,", "/9j/")
    ):
        return f"data:image/png;base64,{image_url}"

    try:
        response = requests.get(image_url, stream=True)
        response.raise_for_status()  # Raises an error for invalid responses
        image_data = base64.b64encode(response.content).decode("utf-8")

        content_type = response.headers.get("Content-Type", "")
        if "image/png" in content_type:
            return f"data:image/png;base64,{image_data}"
        elif "image/jpeg" in content_type:
            return f"data:image/jpeg;base64,{image_data}"
        else:
            
            return ""  # Handle other formats if necessary

    except requests.RequestException as e:
        # print(f"Error fetching image: {e}")
        return ""


def extract_treatment_columns(service_ids):
    # The list of service ids you want to filter by
    service_ids = [7, 80]  # This can be an empty list as well

    # Step 1: Check if the service_ids list is empty
    if not service_ids:
        # If the list is empty, extract all values
        treatment_values = list(SERVICE_TREATMENT_MAP.values())
    else:
        # If the list is not empty, filter based on the list
        treatment_values = [
            SERVICE_TREATMENT_MAP[str(service_id)]
            for service_id in service_ids
            if str(service_id) in SERVICE_TREATMENT_MAP
        ]

    # print(treatment_values)


def process_image_and_annotations(image_url, annotation_file_path, points_input):
    # Validate annotation file existence

    if not os.path.exists(annotation_file_path):
        return JsonResponse(
            {"error": f"Annotation file not found: {annotation_file_path}"}, status=400
        )

    # Load the image from URL
    try:
        response = requests.get(image_url)
        response.raise_for_status()
        image_array = np.frombuffer(response.content, np.uint8)
        image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
    except requests.RequestException as e:
        return JsonResponse(
            {"error": f"Failed to fetch image from URL: {image_url}. Error: {str(e)}"},
            status=400,
        )

    if image is None:
        return JsonResponse(
            {"error": f"Failed to decode image from URL: {image_url}"}, status=400
        )

    height, width, _ = image.shape

    # Parse the annotation file
    with open(annotation_file_path, "r") as file:
        annotations = file.readlines()

    # Extract point identifiers from request
    points_to_highlight = points_input.strip().upper().split(",")
    points_to_highlight = [point.strip() for point in points_to_highlight]

    ls = [line.split()[0] for line in annotations]
    highlighted_points = []

    for point in points_to_highlight:
        try:
            index = ls.index(point)
        except ValueError:
            return JsonResponse({"error": f"Point not found: {point}"}, status=400)

        # Process the annotation
        annotation = annotations[index]
        data = annotation.split()

        # Ignore the first numerical value (metadata)
        region_id, data = data[0], data[2:]

        # Validate the remaining data for coordinate pairs
        if len(data) % 2 != 0:
            return JsonResponse(
                {"error": f"Invalid coordinate data for point {point}: {data}"},
                status=400,
            )

        try:
            points = np.array(
                [
                    (float(data[i]) * width, float(data[i + 1]) * height)
                    for i in range(0, len(data), 2)
                ],
                np.int32,
            )
        except ValueError:
            return JsonResponse(
                {"error": f"Non-numeric data found for point {point}: {data}"},
                status=400,
            )

        # Draw the region on the image
        points = points.reshape((-1, 1, 2))
        # cv2.polylines(image, [points], isClosed=True, color=(255, 0, 0), thickness=5)

        # Compute and draw the centroid
        M = cv2.moments(points)
        if M["m00"] != 0:
            centroid_x = int(M["m10"] / M["m00"])
            centroid_y = int(M["m01"] / M["m00"])
        else:
            centroid_x = int(points[:, 0].mean())
            centroid_y = int(points[:, 1].mean())
        cv2.circle(
            image, (centroid_x, centroid_y), radius=20, color=(0, 0, 0), thickness=-1
        )
        text_to_display = points_input  # Directly display the input text
        # cv2.putText(
        #     image,
        #     text_to_display,
        #     (width - 600, height - 250),
        #     cv2.FONT_HERSHEY_COMPLEX,
        #     4,
        #     (0, 25, 0),
        #     5,
        #     cv2.LINE_AA,
        # )

        highlighted_points.append(point)

    # Encode the image as a base64 string
    _, buffer = cv2.imencode(".jpg", image)
    image_base64 = base64.b64encode(buffer).decode("utf-8")

    return image_base64, highlighted_points


def highlight_points(image_path, annotation_file, input_points):

    # print(233, input_points)
    # print(234, annotation_file)
    """
    Highlights specific points on an image based on provided annotations.

    This modified version:
      - Loads an image from a URL or local file.
      - Creates an overlay copy for transparent drawing.
      - Draws a note (with word wrapping and a background rectangle) on the image.
      - Loads annotation coordinates from a file.
      - Uses a predefined color map (with a default yellow if color not found).
      - Defines certain labels as "circle" labels. For these, it computes the center and an approximate radius,
        then draws a border circle (on the overlay) and fills the inner circle.
      - For non-circle labels, it fills the corresponding polygon.
      - Blends the overlay with the image, prints status messages, and returns a base64-encoded JPEG.

    :param image_path: Path or URL to the input image.
    :param annotation_file: Path to the annotation file containing coordinates.
    :param input_points: List of labels with associated colors
                         (e.g., ['Left-Little-Ring-3-Red', 'Left-Little-Ring-4-Black']).
    :return: Base64 encoded image string, or None on error.
    """

    # Load image from URL or local file
    image = None
    if image_path.startswith("http://") or image_path.startswith("https://"):
        try:
            # print("362")
            response = requests.get(image_path, timeout=10)
            response.raise_for_status()
            image_array = np.frombuffer(response.content, np.uint8)
            image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
            if image is None:
                print(f"Error: Failed to decode image from URL: {image_path}")
                return None
        except requests.RequestException as e:
            print(
                f"Error: Failed to fetch image from URL: {image_path}. Exception: {e}"
            )
            return None
    else:
        if not os.path.exists(image_path):
            print(f"Error: Image file '{image_path}' not found!")
            return None
        image = cv2.imread(image_path)
        if image is None:
            print(f"Error: Failed to load image from local file: {image_path}")
            return None

    # cv2.circle(image, (100, 100), 50, (255, 0, 0), 2)
    # cv2.imshow("Image with Circle", image)
    # cv2.waitKey(0)
    # cv2.destroyAllWindows()
    # return

    height, width, _ = image.shape

    # Create an overlay copy for transparent drawing (used for circle borders)
    overlay = image.copy()

    # --- Add note text overlay (with background rectangle and word wrap) ---
    note_text = (
        "Note: Apply the color precisely on the marked points for better effectiveness. "
        * 8
    ).strip()
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_size = 0.8
    font_thickness = 2
    text_color = (0, 0, 0)  # Black text
    bg_color = (255, 255, 255)  # White ba qckground
    text_x = 50  # Left margin
    text_max_width = width - 100  # Right margin (50px on each side)
    line_spacing = 15  # Space between lines

    def wrap_text(text, font, font_size, thickness, max_width):
        words = text.split()
        lines = []
        current_line = ""
        for word in words:
            test_line = current_line + " " + word if current_line else word
            text_size, _ = cv2.getTextSize(test_line, font, font_size, thickness)
            if text_size[0] <= max_width:
                current_line = test_line
            else:
                lines.append(current_line)
                current_line = word  # Start new line
        if current_line:
            lines.append(current_line)
        return lines

    wrapped_lines = wrap_text(
        note_text, font, font_size, font_thickness, text_max_width
    )
    _, text_height = cv2.getTextSize("A", font, font_size, font_thickness)
    total_text_height = len(wrapped_lines) * (text_height + line_spacing)
    text_y = min(height - total_text_height - 50, height - 70)
    rect_bottom_y = text_y + total_text_height + 10

    # Draw background rectangle for text
    cv2.rectangle(
        image,
        (text_x - 10, text_y - text_height - 10),
        (text_x + text_max_width + 10, rect_bottom_y),
        bg_color,
        -1,
    )
    for i, line in enumerate(wrapped_lines):
        line_y = text_y + i * (text_height + line_spacing)
        cv2.putText(
            image, line, (text_x, line_y), font, font_size, text_color, font_thickness
        )

    # --- Load annotation file ---
    if not os.path.exists(annotation_file):
        print(f"Error: Annotation file '{annotation_file}' not found!")
        return None

    with open(annotation_file, "r") as file:
        annotations = file.readlines()

    # Build a dictionary of annotation points; keys are labels (upper-case)
    annotations_dict = {}
    for annotation in annotations:
        parts = annotation.strip().split()
        if len(parts) < 2:
            continue
        label = parts[0].strip().upper()
        if label not in annotations_dict:
            annotations_dict[label] = []
        annotations_dict[label].append(parts[1:])

    # Predefined color map (BGR)
    color_map = {
        "RED": (0, 0, 255),
        "GREEN": (0, 255, 0),
        "BLUE": (255, 0, 0),
        "YELLOW": (0, 255, 255),
        "CYAN": (255, 255, 0),
        "MAGENTA": (255, 0, 255),
        "WHITE": (255, 255, 255),
        "BLACK": (0, 0, 0),
        "ORANGE": (0, 165, 255),
        "PURPLE": (128, 0, 128),
        "PINK": (255, 20, 147),
        "BROWN": (42, 42, 165),
        "GRAY": (128, 128, 128),
        "SKYBLUE": (255, 255, 0),
    }

    # Define labels that should be drawn as circles with a border and center fill.
    circle_labels = {f"LEFT-CENTER-YANG-{i}" for i in range(1, 17)}
    circle_labels.update({f"LEFT-CENTER-YIN-{i}" for i in range(1, 26)})
    circle_labels.update({f"RIGHT-CENTER-YANG-{i}" for i in range(1, 17)})
    circle_labels.update({f"RIGHT-CENTER-YIN-{i}" for i in range(1, 26)})
    circle_labels.update({str(i) for i in range(1, 28)})

    found_labels = []
    not_found_labels = []

    # Set border opacity and thickness for circle labels
    border_opacity = 0.2
    border_thickness = 5

    # Sort input points (sorting logic based on the last segment if numeric)
    sorted_points = sorted(
        input_points,
        key=lambda x: (
            int(x.split("-")[-1]) if x.split("-")[-1].isdigit() else float("inf")
        ),
    )

    for term in sorted_points:
        parts = term.rsplit("-", 1)
        if len(parts) != 2:
            print(f"Invalid input format: {term}. Use format 'Label-Color'. Skipping.")
            continue

        label, color_name = parts
        label = label.strip().upper()
        color_name = color_name.strip().upper()
        color = color_map.get(
            color_name, (255, 244, 0)
        )  # Default to yellow if color not found

        if label in annotations_dict:
            found_labels.append(f"{label} ({color_name})")
            for data in annotations_dict[label]:
                try:
                    # Ensure there is at least one pair of coordinates (skip if not)
                    if len(data) < 3:
                        print(
                            f"Skipping '{label}': Insufficient coordinate data -> {data}"
                        )
                        continue
                    points = np.array(
                        [
                            (float(data[i]) * width, float(data[i + 1]) * height)
                            for i in range(1, len(data), 2)
                        ],
                        np.int32,
                    )
                except (ValueError, IndexError) as e:
                    print(f"Error processing '{label}' -> {data}. Error: {e}")
                    continue

                points = points.reshape((-1, 1, 2))

                if label in circle_labels:
                    # Compute center and approximate radius for circle labels
                    # print("429")
                    center_x = int(np.mean(points[:, 0, 0]))
                    center_y = int(np.mean(points[:, 0, 1]))
                    radius = int(np.linalg.norm(points[0][0] - (center_x, center_y)))
                    # Draw border circle on overlay and fill inner circle on main image
                    cv2.circle(
                        overlay, (center_x, center_y), radius, color, border_thickness
                    )
                    cv2.circle(
                        image,
                        (center_x, center_y),
                        max(radius - border_thickness, 0),
                        color,
                        -1,
                    )
                else:
                    # For non-circle labels, fill the polygon
                    cv2.fillPoly(image, [points], color)
        else:
            not_found_labels.append(label)

    # Blend the overlay with the image for a transparent border effect on circles
    cv2.addWeighted(overlay, border_opacity, image, 1 - border_opacity, 0, image)

    # Print status messages
    if found_labels:
        print(f"Highlighted: {', '.join(found_labels)}")
    if not_found_labels:
        print(
            f"Warning: The following labels were not found: {', '.join(not_found_labels)}"
        )

    # Save the output image
    output_path = "highlighted_image.jpg"
    cv2.imwrite(output_path, image)
    print("Output saved at:", os.path.abspath(output_path))

    # Try displaying the image using cv2.imshow; if that fails, use matplotlib.
    try:
        cv2.imshow("Highlighted Image", image)
        cv2.waitKey(0)
        cv2.destroyAllWindows()
    except Exception as e:
        print("cv2.imshow did not work, falling back to matplotlib. Error:", e)
        plt.imshow(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
        plt.axis("off")
        plt.title("Highlighted Image")
        plt.show()

    # Convert the final image to a base64-encoded JPEG
    _, buffer = cv2.imencode(".jpg", image)
    base64_image = base64.b64encode(buffer).decode("utf-8")
    return base64_image


def multi_seed_image_generation(image_path, annotation_file_path, labels_input):
    """
    Highlights specific regions on a multi-seed image based on annotations and user input.

    Args:
        image_path (str): Local file path or URL to the input image.
        annotation_file_path (str): Path to the annotation file containing coordinates.
        labels_input (str): Comma or space separated labels with colors
                            (e.g., "Right-3-Red, Left-5-Black, BACK-12-Blue").

    Returns:
        tuple: (base64-encoded image string, list of highlighted labels)
               OR a JsonResponse in case of error.
    """
    # Validate annotation file existence
    if not os.path.exists(annotation_file_path):
        return JsonResponse(
            {"error": f"Annotation file not found: {annotation_file_path}"}, status=400
        )

    # Load the image: check if image_path is a URL or a local file path
    if image_path.startswith("http://") or image_path.startswith("https://"):
        try:
            response = requests.get(image_path, timeout=10)
            response.raise_for_status()
            image_array = np.frombuffer(response.content, np.uint8)
            image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
            if image is None:
                return JsonResponse(
                    {"error": f"Failed to decode image from URL: {image_path}"},
                    status=400,
                )
        except requests.RequestException as e:
            return JsonResponse(
                {
                    "error": f"Error fetching image from URL: {image_path}. Exception: {str(e)}"
                },
                status=400,
            )
    else:
        if not os.path.exists(image_path):
            return JsonResponse(
                {"error": f"Image file not found: {image_path}"}, status=400
            )
        image = cv2.imread(image_path)
        if image is None:
            return JsonResponse(
                {"error": f"Failed to load image from path: {image_path}"}, status=400
            )

    height, width, _ = image.shape

    # Create an overlay copy for transparency effects
    overlay = image.copy()

    # Load the annotation file
    with open(annotation_file_path, "r") as file:
        annotations = file.readlines()

    # --- Draw Note Text ---

    font = cv2.FONT_HERSHEY_SIMPLEX
    font_size = 1.5
    font_thickness = 4
    text_color = (0, 0, 0)  # Black text
    bg_color = (255, 255, 255)  # White background
    text_x = 150  # Left margin
    text_max_width = width - 100  # Right margin
    line_spacing = 15

    def wrap_text(text, font, font_size, thickness, max_width):
        words = text.split()
        lines = []
        current_line = ""
        for word in words:
            test_line = current_line + " " + word if current_line else word
            text_size, _ = cv2.getTextSize(test_line, font, font_size, thickness)
            if text_size[0] <= max_width:
                current_line = test_line
            else:
                lines.append(current_line)
                current_line = word
        if current_line:
            lines.append(current_line)
        return lines

    # # wrapped_lines = wrap_text(font, font_size, font_thickness, text_max_width)
    # _, text_height = cv2.getTextSize("A", font, font_size, font_thickness)
    # total_text_height = len(wrapped_lines) * (text_height + line_spacing)
    # text_y = max(50, height - total_text_height - 300)
    # rect_bottom_y = text_y + total_text_height + 10

    # cv2.rectangle(
    #     image,
    #     (text_x - 10, text_y - text_height - 10),
    #     (text_x + text_max_width + 10, rect_bottom_y),
    #     bg_color,
    #     -1
    # )

    # for i, line in enumerate(wrapped_lines):
    #     line_y = text_y + i * (text_height + line_spacing)
    #     cv2.putText(image, line, (text_x, line_y), font, font_size, text_color, font_thickness)

    # --- Process Annotations ---
    # Build a dictionary where each key is a label (uppercase) and its value is a list of coordinate data.
    annotations_dict = {}
    for annotation in annotations:
        parts = annotation.strip().split()
        if len(parts) < 2:
            continue
        label = parts[0].strip().upper()
        if label not in annotations_dict:
            annotations_dict[label] = []
        annotations_dict[label].append(parts[1:])

    # Predefined color map (BGR format)
    color_map = {
        "RED": (0, 0, 255),
        "GREEN": (0, 255, 0),
        "DARKBLUE": (204, 0, 0),
        "YELLOW": (0, 255, 255),
        "CYAN": (255, 255, 0),
        "MAGENTA": (255, 0, 255),
        "WHITE": (255, 255, 255),
        "BLACK": (0, 0, 0),
        "ORANGE": (0, 165, 255),
        "PURPLE": (128, 0, 128),
        "PINK": (255, 20, 147),
        "BROWN": (42, 42, 165),
        "GRAY": (128, 128, 128),
    }

    # Labels that need circles (with center points) instead of filled polygons
    circle_labels = {f"RIGHT-{i}" for i in range(1, 30)}
    circle_labels.update({f"LEFT-{i}" for i in range(1, 30)})

    # Process the user input.
    # Expected format: "Right-3-Red, Left-5-Black, BACK-12-Blue"
    search_terms = [
        term.strip().upper() for term in labels_input.replace(",", " ").split()
    ]
    highlighted_labels = (
        []
    )  # This will collect labels that were successfully highlighted
    # If needed, you can also collect not-found labels separately.
    found_lables = []
    not_found_lables = []
    center_dot_radius = 25
    # -1 means a filled circle (no outline)
    center_dot_thickness = -1

    # Outline thickness for polygons (used for non-circle labels, if needed)
    polygon_outline_thickness = 0

    for term in search_terms:
        parts = term.rsplit("-", 1)
        if len(parts) != 2:
            print(f"Invalid input format: {term}. Use format 'Label-Color'. Skipping.")
            continue

        label, color_name = parts
        color_name = color_name.strip().upper()
        color = color_map.get(
            color_name, (204, 0, 0)
        )  # default to DarkBlue if not found

        if label in annotations_dict:
            found_lables.append(f"{label} ({color_name})")
            for data in annotations_dict[label]:
                coords = [float(x) for x in data]
                points = np.array(
                    [
                        (coords[i] * width, coords[i + 1] * height)
                        for i in range(1, len(coords), 2)
                    ],
                    np.int32,
                )

                # Compute center of the polygon
                center_x = int(np.mean(points[:, 0]))
                center_y = int(np.mean(points[:, 1]))

                if label in circle_labels:
                    # (Removed cv2.polylines(...) so there's no polygon outline)
                    # Just draw a filled circle at the center
                    cv2.circle(
                        image,
                        (center_x, center_y),
                        center_dot_radius,
                        color,
                        center_dot_thickness,
                    )
                else:
                    # For other labels, fill the polygon (or do any style you want)
                    cv2.fillPoly(image, [points], color)
        else:
            not_found_lables.append(label)
    border_opacity = 0  # No overlay opacity
    border_thickness = 5

    # Optionally, you could track labels not found.

    # Blend the overlay with the image (if any overlay was drawn)
    cv2.addWeighted(overlay, border_opacity, image, 1 - border_opacity, 0, image)

    # Encode the resulting image as a base64 string
    _, buffer = cv2.imencode(".jpg", image)
    image_base64 = base64.b64encode(buffer).decode("utf-8")

    # Return only two values to match the caller's expectation:
    return image_base64, highlighted_labels


def color_therapy(image_url, search_terms):
    # Overwrite search_terms with the provided fixed list.
   
    # Download and decode image from URL.
    try:
        response = requests.get(image_url)
        response.raise_for_status()
    except Exception as e:
        raise Exception(
            f"Error: Unable to download image from URL '{image_url}'. Exception: {e}"
        )

    image_data = np.frombuffer(response.content, np.uint8)
    image = cv2.imdecode(image_data, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Error: The image downloaded from '{image_url}' is invalid.")

    height, width, _ = image.shape
    overlay = image.copy()

    # Build annotation file path and load annotations.
    annotation_file = os.path.join(
        settings.BASE_DIR, "image_processing/colour_coordinates.txt"
    )
    if not os.path.exists(annotation_file):
        raise FileNotFoundError(
            f"Error: Annotation file '{annotation_file}' not found!"
        )

    with open(annotation_file, "r") as file:
        annotations = file.readlines()

    annotations_dict = {}
    for annotation in annotations:
        parts = annotation.strip().split()
        if len(parts) < 3:
            continue
        key = parts[0].strip().upper()
        annotations_dict.setdefault(key, []).append(parts[1:])

    # Define a color map (BGR format).
    color_map = {
        "RED": (0, 0, 255),
        "GREEN": (0, 111, 61),
        "BLUE": (255, 0, 0),
        "YELLOW": (0, 255, 255),
        "CYAN": (255, 255, 0),
        "MAGENTA": (255, 0, 255),
        "WHITE": (255, 255, 255),
        "BLACK": (0, 0, 0),
        "ORANGE": (0, 128, 255),
        "PURPLE": (128, 0, 128),
        "PINK": (153, 0, 153),
        "BROWN": (42, 42, 165),
        "GRAY": (128, 128, 128),
        "SKYBLUE": (255, 153, 51),
    }

    # Define the set of labels that should be drawn as circles.
    circle_labels = {f"RIGHT-CENTER-YIN-{i}" for i in range(1, 30)}
    circle_labels.update({f"LEFT-CENTER-YIN-{i}" for i in range(1, 30)})

    found_labels = []
    not_found_labels = []

    # Flatten search_terms in case any entry contains comma-separated terms.
    all_search_terms = []
    for term in search_terms:
        for t in term.split(","):
            term_clean = t.strip()
            if term_clean:
                all_search_terms.append(term_clean)

    # Process each search term only once.
    for term in all_search_terms:
        if "-" not in term:
            print(
                f"Invalid input format: {term}. Expected format 'Label-Color'. Skipping."
            )
            continue

        # Split on the last hyphen to separate label and color.
        label_part, color_name = term.rsplit("-", 1)
        label_key = label_part.strip().upper()
        color_key = color_name.strip().upper()
        color = color_map.get(
            color_key, (255, 255, 255)
        )  # default to white if not found

        if label_key in annotations_dict:
            found_labels.append(f"{label_key} ({color_key})")
            for coords in annotations_dict[label_key]:
                try:
                    numeric_coords = list(map(float, coords))
                    # If the first number is a flag (e.g. 0 or 1), remove it.
                    if numeric_coords and numeric_coords[0] in (0, 1):
                        numeric_coords = numeric_coords[1:]
                    if len(numeric_coords) % 2 != 0:
                        print(
                            f"Warning: Coordinate count for label '{label_key}' is not even. Skipping this annotation."
                        )
                        continue
                    # Convert normalized coordinates to absolute pixel values.
                    points = [
                        (int(x * width), int(y * height))
                        for x, y in zip(numeric_coords[0::2], numeric_coords[1::2])
                    ]
                    points_array = np.array(points, np.int32).reshape((-1, 1, 2))

                    if label_key in circle_labels:
                        # Compute the center of the circle as the mean of the points.
                        points_np = np.array(points)
                        center_x = int(np.mean(points_np[:, 0]))
                        center_y = int(np.mean(points_np[:, 1]))
                        center_dot_radius = 25  # fixed radius for the center dot
                        cv2.circle(
                            image, (center_x, center_y), center_dot_radius, color, -1
                        )
                    else:
                        # For non-circle labels, fill the polygon.
                        cv2.fillPoly(image, [points_array], color)

                    # Optionally, draw a border on the overlay for all annotations.
                    cv2.polylines(
                        overlay, [points_array], isClosed=True, color=color, thickness=2
                    )
                except Exception as e:
                    print(
                        f"Error processing coordinates for '{label_key}': {coords}. Error: {e}"
                    )
        else:
            not_found_labels.append(term)

    # Blend the overlay with the image for a transparent effect.
    alpha = 0.4  # adjust transparency factor as needed.
    cv2.addWeighted(overlay, alpha, image, 1 - alpha, 0, image)

    if found_labels:
        print(f"Highlighted: {', '.join(found_labels)}")
    if not_found_labels:
        print(
            f"Warning: The following labels were not found: {', '.join(not_found_labels)}"
        )

    # Encode the resulting image to a JPEG and then to a Base64 string.
    retval, buffer = cv2.imencode(".jpg", image)
    base64_image = base64.b64encode(buffer).decode("utf-8")
    return base64_image
