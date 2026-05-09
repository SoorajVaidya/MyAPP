import matplotlib
from matplotlib.ticker import MultipleLocator

from oohy_product import settings

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import matplotlib.pyplot as plt
import io
import os
import numpy as np
import io
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.colors import LinearSegmentedColormap
from io import BytesIO
from PIL import Image
from PIL import Image, ImageDraw, ImageFont


def generate_dosha_chart(vata_level, pitta_level, kapha_level):
    """
    Generates a flexible bar chart for given dosha levels and returns a BytesIO object.
    """

    def parse_percent(value):
        try:
            return float(value.strip("%")) / 100  # 👈 Convert percentage to decimal
        except Exception:
            return 0.6  # Default if parsing fails

    # Parse values
    vata_value = parse_percent(vata_level)
    pitta_value = parse_percent(pitta_level)
    kapha_value = parse_percent(kapha_level)

    # Data
    doshas = ["Vata", "Pitta", "Kapha"]
    values = [vata_value, pitta_value, kapha_value]
    colors = ["grey", "red", "darkblue"]

    # Bar settings
    bar_width = 0.25   # Wider bar
    gap = 0.5          # Space between bars
    positions = np.arange(len(doshas)) * (bar_width + gap)

    # Plotting
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(positions, values, color=colors, width=bar_width)

    # X-axis labels
    ax.set_xticks(positions)
    ax.set_xticklabels(doshas, fontsize=10)

    # Flexible Y-axis
    max_value = max(values)
    y_max = max(0.5, max_value * 1.2)  # At least 0.5, otherwise slightly bigger
    ax.set_ylim(0, y_max)

    # Set y-ticks at 0.1, 0.2, 0.3, etc.
    step = 0.1
    yticks = np.arange(0, y_max + step, step)
    ax.set_yticks(yticks)
    ax.set_yticklabels([f"{y:.1f}" for y in yticks])

    # Full grid: horizontal and vertical
    ax.grid(True, which='both', axis='both', linestyle='--', linewidth=0.5, alpha=0.7)

    # More padding left and right
    total_width = positions[-1] + bar_width
    ax.set_xlim(-1.0, total_width + 1.0)

    # Tight layout
    fig.tight_layout()

    # Save to BytesIO
    buf = io.BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


def plot_organ_chart(
    Wind_Yin,
    Wind_Yang,
    Heat_Yin,
    Heat_Yang,
    Humid_Yin,
    Humid_Yang,
    Dry_Yin,
    Dry_Yang,
    Cold_Yin,
    Cold_Yang,
):
    mapping = {
        "Wind_Yin": "Liv",
        "Wind_Yang": "GB",
        "Heat_Yin": "HT",
        "Heat_Yang": "SI",
        "Humid_Yin": "SP",
        "Humid_Yang": "ST",
        "Dry_Yin": "Lun",
        "Dry_Yang": "LI",
        "Cold_Yin": "KD",
        "Cold_Yang": "UB",
    }
    ordered_fields = [
        "Wind_Yin",
        "Wind_Yang",
        "Heat_Yin",
        "Heat_Yang",
        "Humid_Yin",
        "Humid_Yang",
        "Dry_Yin",
        "Dry_Yang",
        "Cold_Yin",
        "Cold_Yang",
    ]

    organ_names = [mapping[field] for field in ordered_fields]
    raw_levels = [
        Wind_Yin,
        Wind_Yang,
        Heat_Yin,
        Heat_Yang,
        Humid_Yin,
        Humid_Yang,
        Dry_Yin,
        Dry_Yang,
        Cold_Yin,
        Cold_Yang,
    ]

    level_mapping = {
        "very low": 20,
        "low": 40,
        "medium": 60,
        "high": 80,
        "very high": 100,
    }
    values = [level_mapping.get(level.lower(), 60) for level in raw_levels]

    n = len(organ_names)
    bar_width = 0.3
    small_gap = 0.1
    large_gap = 0.6

    centers = [bar_width / 2]
    for i in range(1, n):
        gap = small_gap if (i - 1) % 2 == 0 else large_gap
        centers.append(centers[i - 1] + bar_width + gap)

    colors = ["blue" if i % 2 == 0 else "red" for i in range(n)]

    fig = plt.figure(figsize=(10, 4))  # Wide image
    gs = fig.add_gridspec(1, 2, width_ratios=[4, 1])

    # Main bar chart
    ax = fig.add_subplot(gs[0])
    ax.bar(centers, values, width=bar_width, color=colors, align="center")
    ax.set_xticks(centers)
    ax.set_xticklabels(organ_names, fontsize=10)
    ax.set_ylim(0, 120)
    yticks = [20, 40, 60, 80, 100]
    ax.set_yticks([60])
    ax.set_yticklabels(["Normal"], fontsize=10)
    ax.axhline(60, color="gray", linestyle="--", linewidth=0.8, alpha=0.7)

    ax.set_xlim(centers[0] - 1, centers[-1] + 0.5)

    # Legend with color + label
    legend_ax = fig.add_subplot(gs[1])
    legend_ax.axis("off")

    # Square box size
    box_size = 0.1

    # Blue box - lower position
    legend_ax.add_patch(plt.Rectangle((0.1, 0.4), box_size, box_size, color="blue"))
    legend_ax.text(
        0.25,
        0.45,
        "Nourishment / Fluids / Cold",
        fontsize=9,
        verticalalignment="center",
    )

    # Red box - lower position
    legend_ax.add_patch(plt.Rectangle((0.1, 0.2), box_size, box_size, color="red"))
    legend_ax.text(
        0.25, 0.25, "Functional / Heat", fontsize=9, verticalalignment="center"
    )

    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=300)
    plt.close(fig)
    buf.seek(0)
    return buf


