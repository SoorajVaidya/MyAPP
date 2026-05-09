import os
import pandas as pd
from django.core.management.base import BaseCommand
from dotenv import load_dotenv

# Load environment variables if needed
load_dotenv()

# Import your models – adjust the import paths as necessary
from dynamic_report_service.models import SeedtherapyProtocolBank, SeedtherapyReportSystem
from report_service.models import Patterns  # Adjust based on your project structure

class Command(BaseCommand):
    help = "Import seed therapy protocol data from an Excel file and update or create records."

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

    def handle(self, *args, **options):
        data_folder = options['data_folder']
        excel_filename = options['excel_filename']
        excel_file = os.path.join(data_folder, excel_filename)
        
        if not os.path.exists(excel_file):
            self.stdout.write(self.style.ERROR(f"Excel file not found: {excel_file}"))
            return

        try:
            # Read two sheets from the Excel file:
            # Sheet1 should contain columns: protocol_number and protocol
            # Sheet2 should contain columns: pattern_number and protocols
            df_protocol = pd.read_excel(excel_file, sheet_name='Sheet1')
            df_report = pd.read_excel(excel_file, sheet_name='Sheet2')
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error reading Excel file: {e}"))
            return

        self.stdout.write("Sheet1 columns: " + ", ".join(df_protocol.columns))
        self.stdout.write("Sheet2 columns: " + ", ".join(df_report.columns))

        # Process Sheet1 for SeedtherapyProtocolBank
        for idx, row in df_protocol.iterrows():
            protocol_number = row['protocol_number']
            protocols_text = row['protocol']

            # Update or create a record based on protocol_number
            stpb_instance, created = SeedtherapyProtocolBank.objects.update_or_create(
                protocol_number=protocol_number,
                defaults={'protocol': protocols_text}
            )

            if created:
                self.stdout.write(self.style.SUCCESS(
                    f"Created SeedtherapyProtocolBank record for protocol_number {protocol_number}"
                ))
            else:
                self.stdout.write(self.style.SUCCESS(
                    f"Updated SeedtherapyProtocolBank record for protocol_number {protocol_number}"
                ))

        # Process Sheet2 for SeedtherapyReportSystem
        for idx, row in df_report.iterrows():
            pattern_number = row['pattern_number']
            protocols_text = row['protocols']

            try:
                # Retrieve the corresponding Patterns instance
                pattern_instance = Patterns.objects.get(pattern_number=pattern_number)
            except Patterns.DoesNotExist:
                self.stdout.write(self.style.WARNING(
                    f"Patterns instance with pattern_number {pattern_number} does not exist."
                ))
                continue

            st_report_instance, created = SeedtherapyReportSystem.objects.update_or_create(
                report=pattern_instance,
                defaults={'protocols': protocols_text}
            )
            if created:
                self.stdout.write(self.style.SUCCESS(
                    f"Created SeedtherapyReportSystem record for pattern_number {pattern_number}"
                ))
            else:
                self.stdout.write(self.style.SUCCESS(
                    f"Updated SeedtherapyReportSystem record for pattern_number {pattern_number}"
                ))
