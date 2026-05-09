import json
import re
from b2sdk.v1 import *
import os
from dotenv import load_dotenv
import numpy as np
import pandas as pd
from patients.models import PatientsModel
from user_profile.models import UserProfile
from .models import PulseData
from rest_framework.test import APIRequestFactory, force_authenticate
from django.apps import apps

# Load .env file
load_dotenv()


def valid_pulse(signal_data):
    # Temporary implementation
    return True


def upload_to_backblaze(photo, filename):
    # Your Backblaze B2 credentials
    B2_ACCOUNT_ID = os.getenv("B2_ACCOUNT_ID")
    B2_APPLICATION_KEY = os.getenv("B2_APPLICATION_KEY")
    B2_BUCKET_NAME = os.getenv("B2_BUCKET_NAME")
    B2_ENDPOINT = os.getenv("B2_ENDPOINT")

    # Initialize the B2 API
    info = InMemoryAccountInfo()
    b2_api = B2Api(info)
    b2_api.authorize_account("production", B2_ACCOUNT_ID, B2_APPLICATION_KEY)

    # Get the bucket
    bucket = b2_api.get_bucket_by_name(B2_BUCKET_NAME)

    # Read the file data directly from the InMemoryUploadedFile object
    file_data = photo.read()  # Read the file data

    # Sanitize and construct the correct file path
    file_name = filename.strip("/")  # Remove any leading slashes
    file_path = f"pulse_data/{file_name}"  # Define a subfolder inside the bucket

    # Upload the bytes to Backblaze B2 directly from the file data
    bucket.upload_bytes(file_data, file_path)

    # Ensure the correct URL format for Backblaze
    pulse_uri = f"{B2_ENDPOINT}/file/{B2_BUCKET_NAME}/{file_path}".replace("\\", "/")

    # Ensure that the URL has the proper 'https://' format if missing
    if not pulse_uri.startswith("https://"):
        pulse_uri = "https://" + pulse_uri

    return pulse_uri


def save_pulse_data_in_db(pulse_uri, patient, user_profile):
    """
    Save pulse data in the database.
    """
    pulse = PulseData.objects.create(
        pulse_uri=pulse_uri,
        patient=patient,
        user=user_profile,  # Link pulse data to the authenticated user's profile
    )
    return pulse


def Question_Based(primary, secondary, tertiary):
    # print(71)
    # Replace with your actual file path
    yin_yang_text_path = "pulse_analysis_algo/VPT_Yin_Yang.txt"
    with open(yin_yang_text_path, "r") as file:
        VPK = json.load(file)

    # Remove any percentage parts from the input strings.
    def remove_percentage(value):
        # Updated regex: optionally match a minus sign as well.
        return re.sub(r"_-?\d+(\.\d+)?%", "", value)

    # Clean inputs
    norm_primary = remove_percentage(primary)
    norm_secondary = remove_percentage(secondary)
    norm_tertiary = remove_percentage(tertiary)

    # Build normalized key from the cleaned inputs (e.g., "Wind_Heat_Cold")
    normalized_key = f"{norm_primary}_{norm_secondary}_{norm_tertiary}"

    # First, try to see if the normalized key exists in VPK.
    PST = normalized_key
    if PST not in VPK:
        # Iterate over the keys in VPK and normalize them using the same regex.
        for key in VPK.keys():
            key_normalized = re.sub(r"_-?\d+(\.\d+)?%", "", key)
            if key_normalized == normalized_key:
                PST = key
                break

    # If we still can't find a matching key, raise an error.
    if PST not in VPK:
        raise ValueError(
            f"Key '{normalized_key}' not found in VPT_Yin_Yang.txt. "
            f"Available keys: {list(VPK.keys())}"
        )

    # Create the mapping DataFrame.
    Mapping = pd.DataFrame()
    Mapping.loc[0, "Primary"] = norm_primary
    Mapping.loc[0, "Secondary"] = norm_secondary
    Mapping.loc[0, "Tertiary"] = norm_tertiary
    Mapping.loc[0, "Quaternary"] = np.nan
    Mapping.loc[0, "Quinary"] = np.nan

    # Fill in additional data from the JSON file.
    for k, v in VPK[PST].items():
        Mapping.loc[0, k] = v

    # Prepare a set for nutritional condition checks.
    row_set = {norm_primary, norm_secondary, norm_tertiary}

    # Define condition sets.
    carb_low = {"Humid", "Cold", "Dry"}
    carb_high = {"Humid", "Heat", "Wind"}
    protein_low = {"Cold", "Humid", "Dry"}
    protein_high = {"Cold", "Heat", "Humid"}
    fat_low = {"Wind", "Dry", "Cold"}
    fat_high = {"Humid", "Heat"}

    # Assign nutritional values based on conditions.
    Mapping.loc[0, "Carbohydrate"] = (
        "Low"
        if carb_low.issubset(row_set)
        else "High" if carb_high.issubset(row_set) else "Medium"
    )
    Mapping.loc[0, "Protein"] = (
        "Low"
        if protein_low.issubset(row_set)
        else "High" if protein_high.issubset(row_set) else "Medium"
    )
    Mapping.loc[0, "Fat"] = (
        "Low"
        if fat_low.issubset(row_set)
        else "High" if fat_high.issubset(row_set) else "Medium"
    )

    return Mapping