def map_level_to_weight(level):
    """
    Convert 'low', 'medium', 'high' into numeric weights.
    """
    level = level.lower().strip()
    if level == "low":
        return 0.2
    elif level == "medium":
        return 0.5
    elif level == "high":
        return 0.8
    else:
        return 0.5


def plot_diagonal_gradient(carbs_level, proteins_level, fat_level):
    """
    Creates a bottom-left to top-right gradient that transitions
    from Carbohydrates through Proteins to Fat, using custom RGB values.
    The x-axis is labeled 'Probability' and the y-axis 'Impact'.

    The legend is placed outside the main plot area on the right side.

    :param carbs_level: str ('low','medium','high') for Carbohydrates
    :param proteins_level: str ('low','medium','high') for Proteins
    :param fat_level: str ('low','medium','high') for Fat
    :return: BytesIO object containing the PNG image data
    """
    # 1. Map levels to numeric weights
    w_carbs = map_level_to_weight(carbs_level)
    w_proteins = map_level_to_weight(proteins_level)
    w_fat = map_level_to_weight(fat_level)

    # 2. Normalize so that w_carbs + w_proteins + w_fat = 1
    total = w_carbs + w_proteins + w_fat
    if total == 0:
        w_carbs = w_proteins = w_fat = 1 / 3
        total = 1
    w_carbs /= total
    w_proteins /= total
    w_fat /= total

    # 3. Define breakpoints in [0,1] for each color segment
    carb_pos = w_carbs
    protein_pos = w_carbs + w_proteins
    # Fat occupies [protein_pos, 1]

    # 4. Define new colors using the specified RGB values (normalized)
    carb_color = (252 / 255, 140 / 255, 96 / 255)  # Carbohydrates color
    protein_color = (176 / 255, 29 / 255, 26 / 255)  # Proteins color
    fat_color = (22 / 255, 11 / 255, 176 / 255)  # Fat color

    # 5. Create a segmented colormap
    cdict = [
        (0.0, carb_color),
        (carb_pos, carb_color),
        (protein_pos, protein_color),
        (1.0, fat_color),
    ]
    custom_cmap = LinearSegmentedColormap.from_list("CarbProtFat", cdict)

    # 6. Build a high-resolution 2D array for the diagonal gradient
    rows, cols = 200, 300
    gradient_data = np.zeros((rows, cols))
    max_rc = (rows - 1) + (cols - 1)
    for r in range(rows):
        for c in range(cols):
            gradient_data[r, c] = (r + c) / max_rc

    # 7. Plot the gradient with a wider figure
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.imshow(
        gradient_data, cmap=custom_cmap, origin="lower", extent=[0, cols, 0, rows]
    )

    # 8. Add grid lines (optional)
    num_divisions_x = 5
    num_divisions_y = 5
    x_ticks = np.linspace(0, cols, num_divisions_x)
    y_ticks = np.linspace(0, rows, num_divisions_y)
    ax.set_xticks(x_ticks)
    ax.set_yticks(y_ticks)
    ax.set_xticklabels([])
    ax.set_yticklabels([])
    ax.grid(True, color="white", linewidth=1.0)

    # 9. Label axes
    ax.set_xlabel("Probability", fontsize=12)
    ax.set_ylabel("Impact", fontsize=12, rotation=90, labelpad=10)

    # 10. Create legend patches and place the legend outside (to the right)
    carb_patch = mpatches.Patch(color=carb_color, label="Carbohydrates")
    protein_patch = mpatches.Patch(color=protein_color, label="Proteins")
    fat_patch = mpatches.Patch(color=fat_color, label="Fat")
    ax.legend(
        handles=[carb_patch, protein_patch, fat_patch],
        loc="center left",
        bbox_to_anchor=(1.02, 0.5),
        frameon=False,
    )

    plt.tight_layout()

    # 11. Instead of saving, return the image from an in-memory buffer
    buf = BytesIO()
    plt.savefig(buf, format="png", dpi=300)
    buf.seek(0)
    plt.close(fig)

    # Option 1: Return BytesIO buffer directly (useful for web responses)
    return buf

    # Option 2: Return a PIL Image object if needed:
    # image = Image.open(buf)
    # return image


