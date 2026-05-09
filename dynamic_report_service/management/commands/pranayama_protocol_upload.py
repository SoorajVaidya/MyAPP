import os
import pandas as pd
from django.core.management.base import BaseCommand
from django.core.files.base import ContentFile
from dotenv import load_dotenv

# Load environment variables if needed
load_dotenv()

# Import your models – adjust the import paths as necessary
from dynamic_report_service.models import PranayamaProtocolBank, PranayamaReportSystem
from report_service.models import Patterns  # Adjust if necessary

class Command(BaseCommand):
    help = ("Import Pranayama protocol data from an Excel file and image folder. "
            "Updates or creates PranayamaProtocolBank and PranayamaReportSystem records.")

    def add_arguments(self, parser):
        parser.add_argument(
            '--data_folder',
            type=str,
            required=True,
            help='Path to the folder containing the Excel file.'
        )
        parser.add_argument(
            '--excel_filename',
            type=str,
            required=True,
            help='Name of the Excel file (e.g., Pranayama_Protocols.xlsx).'
        )
        parser.add_argument(
            '--images_folder',
            type=str,
            required=True,
            help='Path to the folder containing the images.'
        )

    def handle(self, *args, **options):
        data_folder = options['data_folder']
        excel_filename = options['excel_filename']
        images_folder = options['images_folder']
        excel_file = os.path.join(data_folder, excel_filename)

        if not os.path.exists(excel_file):
            self.stdout.write(self.style.ERROR(f"Excel file not found: {excel_file}"))
            return

        try:
            # Read the Excel file: Sheet1 for protocols, Sheet2 for reports.
            df_protocol = pd.read_excel(excel_file, sheet_name='Sheet1')
            df_report = pd.read_excel(excel_file, sheet_name='Sheet2')
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error reading Excel file: {e}"))
            return

        self.stdout.write("Sheet1 columns: " + ", ".join(df_protocol.columns))
        self.stdout.write("Sheet2 columns: " + ", ".join(df_report.columns))

        # Process Sheet1: update or create PranayamaProtocolBank records.
        for idx, row in df_protocol.iterrows():
            protocol_number = row['protocol_number']
            protocols_text = row['protocols']

            Pranayama_instance, created = PranayamaProtocolBank.objects.update_or_create(
                protocol_number=protocol_number,
                defaults={'protocol': protocols_text}
            )

            # For Pranayama, image file names are simple numbers, e.g. "1.jpg", "2.jpg", etc.
            image_filename = f"{protocol_number}.jpg"
            image_path = os.path.join(images_folder, image_filename)
            if os.path.exists(image_path):
                with open(image_path, 'rb') as img_file:
                    Pranayama_instance.base_image_1.save(
                        image_filename,
                        ContentFile(img_file.read()),
                        save=False
                    )
            else:
                self.stdout.write(self.style.WARNING(
                    f"Image not found for protocol_number {protocol_number}: {image_path}"
                ))
            Pranayama_instance.save()
            if created:
                self.stdout.write(self.style.SUCCESS(
                    f"Created PranayamaProtocolBank record for protocol_number {protocol_number}"
                ))
            else:
                self.stdout.write(self.style.SUCCESS(
                    f"Updated PranayamaProtocolBank record for protocol_number {protocol_number}"
                ))

        # Process Sheet2: update or create PranayamaReportSystem records.
        for idx, row in df_report.iterrows():
            pattern_number = row['pattern_number']
            protocols_text = row['protocols']

            try:
                pattern_instance = Patterns.objects.get(pattern_number=pattern_number)
            except Patterns.DoesNotExist:
                self.stdout.write(self.style.WARNING(
                    f"Patterns instance with pattern_number {pattern_number} does not exist."
                ))
                continue

            Pranayama_report, created = PranayamaReportSystem.objects.update_or_create(
                report=pattern_instance,
                defaults={'protocols': protocols_text}
            )
            if created:
                self.stdout.write(self.style.SUCCESS(
                    f"Created PranayamaReportSystem record for pattern_number {pattern_number}"
                ))
            else:
                self.stdout.write(self.style.SUCCESS(
                    f"Updated PranayamaReportSystem record for pattern_number {pattern_number}"
                ))



#    python manage.py Pranayama_protocol_upload --data_folder "C:\Users\basav\Downloads\" --excel_filename "asana_protocols.xlsx" --images_folder "C:\Users\basav\Downloads\ASANAS_Images\ASANAS\ASANAS jpeg"