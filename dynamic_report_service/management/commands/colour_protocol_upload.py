import os
import pandas as pd
from django.core.management.base import BaseCommand
from dotenv import load_dotenv

# Load environment variables if needed
load_dotenv()

# Import your models – adjust the import paths as needed
from dynamic_report_service.models import ColourProtocolBank, ColourReportSystem
from report_service.models import Patterns  # Adjust if necessary

class Command(BaseCommand):
    help = "Import colour protocol data from an Excel file and update or create records (no images)."

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
            help='Name of the Excel file (e.g. color_protocols.xlsx).'
        )

    def handle(self, *args, **options):
        data_folder = options['data_folder']
        excel_filename = options['excel_filename']
        excel_file = os.path.join(data_folder, excel_filename)
        
        if not os.path.exists(excel_file):
            self.stdout.write(self.style.ERROR(f"Excel file not found: {excel_file}"))
            return

        try:
            # Read two sheets from the Excel file
            df_protocol = pd.read_excel(excel_file, sheet_name='Sheet1')
            df_report = pd.read_excel(excel_file, sheet_name='Sheet2')
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error reading Excel file: {e}"))
            return

        self.stdout.write("Sheet1 columns: " + ", ".join(df_protocol.columns))
        self.stdout.write("Sheet2 columns: " + ", ".join(df_report.columns))

        # Process Sheet1 for ColourProtocolBank
        for idx, row in df_protocol.iterrows():
            protocol_number = row['protocol_number']
            protocols_text = row['protocol']  # assuming the header is 'protocol'
            
            # Update or create a ColourProtocolBank record using protocol_number as the unique key
            cpb_instance, created = ColourProtocolBank.objects.update_or_create(
                protocol_number=protocol_number,
                defaults={'protocol': protocols_text}
            )
            
            if created:
                self.stdout.write(self.style.SUCCESS(
                    f"Created ColourProtocolBank record for protocol_number {protocol_number}"
                ))
            else:
                self.stdout.write(self.style.SUCCESS(
                    f"Updated ColourProtocolBank record for protocol_number {protocol_number}"
                ))

        # Process Sheet2 for ColourReportSystem
        for idx, row in df_report.iterrows():
            pattern_number = row['pattern_number']
            protocols_text = row['protocols']
            
            try:
                # Get the Patterns instance that relates to this report
                pattern_instance = Patterns.objects.get(pattern_number=pattern_number)
            except Patterns.DoesNotExist:
                self.stdout.write(self.style.WARNING(
                    f"Patterns instance with pattern_number {pattern_number} does not exist."
                ))
                continue

            crs_instance, created = ColourReportSystem.objects.update_or_create(
                report=pattern_instance,
                defaults={'protocols': protocols_text}
            )
            
            if created:
                self.stdout.write(self.style.SUCCESS(
                    f"Created ColourReportSystem record for pattern_number {pattern_number}"
                ))
            else:
                self.stdout.write(self.style.SUCCESS(
                    f"Updated ColourReportSystem record for pattern_number {pattern_number}"
                ))
                
                
                
                
#    python manage.py colour_protocol_upload --data_folder "C:\Users\basav\Downloads" --excel_filename "color_protocols.xlsx"