def highlight_body_parts(image_path, selected_labels):
    """
    Highlights the given body parts on an image based on an annotations file
    and returns the modified image as a BytesIO object containing PNG data.

    Parameters:
        image_path (str): Path to the base image.
        selected_labels (list or str): Body parts to highlight. Can be a list
            (e.g., ['back-head-red', 'back-heart-green', ...]) or a comma-separated string.

    Returns:
        BytesIO: In-memory buffer containing the PNG image data.
    """
    # Define the annotations file path using settings.BASE_DIR
    annotations_file_path = os.path.join(
        settings.BASE_DIR, "image_processing/body_image_coordinates.txt"
    )
    if not os.path.exists(annotations_file_path):
        raise FileNotFoundError(f"Annotations file not found: {annotations_file_path}")

    # Load the base image and convert to RGBA
    base_image = Image.open(image_path).convert("RGBA")
    width, height = base_image.size

    # Read annotation file
    with open(annotations_file_path, "r") as f:
        annotation_lines = f.readlines()

    # Normalize the selected_labels input into a list of lowercase labels
    if isinstance(selected_labels, str):
        selected_labels = [
            label.strip().lower() for label in selected_labels.split(",")
        ]
    else:
        selected_labels = [label.strip().lower() for label in selected_labels]

    # Store centroid data as tuples: (centroid_x, centroid_y, color)
    selected_centroid_data = []

    # Process each annotation line
    for line in annotation_lines:
        tokens = line.strip().split()
        if len(tokens) < 5:
            continue
        label = tokens[0].strip().lower()
        if label not in selected_labels:
            continue

        # Determine color from the label suffix
        if label.endswith("-red"):
            color = "red"
        elif label.endswith("-green"):
            color = "green"
        else:
            continue

        coords_tokens = tokens[2:]  # Skip label and index tokens
        coords = list(map(float, coords_tokens))
        points = [(coords[i], coords[i + 1]) for i in range(0, len(coords), 2)]
        pixel_points = [(int(x * width), int(y * height)) for (x, y) in points]

        # Compute the centroid of the polygon
        centroid_x = int(sum(x for (x, y) in pixel_points) / len(pixel_points))
        centroid_y = int(sum(y for (x, y) in pixel_points) / len(pixel_points))
        selected_centroid_data.append((centroid_x, centroid_y, color))

    # Create an empty overlay image array (RGBA)
    overlay_array = np.zeros((height, width, 4), dtype=np.uint8)

    if not selected_centroid_data:
        raise ValueError(
            f"No matching annotations found for {', '.join(selected_labels)}."
        )

    # Precompute a full patch grid and its alpha channel for blending.
    max_distance = width * 0.03  # Adjust spread as needed
    r = int(np.ceil(max_distance))
    rel_x, rel_y = np.meshgrid(np.arange(-r, r), np.arange(-r, r))
    # Compute Euclidean distances for the patch
    rel_distances = np.sqrt(rel_x**2 + rel_y**2)
    full_alpha = 255 * (1 - (rel_distances / max_distance) ** 2)
    full_alpha[rel_distances > max_distance] = 0
    full_alpha = full_alpha.astype(np.uint8)

    # Precompute patches for red and green colors.
    patch_shape = (2 * r, 2 * r, 4)
    patch_red = np.zeros(patch_shape, dtype=np.uint8)
    patch_green = np.zeros(patch_shape, dtype=np.uint8)
    patch_red[..., 0] = full_alpha  # Red channel
    patch_red[..., 3] = full_alpha  # Alpha channel
    patch_green[..., 1] = full_alpha  # Green channel
    patch_green[..., 3] = full_alpha  # Alpha channel

    # For each centroid, place the appropriate precomputed patch onto the overlay
    for centroid_x, centroid_y, color in selected_centroid_data:
        patch = patch_red if color == "red" else patch_green

        # Determine the region in the overlay array where the patch should be applied.
        min_x = max(0, centroid_x - r)
        max_x_ = min(width, centroid_x + r)
        min_y = max(0, centroid_y - r)
        max_y_ = min(height, centroid_y + r)

        # Calculate the corresponding indices in the patch
        alpha_start_x = min_x - (centroid_x - r)
        alpha_end_x = alpha_start_x + (max_x_ - min_x)
        alpha_start_y = min_y - (centroid_y - r)
        alpha_end_y = alpha_start_y + (max_y_ - min_y)
        local_patch = patch[alpha_start_y:alpha_end_y, alpha_start_x:alpha_end_x]

        # Blend the local patch with the overlay using maximum blending
        overlay_array[min_y:max_y_, min_x:max_x_] = np.maximum(
            overlay_array[min_y:max_y_, min_x:max_x_], local_patch
        )

    # Composite the overlay onto the base image
    overlay_image = Image.fromarray(overlay_array, mode="RGBA")
    result_image = Image.alpha_composite(base_image, overlay_image)

    # Save the resulting image into a BytesIO buffer as PNG
    buf = BytesIO()
    result_image.save(buf, format="PNG")
    buf.seek(0)

    return buf


