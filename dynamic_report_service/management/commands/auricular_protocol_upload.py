import os
import pandas as pd
from django.core.management.base import BaseCommand
from dotenv import load_dotenv

# Load environment variables if needed
load_dotenv()

# Import your models – adjust the import paths as needed
from dynamic_report_service.models import AuricularProtocolBank, AuricularReportSystem
from report_service.models import Patterns  # Adjust as needed


class Command(BaseCommand):
    help = "Import ear protocol data from an Excel file and update or create records."

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
            help="Name of the Excel file (e.g., ear_protocols.xlsx).",
        )

    def handle(self, *args, **options):
        data_folder = options["data_folder"]
        excel_filename = options["excel_filename"]
        excel_file = os.path.join(data_folder, excel_filename)

        if not os.path.exists(excel_file):
            self.stdout.write(self.style.ERROR(f"Excel file not found: {excel_file}"))
            return

        try:
            # Read the two sheets from the Excel file
            df_protocol = pd.read_excel(excel_file, sheet_name="Sheet1")
            df_report = pd.read_excel(excel_file, sheet_name="Sheet2")
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error reading Excel file: {e}"))
            return

        self.stdout.write("Sheet1 columns: " + ", ".join(df_protocol.columns))
        self.stdout.write("Sheet2 columns: " + ", ".join(df_report.columns))

        # Process Sheet1 for AuricularProtocolBank
        for idx, row in df_protocol.iterrows():
            protocol_number = row["protocol_number"]
            protocol_text = row["protocol"]
            protocol_notes = row["Comments"]

            # Update or create based on protocol_number
            auricular_instance, created = (
                AuricularProtocolBank.objects.update_or_create(
                    protocol_number=protocol_number,
                    defaults={
                        "protocol": protocol_text,
                        "protocol_notes": protocol_notes,
                    },
                )
            )
            if created:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Created AuricularProtocolBank record for protocol_number {protocol_number}"
                    )
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Updated AuricularProtocolBank record for protocol_number {protocol_number}"
                    )
                )

        # Process Sheet2 for AuricularReportSystem
        for idx, row in df_report.iterrows():
            pattern_number = row["pattern_number"]
            protocols_text = row["protocols"]

            try:
                # Retrieve the related Patterns instance
                pattern_instance = Patterns.objects.get(pattern_number=pattern_number)
            except Patterns.DoesNotExist:
                self.stdout.write(
                    self.style.WARNING(
                        f"Patterns instance with pattern_number {pattern_number} does not exist."
                    )
                )
                continue

            auricular_report, created = AuricularReportSystem.objects.update_or_create(
                report=pattern_instance, defaults={"protocols": protocols_text}
            )
            if created:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Created AuricularReportSystem record for pattern_number {pattern_number}"
                    )
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Updated AuricularReportSystem record for pattern_number {pattern_number}"
                    )
                )