def format_percent(value):
    try:
        if isinstance(value, str) and value.endswith('%'):
            return value.strip()
        elif isinstance(value, (int, float)):
            return f"{round(value, 2)}%"
        else:
            return str(value)
    except:
        return "0.0%"

def insert_processed_report_id(report_history_id, Mapping, seed_organ, seed_yinyang):
    # print(151)
    """
    Updates the DiagnosisReportHistory instance with fields from the Mapping DataFrame.
    The Mapping DataFrame is expected to have one row with columns:
      - Primary, Secondary, Tertiary, Quaternary, Quinary,
      - Wind_Yin, Wind_Yang, Heat_Yin, Heat_Yang, Humid_Yin, Humid_Yang,
      - Dry_Yin, Dry_Yang, Cold_Yin, Cold_Yang, VATA, PITTA, KAPHA,
      - Carbohydrate, Protein, Fat

    This function updates the corresponding fields in the model, sets processed=1,
    and updates the report_pattern_type by matching a Patterns instance with the given
    primary, secondary, and tertiary values.

    Parameters:
        report_history_id (int): The ID of the DiagnosisReportHistory instance to update.
        Mapping (pd.DataFrame): A pandas DataFrame containing the mapping data (1 row).

    Returns:
        DiagnosisReportHistory: The updated instance.
    """
    # Dynamically load models to avoid circular import issues.
    DiagnosisReportHistory = apps.get_model("report_service", "DiagnosisReportHistory")
    Patterns = apps.get_model("report_service", "Patterns")

    # Retrieve the original instance for copying some values.
    original_instance = DiagnosisReportHistory.objects.get(
        report_history_id=report_history_id
    )

    # Look up a matching Patterns instance based on the new pulse fields.
    pattern_instance = Patterns.objects.filter(
        primary=Mapping.loc[0, "Primary"],
        secondary=Mapping.loc[0, "Secondary"],
        tertiary=Mapping.loc[0, "Tertiary"],
    ).first()

    # Create a new DiagnosisReportHistory record with updated values.
    # print(198)
    new_instance = DiagnosisReportHistory.objects.create(
        user_id=original_instance.user_id,
        patient_id=original_instance.patient_id,
        pulse_id=original_instance.pulse_id,
        report_pattern_type=pattern_instance,
        primary=Mapping.loc[0, "Primary"],
        secondary=Mapping.loc[0, "Secondary"],
        tertiary=Mapping.loc[0, "Tertiary"],
        quaternary=Mapping.loc[0, "Quaternary"],
        quinary=Mapping.loc[0, "Quinary"],
        carbohydrate=Mapping.loc[0, "Carbohydrate"],
        protein=Mapping.loc[0, "Protein"],
        fat=Mapping.loc[0, "Fat"],
        wind_yin=Mapping.loc[0, "Wind_Yin"],
        wind_yang=Mapping.loc[0, "Wind_Yang"],
        heat_yin=Mapping.loc[0, "Heat_Yin"],
        heat_yang=Mapping.loc[0, "Heat_Yang"],
        humid_yin=Mapping.loc[0, "Humid_Yin"],
        humid_yang=Mapping.loc[0, "Humid_Yang"],
        dry_yin=Mapping.loc[0, "Dry_Yin"],
        dry_yang=Mapping.loc[0, "Dry_Yang"],
        cold_yin=Mapping.loc[0, "Cold_Yin"],
        cold_yang=Mapping.loc[0, "Cold_Yang"],
        vata=format_percent(Mapping.loc[0, "VATA"]),
        pitta=format_percent(Mapping.loc[0, "PITTA"]),
        kapha=format_percent(Mapping.loc[0, "KAPHA"]),

        # Update seed fields with Organ and Yin_Yang from the Mapping.
        seed_organ=seed_organ,
        seed_yin_yang=seed_yinyang,
        # Mark the report as processed.
        processed=report_history_id,
    )
    # print(232)
    return new_instance


def insert_processed_report_id1(report_history_id, Mapping, seed_organ, seed_yinyang):
    from django.apps import apps

    DiagnosisReportHistory = apps.get_model("report_service", "DiagnosisReportHistory")
    Patterns = apps.get_model("report_service", "Patterns")

    # Fetch the original instance
    original_instance = DiagnosisReportHistory.objects.get(report_history_id=report_history_id)

    # Get matching pattern instance
    pattern_instance = Patterns.objects.filter(
        primary=Mapping.loc[0, "Primary"],
        secondary=Mapping.loc[0, "Secondary"],
        tertiary=Mapping.loc[0, "Tertiary"],
    ).first()

    # Copy all fields except ID and explicitly overridden ones
    new_data = {
        field.name: getattr(original_instance, field.name)
        for field in DiagnosisReportHistory._meta.fields
        if field.name not in ["id", "report_history_id", "report_pattern_type", "primary", "secondary", "tertiary", "processed"]
    }

    # Add overridden fields
    new_data.update({
        "primary": Mapping.loc[0, "Primary"],
        "secondary": Mapping.loc[0, "Secondary"],
        "tertiary": Mapping.loc[0, "Tertiary"],
        "report_pattern_type": pattern_instance,
        "processed": report_history_id,
        "seed_organ": seed_organ,
        "seed_yin_yang": seed_yinyang,
    })

    # Create new instance (Django auto-generates new ID and report_history_id)
    new_instance = DiagnosisReportHistory.objects.create(**new_data)
    return new_instance


