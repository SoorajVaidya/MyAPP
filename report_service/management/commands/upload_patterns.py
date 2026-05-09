import os
import importlib.util
import pandas as pd

# Import openpyxl so pandas can use it.
import openpyxl

from django.core.management.base import BaseCommand, CommandError
from report_service.models import Patterns

# Optionally load environment variables from .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

def safe_str(val, default=""):
    """Convert a value to string; if it is NaN or empty, return default."""
    if pd.isna(val) or (isinstance(val, str) and val.lower() == "nan"):
        return default
    return str(val).strip() or default

def map_five_element(val):
    """
    Map a value to one of the allowed five-element keys.
    Allowed keys: 'wind', 'heat', 'cold', 'dry', 'humid'
    For example, variants like "windy" become "wind" and "high" becomes "heat".
    """
    mapping = {
        'wind': 'wind',
        'windy': 'wind',
        'heat': 'heat',
        'hot': 'heat',
        'high': 'heat',  # Map "high" to "heat"
        'cold': 'cold',
        'dry': 'dry',
        'humid': 'humid',
        'humidity': 'humid'
    }
    return mapping.get(val.lower(), val.lower())

def map_yin_yang(val):
    """
    Map a value to one of the allowed yin_yang keys.
    Allowed keys: 'yin', 'yang'
    """
    mapping = {
        'yin': 'yin',
        'yang': 'yang'
    }
    return mapping.get(val.lower(), val.lower())

class Command(BaseCommand):
    help = (
        "Bulk upload Patterns records from an Excel file with multi-row headers.\n\n"
        "Your file appears to have two header rows. This command reads the file using header=[0,1] so that\n"
        "we get a MultiIndex for the columns. Then it flattens the header by taking the second-level value\n"
        "(if available) or falling back to the first level. Finally, it uses an explicit COLUMN_MAPPING to\n"
        "map column indices (0-indexed) to the model fields:\n\n"
        "  - 'Case No'      : column 0\n"
        "  - 'Primary'      : column 1\n"
        "  - 'Secondary'    : column 2\n"
        "  - 'Tertiary'     : column 3\n"
        "  - 'Yin or Yang'  : column 4\n\n"
        "The pattern name is constructed by concatenating primary, secondary, and tertiary (all lowercased).\n"
        "Records are updated/created based on the numeric 'Case No'.\n\n"
        "Adjust COLUMN_MAPPING below if your file’s structure differs."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            'excel_file',
            type=str,
            help='Path to the Excel file containing the records.'
        )

    def handle(self, *args, **options):
        excel_file = options['excel_file']
        if not os.path.exists(excel_file):
            raise CommandError(f"'{excel_file}' does not exist.")

        # Determine Excel engine.
        engine = "openpyxl" if importlib.util.find_spec("openpyxl") is not None else None
        if engine is None:
            raise CommandError("Missing optional dependency 'openpyxl'. Use pip or conda to install it.")

        try:
            # Read the Excel file with two header rows.
            df = pd.read_excel(excel_file, header=[0,1], engine=engine)
        except Exception as e:
            raise CommandError(f"Error reading Excel file: {e}")

        if df.empty:
            self.stdout.write(self.style.WARNING("The Excel file is empty."))
            return

        # Flatten the MultiIndex columns:
        # Use the second header row if available, otherwise the first.
        df.columns = [col[1] if pd.notna(col[1]) else col[0] for col in df.columns]
        self.stdout.write(self.style.NOTICE("Flattened columns: " + ", ".join(df.columns.astype(str))))
        # Optional: print a preview of the data.
        self.stdout.write(self.style.NOTICE("Data preview (first 5 rows):\n" + df.head(5).to_string()))

        # Now, define explicit mapping from field names to column indices.
        # Adjust these indices based on your file's structure.
        COLUMN_MAPPING = {
            'Case No': 0,      # Column 0: should contain the case number
            'Primary': 1,      # Column 1: primary element (e.g., "Wind", "Dry", etc.)
            'Secondary': 2,    # Column 2: secondary element
            'Tertiary': 3,     # Column 3: tertiary element
            'Yin or Yang': 4   # Column 4: yin/yang value
            # You can add 'Pattern Name' if available or construct it.
        }

        # Create a new DataFrame using only the columns we need.
        try:
            df_mapped = pd.DataFrame({
                field: df.iloc[:, col_index] for field, col_index in COLUMN_MAPPING.items()
            })
        except Exception as e:
            raise CommandError(f"Error mapping columns: {e}")

        self.stdout.write(self.style.NOTICE("Mapped columns: " + ", ".join(df_mapped.columns.astype(str))))
        total_records = len(df_mapped)
        self.stdout.write(self.style.SUCCESS(f"Found {total_records} record(s) in the mapped data."))

        # Process each row.
        for index, row in df_mapped.iterrows():
            try:
                pattern_number = int(safe_str(row.get("Case No")))
            except (ValueError, KeyError, TypeError):
                self.stdout.write(self.style.WARNING(f"Row {index + 2}: Missing or invalid 'Case No'. Skipping record."))
                continue

            # Extract values and apply mapping.
            primary_val = map_five_element(safe_str(row.get('Primary'), ""))
            secondary_val = map_five_element(safe_str(row.get('Secondary'), ""))
            tertiary_val = map_five_element(safe_str(row.get('Tertiary'), ""))
            yin_yang_val = map_yin_yang(safe_str(row.get('Yin or Yang'), ""))

            # Construct pattern name from primary, secondary, tertiary.
            constructed_pattern_name = '-'.join(
                ("Humidity" if part.lower() == "humid" else part.capitalize())
                 for part in [primary_val, secondary_val, tertiary_val] if part
                )

            pattern_name = constructed_pattern_name.replace("Humidity", "Humid")

            # Debug: print extracted values.
            self.stdout.write(self.style.NOTICE(
                f"Row {index+2}: Case No {pattern_number}, Primary: '{primary_val}', Secondary: '{secondary_val}', "
                f"Tertiary: '{tertiary_val}', Yin or Yang: '{yin_yang_val}'"
            ))

            record_data = {
                "pattern_number": pattern_number,
                "pattern_name": pattern_name,
                "primary": primary_val,
                "secondary": secondary_val,
                "tertiary": tertiary_val,
                "yin_yang": yin_yang_val,
                # You can add quaternary/quinary if needed.
            }

            try:
                obj, created = Patterns.objects.update_or_create(
                    pattern_number=pattern_number,
                    defaults=record_data,
                )
                if created:
                    self.stdout.write(self.style.SUCCESS(
                        f"Created Patterns record: '{obj.pattern_name}' ({obj.pattern_number})"
                    ))
                else:
                    self.stdout.write(self.style.SUCCESS(
                        f"Updated Patterns record: '{obj.pattern_name}' ({obj.pattern_number})"
                    ))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error processing row {index + 2} (Case No: {pattern_number}): {e}"))

        self.stdout.write(self.style.SUCCESS("Bulk upload complete."))
