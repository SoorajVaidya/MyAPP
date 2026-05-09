import os
import pandas as pd
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from dotenv import load_dotenv

# Load environment variables if needed
load_dotenv()

# Import your models
from dynamic_report_service.models import AcupressureProtocolBank, AcupressureReportSystem
from report_service.models import Patterns  # Adjust the import based on your project structure

class Command(BaseCommand):
    help = "Import acupressure data from Excel and images, updating existing records if they exist."

    def add_arguments(self, parser):
        parser.add_argument(
            '--data_folder',
            type=str,
            required=True,
            help='Path to the folder containing the Excel file (e.g., AcupressureData folder).'
        )
        parser.add_argument(
            '--images_folder',
            type=str,
            required=True,
            help='Path to the folder containing the images.'
        )
        parser.add_argument(
            '--excel_filename',
            type=str,
            default='AcupressureData.xlsx',
            help='Name of the Excel file (default: AcupressureData.xlsx).'
        )

    def handle(self, *args, **options):
        data_folder = options['data_folder']
        images_folder = options['images_folder']
        excel_filename = options['excel_filename']

        # Construct the full path to the Excel file
        excel_file = os.path.join(data_folder, excel_filename)
        if not os.path.exists(excel_file):
            self.stdout.write(self.style.ERROR(f"Excel file not found: {excel_file}"))
            return

        # Read the Excel file with two sheets
        try:
            df_protocol = pd.read_excel(excel_file, sheet_name='Sheet1')
            df_report = pd.read_excel(excel_file, sheet_name='Sheet2')
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error reading Excel file: {e}"))
            return

        # Debug prints for column names
        self.stdout.write("Sheet1 columns: " + ", ".join(df_protocol.columns))
        self.stdout.write("Sheet2 columns: " + ", ".join(df_report.columns))

        # Process Sheet1 for AcupressureProtocolBank
        for idx, row in df_protocol.iterrows():
            protocol_number = row['protocol_number']
            # Column name is 'protocol' as printed in your output
            protocols_text = row['protocol']

            # Use update_or_create so that if the record exists, it will be updated
            protocol_instance, created = AcupressureProtocolBank.objects.update_or_create(
                protocol_number=protocol_number,
                defaults={'protocol': protocols_text}
            )

            # Determine the image filename based on protocol_number (e.g. P1.jpg for protocol_number 1)
            image_filename = f'P{protocol_number}.jpg'
            image_path = os.path.join(images_folder, image_filename)

            if os.path.exists(image_path):
                with open(image_path, 'rb') as img_file:
                    # Save new image file to the instance (this will replace the old one)
                    protocol_instance.base_image_1.save(
                        image_filename, ContentFile(img_file.read()), save=False
                    )
            else:
                self.stdout.write(self.style.WARNING(
                    f"Image not found for protocol_number {protocol_number}: {image_path}"
                ))

            protocol_instance.save()
            if created:
                self.stdout.write(self.style.SUCCESS(
                    f"Created AcupressureProtocolBank record for protocol_number {protocol_number}"
                ))
            else:
                self.stdout.write(self.style.SUCCESS(
                    f"Updated AcupressureProtocolBank record for protocol_number {protocol_number}"
                ))

        # Process Sheet2 for AcupressureReportSystem
        for idx, row in df_report.iterrows():
            pattern_number = row['pattern_number']
            protocols_text = row['protocols']

            try:
                # Retrieve the Patterns instance based on pattern_number
                pattern_instance = Patterns.objects.get(pattern_number=pattern_number)
            except Patterns.DoesNotExist:
                self.stdout.write(self.style.WARNING(
                    f"Patterns instance with pattern_number {pattern_number} does not exist."
                ))
                continue

            # Use update_or_create to update the report record if it already exists
            report_instance, created = AcupressureReportSystem.objects.update_or_create(
                report=pattern_instance,
                defaults={'protocols': protocols_text}
            )
            if created:
                self.stdout.write(self.style.SUCCESS(
                    f"Created AcupressureReportSystem record for pattern_number {pattern_number}"
                ))
            else:
                self.stdout.write(self.style.SUCCESS(
                    f"Updated AcupressureReportSystem record for pattern_number {pattern_number}"
                ))


#  python manage.py acupressure_upload --data_folder "C:\Users\basav\Downloads\Acupressure" --excel_filename "AcupressureData.xlsx" --images_folder "C:\Users\basav\Downloads\Acupressure\images"