def rearrange_five_elements(report_history_id, answers, user):
    """
    Calls ChangePatternAPIView to get the pulse mapping based on the provided report_history_id
    and answers, then rearranges the mapping into a dictionary containing only primary, secondary,
    and tertiary values. The quaternary and quinary elements are set to empty strings.

    This function does not modify the database.

    Parameters:
        report_history_id (int): The DiagnosisReportHistory ID.
        answers (dict): The answers payload expected by ChangePatternAPIView (e.g., must include a key like 'cycle_1').
        user (User): The user instance for request authentication.

    Returns:
        dict: A dictionary with keys 'primary', 'secondary', 'tertiary', 'quaternary', 'quinary'.
              Example:
              {
                  "primary": "Heat",
                  "secondary": "Wind",
                  "tertiary": "Dry",
                  "quaternary": "",
                  "quinary": ""
              }
    """
    # Local import to avoid circular import issues.
    from pulse_service.views import (
        ChangePatternAPIView,
    )  # Adjust the import path if necessary

    factory = APIRequestFactory()
    request_data = {
        "report_history_id": report_history_id,
        "answers": answers,
    }
    request_obj = factory.post("/change-pattern/", request_data, format="json")
    force_authenticate(request_obj, user=user)

    # Call ChangePatternAPIView internally
    response = ChangePatternAPIView.as_view()(request_obj)

    # Check for success; otherwise, return empty mapping.
    if response.status_code != 200:
        return {
            "primary": "",
            "secondary": "",
            "tertiary": "",
            "quaternary": "",
            "quinary": "",
            "Organ": "",
            "Yin_Yang": "",
        }

    # Extract the pulse mapping from the nested response structure.
    pulse_mapping = response.data.get("data", {}).get("pulse_mapping", {})
    data = response.data.get("data", {})

    rearranged = {
        "primary": pulse_mapping.get("primary", ""),
        "secondary": pulse_mapping.get("secondary", ""),
        "tertiary": pulse_mapping.get("tertiary", ""),
        "quaternary": "",
        "quinary": "",
        "Organ": data.get("Organ", ""),
        "Yin_Yang": data.get("Yin_Yang", ""),
    }

    return rearranged


def deduct_from_wallet(request, pulse_id, patient_id, report_history_id):
    """
    Calls DeductFromWalletAPIView and returns its response.
    """
    factory = APIRequestFactory()
    wallet_data = {
        "service_name_or_id": "Diagnosis Report",
        "pulse_id": pulse_id,
        "patient_id": patient_id,
        "report_history_id": report_history_id,
    }
    wallet_request = factory.post("/deduct-wallet/", wallet_data, format="json")
    wallet_request.is_superuser = request.user.is_superuser
    force_authenticate(wallet_request, user=request.user)

    from pulse_service.views import (
        DeductFromWalletAPIView,
    )  # Local import to avoid circular issues

    wallet_response = DeductFromWalletAPIView.as_view()(wallet_request)
    return wallet_response


def generate_diagnosis_report(request, report_history_id, answers):
    """
    Calls GenerateDiagnosisReport and returns its response.
    """
    factory = APIRequestFactory()
    diagnosis_params = {
        "regenerate": True,
        "report_history_id": report_history_id,
        "answers": answers,
    }
    diagnosis_request = factory.get(
        "/generate-diagnosis-report/", data=diagnosis_params
    )
    force_authenticate(diagnosis_request, user=request.user)

    from pulse_service.views import GenerateDiagnosisReport  # Local import

    diagnosis_response = GenerateDiagnosisReport.as_view()(diagnosis_request)
    return diagnosis_response


def generate_report_pdf(request, report_history_id, language):
    """
    Calls ReportPDFView and returns its response.
    This call is placed at the end.
    """
    factory = APIRequestFactory()
    pdf_params = {
        "report_history_id": report_history_id,
        "language": language,
    }
    pdf_request = factory.get("/download-diagnosis-report/", data=pdf_params)
    force_authenticate(pdf_request, user=request.user)

    from pulse_service.views import ReportPDFView  # Local import

    pdf_response = ReportPDFView.as_view()(pdf_request)
    return pdf_response


def get_service_list(request):
    """
    Calls ServiceListAPIView and returns its response.
    """
    factory = APIRequestFactory()
    service_request = factory.get("/services/")
    force_authenticate(service_request, user=request.user)

    from pulse_service.views import ServiceListAPIView  # Local import

    service_response = ServiceListAPIView.as_view()(service_request)
    return service_response
