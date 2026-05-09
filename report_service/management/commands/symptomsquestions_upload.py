import os
import pandas as pd
from django.core.management.base import BaseCommand
from dotenv import load_dotenv

from report_service.models import SymptomsQuestions

# Load environment variables if needed
load_dotenv()

# Import your model – adjust the import path according to your project structure


class Command(BaseCommand):
    help = "Import symptoms questions data from an Excel file and update or create records."

    def add_arguments(self, parser):
        parser.add_argument(
            "--data_folder",
            type=str,
            required=True,
            help="Path to the folder containing the Excel file.",
        )
        parser.add_argument(
            "--excel_filename",
            type=str,
            required=True,
            help="Name of the Excel file (e.g., questions_model.xlsx).",
        )

    def handle(self, *args, **options):
        data_folder = options["data_folder"]
        excel_filename = options["excel_filename"]
        excel_file = os.path.join(data_folder, excel_filename)

        if not os.path.exists(excel_file):
            self.stdout.write(self.style.ERROR(f"Excel file not found: {excel_file}"))
            return

        try:
            # Read the first sheet from the Excel file
            df = pd.read_excel(excel_file, sheet_name="Sheet1")
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error reading Excel file: {e}"))
            return

        self.stdout.write("Excel columns: " + ", ".join(df.columns))

        # Iterate over each row in the DataFrame
        for idx, row in df.iterrows():
            question_number = row["question_number"]
            name = row["element_name"]  # Maps to the model field "name"
            yin_yang = row["yin_yang"]
            organ = row["organ"]
            question_text = row["question"]
            question_kannada = row.get(
                "question_kannada", ""
            )  # Handle missing gracefully

            # Use update_or_create so that existing questions (by question_number) get updated
            question_instance, created = SymptomsQuestions.objects.update_or_create(
                question_number=question_number,
                defaults={
                    "name": name,
                    "yin_yang": yin_yang,
                    "organ": organ,
                    "question": question_text,
                    "question_kannada": question_kannada,
                },
            )
            if created:
                self.stdout.write(
                    self.style.SUCCESS(f"Created question {question_number}: {name}")
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(f"Updated question {question_number}: {name}")
                )


#   python manage.py symptomsquestions_upload --data_folder "C:\Users\basav\Downloads" --excel_filename "questions (2) (2).xlsx"