def pulse_image(data):
    """
    Plots the last 1000 points of the given data (or all points if fewer than 1000)
    on a wide figure, then returns the plot as a PNG image stored in an io.BytesIO buffer.

    Parameters:
        data (array-like): Input data points.

    Returns:
        io.BytesIO: Buffer containing the PNG image.
    """
    # Use only the last 1000 points if data length is greater than 1000
    # if len(data) > 1000:
    #     data = data[-1000:]
    try:
        data = np.array(data, dtype=float)
    except ValueError as e:
        print("Data conversion error:", e)
        raise

    # Create a time axis from 0 to 5 for the truncated data
    x = np.linspace(0, 5, len(data))

    # Create a wide figure (20 inches by 4 inches)
    fig, ax = plt.subplots(figsize=(30, 4))
    ax.plot(x, data, label="Signal")

    # Add vertical dotted lines at x=1, 2, 3, and 4
    for t in range(1, 5):
        ax.axvline(x=t, color="gray", linestyle="--", linewidth=0.8)

    # Customize the plot: grid, labels, and title
    ax.grid(True, which="both", linestyle="-", linewidth=0.5, alpha=0.7)
    ax.set_xlabel("Time")
    ax.set_ylabel("Amplitude")
    # ax.set_title('Amplitude vs. Time (Last 1000 Points)')
    ax.set_xlim(0, 5)

    # Save the plot to an in-memory bytes buffer
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=300, bbox_inches="tight")

    plt.close(fig)
    buf.seek(0)

    return buf
