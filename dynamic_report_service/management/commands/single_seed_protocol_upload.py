import os
import pandas as pd
from django.core.management.base import BaseCommand
from django.core.files.base import ContentFile
from dotenv import load_dotenv

from dynamic_report_service.models import SingleSeedProtocolBank

# Load environment variables if needed
load_dotenv()

# Import your SingleSeedProtocolBank model – adjust the path as needed

class Command(BaseCommand):
    help = ("Import Single Seed protocol data from an Excel file and image folder. "
            "Deletes all previous records and assigns protocol_number sequentially.")

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
            help='Name of the Excel file (e.g., Multi_Seed_Protocol.xlsx).'
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
            # Read the Excel file from Sheet1.
            df = pd.read_excel(excel_file, sheet_name='Sheet1')
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error reading Excel file: {e}"))
            return

        self.stdout.write("Excel columns: " + ", ".join(df.columns))

        # Delete all previous records
        SingleSeedProtocolBank.objects.all().delete()
        self.stdout.write(self.style.SUCCESS("Deleted all existing SingleSeedProtocolBank records."))

        # Initialize protocol_number counter starting at 1.
        protocol_counter = 1

        # Process each row in the Excel file.
        for idx, row in df.iterrows():
            organ_value = row['organ']
            yin_yang_value = row['yin_yang']
            points_str = row['points']  # e.g., "Liv1T,Li4S, K10T,Lu7T,Si5S,St42S,Liv4S"

            # Split the points string into individual points, removing extra whitespace.
            points_list = [p.strip() for p in points_str.split(',') if p.strip()]

            for point in points_list:
                # Create a new record with a sequential protocol_number.
                single_seed_instance = SingleSeedProtocolBank.objects.create(
                    protocol_number=protocol_counter,
                    protocol=point,
                    organ=organ_value,
                    yin_yang=yin_yang_value
                )

                # Attach an image file if available (image filename is assumed to be {point}.jpg).
                image_filename = f"{point}.jpg"
                image_path = os.path.join(images_folder, image_filename)
                if os.path.exists(image_path):
                    with open(image_path, 'rb') as img_file:
                        single_seed_instance.base_image_1.save(
                            image_filename,
                            ContentFile(img_file.read()),
                            save=False
                        )
                else:
                    self.stdout.write(self.style.WARNING(
                        f"Image not found for point '{point}' at path: {image_path}"
                    ))

                single_seed_instance.save()
                self.stdout.write(self.style.SUCCESS(
                    f"Created record: protocol_number {protocol_counter}, protocol '{point}', organ '{organ_value}', yin_yang '{yin_yang_value}'"
                ))
                protocol_counter += 1


#   python manage.py single_seed_protocol_upload --data_folder "C:\Users\basav\Downloads\" --excel_filename "single_seed.xlsx" --images_folder "C:\Users\basav\Downloads\SINGLE SEED\JPEG"