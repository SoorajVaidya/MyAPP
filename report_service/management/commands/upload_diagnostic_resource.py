import os
import json
import glob
from io import BytesIO

from django.core.management.base import BaseCommand, CommandError
from django.core.files import File as DjangoFile
from report_service.models import DiagnosticResource

# Optionally load .env variables (make sure you have python-dotenv installed)
try:
    from dotenv import load_dotenv
    load_dotenv()  # Loads variables from .env into os.environ.
except ImportError:
    pass

class Command(BaseCommand):
    help = (
        "Bulk upload DiagnosticResource records from a parent folder.\n"
        "Each record folder must be named like '1.Wind-Dry-Humidity' where '1' is the pattern_number\n"
        "and 'Wind-Dry-Humidity' is the pattern_name. Inside each record folder, there must be a folder\n"
        "named 'Diagnose' which contains a JSON file 'text.json' with all the text data.\n"
        "Within Diagnose there are subfolders for images. For each image field, the command looks for a file\n"
        "whose name starts with the field name. If found, that file is uploaded; if not, the field is left empty.\n"
        "If a record with the same pattern_number exists, its data will be updated."
    )
    
    def process_text(self, text):
        """
        Replaces every newline character with two newlines.
        For example: "Line 1\nLine 2" becomes "Line 1\n\nLine 2".
        """
        if isinstance(text, str):
            return text.replace("\n", "\n\n")
        return text

    def add_arguments(self, parser):
        parser.add_argument(
            'parent_folder',
            type=str,
            help='Path to the parent folder containing record folders (e.g. "Nadiswara").'
        )

    def handle(self, *args, **options):
        parent_folder = options['parent_folder']
        if not os.path.isdir(parent_folder):
            raise CommandError(f"'{parent_folder}' is not a valid directory.")

        # Each subfolder in the parent folder represents one record.
        record_folders = [
            os.path.join(parent_folder, d)
            for d in os.listdir(parent_folder)
            if os.path.isdir(os.path.join(parent_folder, d))
        ]
        if not record_folders:
            self.stdout.write(self.style.WARNING("No record folders found in the parent folder."))
            return

        self.stdout.write(self.style.SUCCESS(f"Found {len(record_folders)} record folder(s)."))

        # Define the image field names as in your model.
        image_fields = [
            "pulse_pdf_image", "pulse_mobile_image", "pulse_pdf_icon_1","pulse_pdf_icon_2",
            "tridosha_pdf_graph", "tridosha_mobile_graph", "tridosha_pdf_icon_1","tridosha_pdf_icon_2","tridosha_pdf_icon_3", "tridosha_mobile_icon_1",
            "tridosha_mobile_icon_2","tridosha_mobile_icon_2", "tridosha_pdf_sloka_icon_1", "tridosha_pdf_sloka_icon_2"
            "yin_yang_pdf_graph", "yin_yang_mobile_graph",
            "organ_rel_pdf_image", "organ_rel_mobile_image", "organ_rel_pdf_icon1", "organ_rel_mobile_icon1",
            "organ_rel_pdf_icon2", "organ_rel_mobile_icon2", "organ_rel_pdf_icon3", "organ_rel_mobile_icon3",
            "nature_correlation_pdf_image", "nature_correlation_mobile_image",
            "thought_pattern_pdf_image", "thought_pattern_mobile_image",
            "fm_pdf_graph", "fm_mobile_graph", "fm_pdf_icon", "fm_mobile_icon",
            "ai_prediction_pdf_icon1", "ai_prediction_mobile_icon1", "ai_prediction_pdf_icon2", "ai_prediction_mobile_icon2",
            "ai_prediction_pdf_icon3", "ai_prediction_mobile_icon3", "ai_prediction_pdf_icon4", "ai_prediction_mobile_icon4",
            "body_pdf_image", "body_mobile_image",
            # New image fields for dietary_solution, emotional_correction and lifestyle_correction
            "dietary_solution_pdf_icon_1", "dietary_solution_pdf_icon_2", "dietary_solution_pdf_icon_3",
            "dietary_solution_pdf_icon_4", "dietary_solution_pdf_icon_5", "dietary_solution_pdf_icon_6",
            "emotional_lifestyle_correction_pdf_icon_1", "emotional_lifestyle_correction_pdf_icon_2",
            "emotional_lifestyle_correction_pdf_icon_3", "emotional_lifestyle_correction_pdf_icon_4",
        ]

        # Mapping from model image field to subfolder name inside the Diagnose folder.
        image_folder_mapping = {
            "pulse_pdf_image": "pulse_pdf_image",
            "pulse_mobile_image": "pulse_mobile_image",
            "pulse_pdf_icon_1": "pulse_pdf_icon",
            "pulse_pdf_icon_2": "pulse_pdf_icon",
            "pulse_mobile_icon": "pulse_mobile_icon",
            "tridosha_pdf_graph": "tridosha_pdf_graph",
            "tridosha_mobile_graph": "tridosha_mobile_graph",
            "tridosha_pdf_icon_1": "tridosha_pdf_icon",
            "tridosha_pdf_icon_2": "tridosha_pdf_icon",
            "tridosha_pdf_icon_3": "tridosha_pdf_icon",
            "tridosha_pdf_sloka_icon_1": "tridosha_pdf_icon",
            "tridosha_pdf_sloka_icon_2": "tridosha_pdf_icon",
            "tridosha_mobile_icon_1": "tridosha_mobile_icon",
            "tridosha_mobile_icon_2": "tridosha_mobile_icon",
            "tridosha_mobile_icon_3": "tridosha_mobile_icon",
            "yin_yang_pdf_graph": "yin_yang_pdf_graph",
            "yin_yang_mobile_graph": "yin_yang_mobile_graph",
            "organ_rel_pdf_image": "organ_rel",
            "organ_rel_mobile_image": "organ_rel",
            "organ_rel_pdf_icon1": "organ_rel",
            "organ_rel_mobile_icon1": "organ_rel",
            "organ_rel_pdf_icon2": "organ_rel",
            "organ_rel_mobile_icon2": "organ_rel",
            "organ_rel_pdf_icon3": "organ_rel",
            "organ_rel_mobile_icon3": "organ_rel",
            "nature_correlation_pdf_image": "nature_correlation",
            "nature_correlation_mobile_image": "nature_correlation",
            "thought_pattern_pdf_image": "thought_pattern_pdf_image",
            "thought_pattern_mobile_image": "thought_pattern_mobile_image",
            "fm_pdf_graph": "fm_pdf_graph",
            "fm_mobile_graph": "fm_mobile_graph",
            "fm_pdf_icon": "fm_pdf_icon",
            "fm_mobile_icon": "fm_mobile_icon",
            "ai_prediction_pdf_icon1": "ai_prediction",
            "ai_prediction_mobile_icon1": "ai_prediction",
            "ai_prediction_pdf_icon2": "ai_prediction",
            "ai_prediction_mobile_icon2": "ai_prediction",
            "ai_prediction_pdf_icon3": "ai_prediction",
            "ai_prediction_mobile_icon3": "ai_prediction",
            "ai_prediction_pdf_icon4": "ai_prediction",
            "ai_prediction_mobile_icon4": "ai_prediction",
            "body_pdf_image": "body_pdf_image",
            "body_mobile_image": "body_mobile_image",
            # New mappings for the added image fields.
            "dietary_solution_pdf_icon_1": "dietary_solution",
            "dietary_solution_pdf_icon_2": "dietary_solution",
            "dietary_solution_pdf_icon_3": "dietary_solution",
            "dietary_solution_pdf_icon_4": "dietary_solution",
            "dietary_solution_pdf_icon_5": "dietary_solution",
            "dietary_solution_pdf_icon_6": "dietary_solution",
            "emotional_lifestyle_correction_pdf_icon_1": "emotional_lifestyle_correction",
            "emotional_lifestyle_correction_pdf_icon_2": "emotional_lifestyle_correction",
            "emotional_lifestyle_correction_pdf_icon_3": "emotional_lifestyle_correction",
            "emotional_lifestyle_correction_pdf_icon_4": "emotional_lifestyle_correction",
        }

        for record_folder in record_folders:
            folder_name = os.path.basename(record_folder)
            # Expect folder name format: "number.pattern_name"
            if '.' in folder_name:
                parts = folder_name.split('.', 1)
                pattern_number = parts[0].strip()
                pattern_name = parts[1].strip()
            else:
                self.stdout.write(self.style.WARNING(
                    f"Folder name '{folder_name}' does not follow expected format 'number.pattern_name'. Skipping."
                ))
                continue

            self.stdout.write(self.style.NOTICE(f"Processing record: {folder_name}"))
            record_data = {
                "pattern_number": pattern_number,
                "pattern_name": pattern_name,
            }

            # Process the Diagnose folder.
            diagnose_folder = os.path.join(record_folder, "Diagnose")
            if not os.path.isdir(diagnose_folder):
                self.stdout.write(self.style.WARNING(f"'Diagnose' folder not found in {record_folder}. Skipping record."))
                continue

            # Load text data from Diagnose/text.json.
            text_json_path = os.path.join(diagnose_folder, "text.json")
            if not os.path.exists(text_json_path):
                self.stdout.write(self.style.WARNING(f"'text.json' not found in {diagnose_folder}. Skipping record."))
                continue

            try:
                with open(text_json_path, "r", encoding="utf-8") as f:
                    text_data = json.load(f)
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"Error loading JSON from {text_json_path}: {e}. Skipping record."))
                continue

            # Map text JSON data to model fields, processing newlines.
            record_data["pulse_explanation"] = self.process_text(text_data.get("pulse_explanation", ""))
            record_data["tridosha_text_1"] = self.process_text(text_data.get("tridosha_text_1", ""))
            record_data["tridosha_text_2"] = self.process_text(text_data.get("tridosha_text_2", ""))
            record_data["tridosha_text_3"] = self.process_text(text_data.get("tridosha_text_3", ""))
            
            organ_rel = text_data.get("organ_rel", {})
            record_data["organ_rel_text1"] = self.process_text(organ_rel.get("organ_rel_text1", ""))
            record_data["organ_rel_text2"] = self.process_text(organ_rel.get("organ_rel_text2", ""))
            record_data["organ_rel_text3"] = self.process_text(organ_rel.get("organ_rel_text3", ""))
            record_data["organ_rel_text4"] = self.process_text(organ_rel.get("organ_rel_text4", ""))

            record_data["nature_correlation_text"] = self.process_text(text_data.get("nature_correlation_text", ""))
            record_data["thought_pattern_text"] = self.process_text(text_data.get("thought_pattern_text", ""))
            record_data["fm_text"] = self.process_text(text_data.get("fm_text", ""))

            ai_prediction = text_data.get("ai_prediction", {})
            record_data["ai_prediction_text1"] = self.process_text(ai_prediction.get("ai_prediction_text1", ""))
            record_data["ai_prediction_text2"] = self.process_text(ai_prediction.get("ai_prediction_text2", ""))
            record_data["ai_prediction_text3"] = self.process_text(ai_prediction.get("ai_prediction_text3", ""))
            record_data["ai_prediction_text4"] = self.process_text(ai_prediction.get("ai_prediction_text4", ""))
            record_data["ai_prediction_text5"] = self.process_text(ai_prediction.get("ai_prediction_text5", ""))
            record_data["ai_prediction_text6"] = self.process_text(ai_prediction.get("ai_prediction_text6", ""))
            record_data["ai_prediction_text7"] = self.process_text(ai_prediction.get("ai_prediction_text7", ""))
            record_data["ai_prediction_text8"] = self.process_text(ai_prediction.get("ai_prediction_text8", ""))

            # Map new dietary solution, emotional and lifestyle correction fields.
            record_data["body_anotations"] = self.process_text(text_data.get("body_anotations", ""))
            record_data["dietary_solution_1"] = self.process_text(text_data.get("dietary_solution_1", ""))
            record_data["dietary_solution_2"] = self.process_text(text_data.get("dietary_solution_2", ""))
            record_data["dietary_solution_3"] = self.process_text(text_data.get("dietary_solution_3", ""))
            record_data["dietary_solution_4"] = self.process_text(text_data.get("dietary_solution_4", ""))
            record_data["dietary_solution_5"] = self.process_text(text_data.get("dietary_solution_5", ""))
            record_data["dietary_solution_6"] = self.process_text(text_data.get("dietary_solution_6", ""))
            record_data["emotional_lifestyle_correction_1"] = self.process_text(text_data.get("emotional_lifestyle_correction_1", ""))
            record_data["emotional_lifestyle_correction_2"] = self.process_text(text_data.get("emotional_lifestyle_correction_2", ""))
            record_data["emotional_lifestyle_correction_3"] = self.process_text(text_data.get("emotional_lifestyle_correction_3", ""))
            record_data["emotional_lifestyle_correction_4"] = self.process_text(text_data.get("emotional_lifestyle_correction_4", ""))

            # Set defaults for JSON/integer fields.
            record_data.setdefault("tridosha_values", {})
            record_data.setdefault("yin_yang", {})
            record_data.setdefault("fm_values", {})
            record_data.setdefault("heart_rate", None)

            # Process image fields:
            # For each image field, look in the mapped subfolder inside Diagnose for a file that starts with the field name.
            for field in image_fields:
                folder_key = image_folder_mapping.get(field, field)
                image_folder_path = os.path.join(diagnose_folder, folder_key)
                # Use a file pattern that starts with the field name (any extension)
                file_pattern = os.path.join(image_folder_path, f"{field}*")
                matched_files = glob.glob(file_pattern)
                if matched_files:
                    image_file = matched_files[0]  # Use the first matching file
                    try:
                        with open(image_file, "rb") as f:
                            file_content = f.read()
                        record_data[field] = DjangoFile(BytesIO(file_content), name=os.path.basename(image_file))
                        self.stdout.write(self.style.SUCCESS(f"Loaded image for '{field}' from '{image_folder_path}'"))
                    except Exception as e:
                        self.stdout.write(self.style.WARNING(f"Error loading image for '{field}' from '{image_folder_path}': {e}"))
                        record_data[field] = None
                else:
                    self.stdout.write(self.style.WARNING(f"No file found for '{field}' in folder '{image_folder_path}'. Field left empty."))
                    record_data[field] = None

            # Update the record if it exists; otherwise, create a new one.
            try:
                obj, created = DiagnosticResource.objects.update_or_create(
                    pattern_number=record_data["pattern_number"],
                    # pattern_name=record_data["pattern_name"],
                    defaults=record_data,
                )
                if created:
                    self.stdout.write(self.style.SUCCESS(f"Created DiagnosticResource: '{obj.pattern_name}'"))
                else:
                    self.stdout.write(self.style.SUCCESS(f"Updated DiagnosticResource: '{obj.pattern_name}'"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error creating/updating DiagnosticResource for folder {record_folder}: {e}"))

        self.stdout.write(self.style.SUCCESS("Bulk upload complete."))
