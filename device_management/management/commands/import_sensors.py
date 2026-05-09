from django.core.management.base import BaseCommand
import pandas as pd
from device_management.models import FactorySenorList  # Adjust this import based on your app name

class Command(BaseCommand):
    help = 'Import sensor unique_id values from an Excel file'

    def add_arguments(self, parser):
        parser.add_argument('excel_file', type=str, help='Path to the Excel file')

    def handle(self, *args, **options):
        file_path = options['excel_file']
        df = pd.read_excel(file_path)
        
        for index, row in df.iterrows():
            device_id = row.get("Device id")
            if pd.isna(device_id):
                continue

            if not FactorySenorList.objects.filter(unique_id=device_id).exists():
                FactorySenorList.objects.create(unique_id=device_id)
                self.stdout.write(self.style.SUCCESS(f"Inserted sensor with unique_id: {device_id}"))
            else:
                self.stdout.write(self.style.WARNING(f"Sensor with unique_id {device_id} already exists. Skipping."))



# python manage.py import_sensors "C:\Users\basav\Downloads\Book1.xlsx"   