import base64
from datetime import datetime, date
from io import BytesIO
import json
import os
import boto3
from botocore.exceptions import ClientError
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.utils.decorators import method_decorator
from django.views.decorators.clickjacking import xframe_options_exempt
from weasyprint import HTML

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

# Assume these models are imported from your app:
# DiagnosisReportHistory, Patterns, DiagnosticResource, UserProfile, PatientsModel

# Assume these helper functions exist and work as expected:
# generate_dosha_chart(vata, pitta, kapha)
# plot_organ_chart(wind_yin, wind_yang, heat_yin, heat_yang, humid_yin, humid_yang, dry_yin, dry_yang, cold_yin, cold_yang)
# plot_diagonal_gradient(carbohydrate, protein, fat)
# highlight_body_parts(body_pdf_image, labels_to_highlight)
# image_url_to_base64(image_url)
# And also assume you have xhtml2pdf's pisa imported:
from xhtml2pdf import pisa

from dynamic_report_service.utils import image_url_to_base64
from dynamic_report_service.views import fetch_resources
from global_utils.plotting_graphs import (
    generate_dosha_chart,
    highlight_body_parts,
    plot_diagonal_gradient,
    plot_organ_chart,
    pulse_image,
)
from patients.models import PatientsModel
from report_service.models import DiagnosisReportHistory, DiagnosticResource, Patterns
from report_service.report_service_handler import generate_treatment_report
from report_service.serliaizers import DiagnosticResourceSerializer
from user_profile.models import UserProfile

# -----------------------------------------------------------------------------
# Helper: Generate PDF for one report type (pattern) using a given report history.
# -----------------------------------------------------------------------------


def convert_bytesio_to_base64(bytesio_obj):
    bytesio_obj.seek(0)
    encoded = base64.b64encode(bytesio_obj.read()).decode("utf-8")
    # Assuming PNG output; adjust the mime type if needed.
    return f"data:image/png;base64,{encoded}"




def generate_pdf_for_pattern(report_history, parameters, user_name, patient_name, patient_age, patient_number):
    """
    Generate a PDF for a given report type by:
      1. Calling generate_treatment_report to get the report data.
      2. Generating charts and processing images.
      3. Updating the report content with the dynamic images.
      4. Rendering HTML and converting it to a PDF using WeasyPrint.
      5. Uploading the PDF to AWS S3 and returning its URL.
    """

    treatment_report = generate_treatment_report(parameters, user_name, patient_name, patient_age, patient_number)
    if treatment_report.get("status") != "success":
        return {"error": treatment_report.get("message"), "pdf_url": None}
    all_context = {"sections": treatment_report.get("data", [])}

    # Generate dynamic charts/images
    dosha_chart = generate_dosha_chart(report_history.vata, report_history.pitta, report_history.kapha)
    yin_yang = plot_organ_chart(
        report_history.wind_yin, report_history.wind_yang,
        report_history.heat_yin, report_history.heat_yang,
        report_history.humid_yin, report_history.humid_yang,
        report_history.dry_yin, report_history.dry_yang,
        report_history.cold_yin, report_history.cold_yang
    )
    food_metabolism = plot_diagonal_gradient(report_history.carbohydrate, report_history.protein, report_history.fat)

    dosha_chart_base64 = convert_bytesio_to_base64(dosha_chart)
    yin_yang_base64 = convert_bytesio_to_base64(yin_yang)
    food_metabolism_base64 = convert_bytesio_to_base64(food_metabolism)

    # Retrieve diagnostic resource for the current report type using an override parameter
    report_type_override = parameters.get("report_type_override", "default")
    diagnostic_resource = DiagnosticResource.objects.filter(pattern_name__icontains=report_type_override).first()

    if diagnostic_resource and diagnostic_resource.body_anotations:
        labels_to_highlight = [label.strip() for label in diagnostic_resource.body_anotations.split(',') if label.strip()]
    else:
        labels_to_highlight = []

    if diagnostic_resource:
        body_image_value = (highlight_body_parts(diagnostic_resource.body_pdf_image, labels_to_highlight)
                            if labels_to_highlight
                            else diagnostic_resource.body_pdf_image)
        if isinstance(body_image_value, str) and not body_image_value.startswith("data:image"):
            body_image_value = image_url_to_base64(body_image_value)
    else:
        body_image_value = ""

    pulse_data = report_history.pulse_id

    if pulse_data and pulse_data.signal_data:
        try:
            pulse_signal_data = json.loads(pulse_data.signal_data)
        except json.JSONDecodeError:
            pulse_signal_data = pulse_data.signal_data
    else:
        pulse_signal_data = []

    if isinstance(pulse_signal_data, str):
        pulse_signal_data = [float(val.strip()) for val in pulse_signal_data.split(",")]
    elif isinstance(pulse_signal_data, list):
        pulse_signal_data = [float(val) for val in pulse_signal_data]

    pulse_image_plot = "https://naadiswara.s3.ap-south-1.amazonaws.com/DiagnosticResource/pdf/1dcf30d393d14de3a230aa3275727107.png"

    # Update context content
    for section in all_context["sections"]:
        for content in section.get("content", []):
            if content.get("title") == "tridosha_pdf_graph":
                content["value"] = dosha_chart_base64
            elif content.get("title") == "yin_yang_pdf_graph":
                content["value"] = yin_yang_base64
            elif content.get("title") == "fm_pdf_graph":
                content["value"] = food_metabolism_base64
            elif content.get("title") == "heart_rate":
                content["value"] = report_history.heart_rate
            elif content.get("title") == "pulse_pdf_image":
                content["value"] = pulse_image_plot
            # You can also add 'body_pdf_image' back here if needed

    # Render HTML
    html_content = render_to_string("diagnostic_resource_weasyprint1.html", all_context)

    pdf_file = BytesIO()

    # Generate PDF using WeasyPrint
    HTML(string=html_content).write_pdf(target=pdf_file)
    pdf_file.seek(0)
    pdf_content = pdf_file.getvalue()

    # Upload PDF to S3
    AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
    AWS_STORAGE_BUCKET_NAME = os.getenv("AWS_STORAGE_BUCKET_NAME")
    AWS_S3_REGION_NAME = os.getenv("AWS_S3_REGION_NAME", "ap-south-1")

    s3_client = boto3.client(
        "s3",
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_S3_REGION_NAME,
    )

    file_name = f"DiagnosticReport_{report_type_override}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"

    try:
        s3_client.put_object(
            Bucket=AWS_STORAGE_BUCKET_NAME,
            Key=f"temp_reports/{file_name}",
            Body=pdf_content,
            ContentType="application/pdf",
        )
        download_url = f"https://{AWS_STORAGE_BUCKET_NAME}.s3.{AWS_S3_REGION_NAME}.amazonaws.com/temp_reports/{file_name}"
        return {"pdf_url": download_url}
    except ClientError as e:
        return {"error": str(e), "pdf_url": None}

# -----------------------------------------------------------------------------
# New API View: BulkPatternReportPDFView
# -----------------------------------------------------------------------------
@method_decorator(xframe_options_exempt, name="dispatch")
class BulkPatternReportPDFView(APIView):
    """
    For a given DiagnosisReportHistory (by report_history_id), this endpoint generates a PDF
    report for each report type (pattern) from your Patterns model. The response is a list
    of objects containing each pattern's identifier and the actual S3 PDF URL.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        report_history_id = request.query_params.get("report_history_id")
        if not report_history_id:
            return Response(
                {"error": "report_history_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            report_history = DiagnosisReportHistory.objects.get(
                report_history_id=report_history_id
            )
        except DiagnosisReportHistory.DoesNotExist:
            return Response(
                {"error": "DiagnosisReportHistory not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Fetch user and patient details (similar to your GenerateDiagnosisReport logic)
        user_profile = UserProfile.objects.filter(
            user_id=report_history.user_id
        ).first()
        user_name = user_profile.user_name if user_profile else "Unknown User"

        patient = PatientsModel.objects.filter(
            first_name=report_history.patient_id
        ).first()
        patient_name = patient.first_name if patient else "Unknown Patient"
        patient_number = patient.phone_number if patient else "Unknown Number"
        if patient and patient.dob:
            dob = patient.dob
            today = date.today()
            patient_age = (
                today.year
                - dob.year
                - ((today.month, today.day) < (dob.month, dob.day))
            )
        else:
            patient_age = "Unknown"

        # Base parameters from the report history
        base_parameters = {
            "primary": report_history.primary,
            "secondary": report_history.secondary,
            "tertiary": report_history.tertiary,
            "quaternary": report_history.quaternary,
            "quinary": report_history.quinary,
        }

        # Check if the 'pattern_numbers' parameter is provided.
        # For example: ?pattern_numbers=1,3,5
        pattern_numbers_param = request.query_params.get("pattern_numbers")
        if pattern_numbers_param:
            # Split and clean the input into a list.
            pattern_numbers = [
                pn.strip() for pn in pattern_numbers_param.split(",") if pn.strip()
            ]
            # Filter patterns based on the provided pattern numbers.
            patterns = Patterns.objects.filter(pattern_number__in=pattern_numbers)
        else:
            patterns = Patterns.objects.all()

        pdf_results = []
        # Loop through all patterns (assumed 60 patterns)
        for pattern in patterns:
            # Copy base parameters and add an override for the report type.
            parameters = base_parameters.copy()
            parameters["report_type_override"] = pattern.pattern_name

            # Generate the PDF for the current pattern.
            pdf_response = generate_pdf_for_pattern(
                report_history,
                parameters,
                user_name,
                patient_name,
                patient_age,
                patient_number,
            )
            pdf_results.append(
                {
                    "pattern_type": pattern.pattern_number,  # or use pattern.id if preferred
                    "pdf_url": pdf_response.get("pdf_url"),
                    "error": pdf_response.get("error"),
                }
            )

        return Response({"pdf_reports": pdf_results}, status=status.HTTP_200_OK)


import base64
import os
from datetime import datetime, date
from io import BytesIO

import boto3
from botocore.exceptions import ClientError
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.utils.decorators import method_decorator
from django.views.decorators.clickjacking import xframe_options_exempt
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from xhtml2pdf import pisa



# Import your chart/image helper functions
# (Ensure these functions are defined elsewhere in your codebase)


#############################################
# Helper to convert a BytesIO image to base64
#############################################
def convert_bytesio_to_base64(bytesio_obj):
    bytesio_obj.seek(0)
    encoded = base64.b64encode(bytesio_obj.read()).decode('utf-8')
    # Assuming the image output is PNG; change mime type if necessary
    return f"data:image/png;base64,{encoded}"

#############################################
# Existing treatment report generator
#############################################
def generate_treatment_report(parameters, user_name=None, patient_name=None, patient_age=None, patient_number=None) -> dict:
    """
    Generate a treatment report by fetching data from the DiagnosticResource model based on predefined patterns.
    """
    if user_name is None:
        user_name = "Unknown User"
    if patient_name is None:
        patient_name = "Unknown Patient"
    if patient_age is None:
        patient_age = "Unknown Age"
    if patient_number is None:
        patient_number = "Unknown Number"

    primary = parameters.get('primary', '').split('_')[0].lower()
    secondary = parameters.get('secondary', '').split('_')[0].lower()
    tertiary = parameters.get('tertiary', '').split('_')[0].lower()
    quaternary = parameters.get('quaternary', '').split('_')[0].lower()
    quinary = parameters.get('quinary', '').split('_')[0].lower()

    report_type = None

    try:
        pattern_instance = Patterns.objects.filter(
            primary__iexact=primary,
            secondary__iexact=secondary,
            tertiary__iexact=tertiary
        ).first()

        if pattern_instance:
            report_type = pattern_instance.pattern_name
        else:
            return {
                "status": "failure",
                "message": "No matching pattern found for the provided primary, secondary, and tertiary values.",
                "data": {}
            }

        

        pattern = DiagnosticResource.objects.filter(
            pattern_name__icontains=report_type
        ).first()

        if pattern:
            response_data = DiagnosticResourceSerializer(pattern).data
            pdf_image_fields = [field for field in response_data.keys() if '_pdf_' in field]

            for key, value in response_data.items():
                if isinstance(value, bytes):
                    response_data[key] = None

            content = []
            for field_name, field_value in response_data.items():
                if field_name == "heart_rate":
                    hr_value = field_value if field_value is not None else "Not provided"
                    content.append({
                        "type": "text",
                        "title": field_name,
                        "value": hr_value
                    })
                    continue
                if field_name in pdf_image_fields:
                    field_type = "image"
                elif field_name not in pdf_image_fields and isinstance(field_value, (str, int, dict, list)):
                    field_type = "text"
                else:
                    continue

                if field_type == "image" and isinstance(field_value, str) and not field_value.startswith("http"):
                    field_value = f"https://{field_value}"

                content.append({
                    "type": field_type,
                    "title": field_name,
                    "value": field_value
                })

            current_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            transformed_response = [{
                "section_name": "Diagnosis Report",
                "section_metadata": {
                    "patient_name": patient_name,
                    "patient_age": patient_age,
                    "user_name": user_name,
                    "patient_number": patient_number,
                    "current_datetime": current_datetime,
                    "id": response_data.get("id"),
                    "pattern_name": response_data.get("pattern_name"),
                    "pattern_number": response_data.get("pattern_number")
                },
                "content": content
            }]

            return {
                "status": "success",
                "message": f"Data available for {report_type}.",
                "data": transformed_response
            }

        return {
            "status": "failure",
            "message": f"No data available for {report_type}.",
            "data": {}
        }
    except Exception as e:
        return {
            "status": "failure",
            "message": f"An error occurred: {str(e)}",
            "data": {}
        }

#############################################
# PDF Generation Helper Function
#############################################


def render_pattern_pdf_bytes(report_history, parameters, user_name, patient_name, patient_age, patient_number):
    """
    Assemble the diagnostic-report PDF and return the raw bytes.

    Pipeline:
      1. Call generate_treatment_report to fetch the structured report data.
      2. Generate dosha / yin-yang / food-metabolism charts from report_history.
      3. Resolve the DiagnosticResource for the requested report_type_override
         and optionally highlight body-image labels.
      4. Inject charts and pulse data into the section context.
      5. Render diagnostic_resource_weasyprint1.html via WeasyPrint and return
         the resulting PDF bytes.

    Contract:
      Returns the PDF bytes on success.
      Raises ValueError when the treatment-report lookup fails (e.g. no matching
      pattern). The async ReportWorker treats exceptions as transient and applies
      its exponential-backoff retry / DLQ policy; the legacy
      generate_pdf_for_pattern() wrapper catches ValueError to preserve its older
      {"pdf_url"/"error"} dict contract for synchronous callers.
    """

    treatment_report = generate_treatment_report(parameters, user_name, patient_name, patient_age, patient_number)
    if treatment_report.get("status") != "success":
        raise ValueError(treatment_report.get("message") or "treatment report failed")
    all_context = {"sections": treatment_report.get("data", [])}

    # Generate dynamic charts/images
    dosha_chart = generate_dosha_chart(report_history.vata, report_history.pitta, report_history.kapha)
    yin_yang = plot_organ_chart(
        report_history.wind_yin, report_history.wind_yang,
        report_history.heat_yin, report_history.heat_yang,
        report_history.humid_yin, report_history.humid_yang,
        report_history.dry_yin, report_history.dry_yang,
        report_history.cold_yin, report_history.cold_yang
    )
    food_metabolism = plot_diagonal_gradient(report_history.carbohydrate, report_history.protein, report_history.fat)

    dosha_chart_base64 = convert_bytesio_to_base64(dosha_chart)
    yin_yang_base64 = convert_bytesio_to_base64(yin_yang)
    food_metabolism_base64 = convert_bytesio_to_base64(food_metabolism)

    # Retrieve diagnostic resource for the current report type using an override parameter
    report_type_override = parameters.get("report_type_override", "default")
    diagnostic_resource = DiagnosticResource.objects.filter(pattern_name__icontains=report_type_override).first()

    if diagnostic_resource and diagnostic_resource.body_anotations:
        labels_to_highlight = [label.strip() for label in diagnostic_resource.body_anotations.split(',') if label.strip()]
    else:
        labels_to_highlight = []

    if diagnostic_resource:
        body_image_value = (highlight_body_parts(diagnostic_resource.body_pdf_image, labels_to_highlight)
                            if labels_to_highlight
                            else diagnostic_resource.body_pdf_image)
        if isinstance(body_image_value, str) and not body_image_value.startswith("data:image"):
            body_image_value = image_url_to_base64(body_image_value)
    else:
        body_image_value = ""

    pulse_data = report_history.pulse_id

    if pulse_data and pulse_data.signal_data:
        try:
            pulse_signal_data = json.loads(pulse_data.signal_data)
        except json.JSONDecodeError:
            pulse_signal_data = pulse_data.signal_data
    else:
        pulse_signal_data = []

    if isinstance(pulse_signal_data, str):
        pulse_signal_data = [float(val.strip()) for val in pulse_signal_data.split(",")]
    elif isinstance(pulse_signal_data, list):
        pulse_signal_data = [float(val) for val in pulse_signal_data]

    pulse_image_plot = "https://naadiswara.s3.ap-south-1.amazonaws.com/DiagnosticResource/pdf/1dcf30d393d14de3a230aa3275727107.png"

    # Update context content
    for section in all_context["sections"]:
        for content in section.get("content", []):
            if content.get("title") == "tridosha_pdf_graph":
                content["value"] = dosha_chart_base64
            elif content.get("title") == "yin_yang_pdf_graph":
                content["value"] = yin_yang_base64
            elif content.get("title") == "fm_pdf_graph":
                content["value"] = food_metabolism_base64
            elif content.get("title") == "heart_rate":
                content["value"] = report_history.heart_rate
            elif content.get("title") == "pulse_pdf_image":
                content["value"] = pulse_image_plot
            # You can also add 'body_pdf_image' back here if needed

    # Render HTML
    html_content = render_to_string("diagnostic_resource_weasyprint1.html", all_context)

    pdf_file = BytesIO()

    # Generate PDF using WeasyPrint
    HTML(string=html_content).write_pdf(target=pdf_file)
    pdf_file.seek(0)
    return pdf_file.getvalue()


def generate_pdf_for_pattern(report_history, parameters, user_name, patient_name, patient_age, patient_number):
    """
    Generate a PDF for a given report type and upload it to AWS S3, returning its URL.

    PDF assembly is delegated to render_pattern_pdf_bytes(); this function keeps its
    original {"pdf_url": ...} / {"error": ...} contract for existing callers, while
    the async pipeline can call render_pattern_pdf_bytes() directly for raw bytes.
    """
    try:
        pdf_content = render_pattern_pdf_bytes(
            report_history, parameters, user_name, patient_name, patient_age, patient_number
        )
    except ValueError as exc:
        return {"error": str(exc), "pdf_url": None}

    report_type_override = parameters.get("report_type_override", "default")

    # Upload PDF to S3
    AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
    AWS_STORAGE_BUCKET_NAME = os.getenv("AWS_STORAGE_BUCKET_NAME")
    AWS_S3_REGION_NAME = os.getenv("AWS_S3_REGION_NAME", "ap-south-1")

    s3_client = boto3.client(
        "s3",
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_S3_REGION_NAME,
    )

    file_name = f"DiagnosticReport_{report_type_override}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"

    try:
        s3_client.put_object(
            Bucket=AWS_STORAGE_BUCKET_NAME,
            Key=f"temp_reports/{file_name}",
            Body=pdf_content,
            ContentType="application/pdf",
        )
        download_url = f"https://{AWS_STORAGE_BUCKET_NAME}.s3.{AWS_S3_REGION_NAME}.amazonaws.com/temp_reports/{file_name}"
        return {"pdf_url": download_url}
    except ClientError as e:
        return {"error": str(e), "pdf_url": None}

#############################################
# Looping Through the 60 Hardcoded Report Types
#############################################
def generate_pdf_reports_for_all_patterns(user_name, patient_name, patient_age, patient_number, report_history):
    """
    Loop through a hardcoded list of 60 report types, generate a PDF for each using generate_pdf_for_pattern,
    and return a list of PDF URLs.
    """
    report_types = [
        "Wind-Humid-Heat",
        "Wind-Humid-Dry",
        "Wind-Humid-Cold",
        "Wind-Heat-Humid",
        "Wind-Heat-Dry",
        "Wind-Heat-Cold",
        "Wind-Dry-Humid",
        "Wind-Dry-Heat",
        "Wind-Dry-Cold",
        "Wind-Cold-Humid",
        "Wind-Cold-Heat",
        "Wind-Cold-Dry",
        "Humid-Wind-Heat",
        "Humid-Wind-Dry",
        "Humid-Wind-Cold",
        "Humid-Heat-Wind",
        "Humid-Heat-Dry",
        "Humid-Heat-Cold",
        "Humid-Dry-Wind",
        "Humid-Dry-Heat",
        "Humid-Dry-Cold",
        "Humid-Cold-Wind",
        "Humid-Cold-Heat",
        "Humid-Cold-Dry",
        "Heat-Wind-Humid",
        "Heat-Wind-Dry",
        "Heat-Wind-Cold",
        "Heat-Humid-Wind",
        "Heat-Humid-Dry",
        "Heat-Humid-Cold",
        "Heat-Dry-Wind",
        "Heat-Dry-Humid",
        "Heat-Dry-Cold",
        "Heat-Cold-Wind",
        "Heat-Cold-Humid",
        "Heat-Cold-Dry",
        "Dry-Wind-Humid",
        "Dry-Wind-Heat",
        "Dry-Wind-Cold",
        "Dry-Humid-Wind",
        "Dry-Humid-Heat",
        "Dry-Humid-Cold",
        "Dry-Heat-Wind",
        "Dry-Heat-Humid",
        "Dry-Heat-Cold",
        "Dry-Cold-Wind",
        "Dry-Cold-Humid",
        "Dry-Cold-Heat",
        "Cold-Wind-Humid",
        "Cold-Wind-Heat",
        "Cold-Wind-Dry",
        "Cold-Humid-Wind",
        "Cold-Humid-Heat",
        "Cold-Humid-Dry",
        "Cold-Heat-Wind",
        "Cold-Heat-Humid",
        "Cold-Heat-Dry",
        "Cold-Dry-Wind",
        "Cold-Dry-Humid",
        "Cold-Dry-Heat"
    ]
    pdf_reports = []
    for rt in report_types:
        parts = rt.split("-")
        params = {
            "primary": parts[0],
            "secondary": parts[1],
            "tertiary": parts[2],
            "quaternary": "",
            "quinary": ""
        }
        # Add an override so the PDF filename reflects the current report type.
        params['report_type_override'] = rt
        result = generate_pdf_for_pattern(report_history, params, user_name, patient_name, patient_age, patient_number)
        pdf_reports.append({
            "report_type": rt,
            "pdf_url": result.get("pdf_url"),
            "error": result.get("error")
        })
    return pdf_reports

#############################################
# API Endpoint: BulkPDFReportsView
#############################################
@method_decorator(xframe_options_exempt, name="dispatch")
class BulkPDFReportsView(APIView):
    """
    API endpoint to generate PDF reports for a given DiagnosisReportHistory instance
    for all 60 hardcoded report types, and return the PDF URLs.
    """
    def get(self, request):
        report_history_id = request.query_params.get("report_history_id")
        if not report_history_id:
            return Response({"error": "report_history_id is required."}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            report_history = DiagnosisReportHistory.objects.get(report_history_id=report_history_id)
        except DiagnosisReportHistory.DoesNotExist:
            return Response({"error": "DiagnosisReportHistory not found."}, status=status.HTTP_404_NOT_FOUND)
        
        # Fetch user details
        user_profile = UserProfile.objects.filter(user_id=report_history.user_id).first()
        user_name = user_profile.user_name if user_profile else "Unknown User"
        
        # Fetch patient details
        patient = PatientsModel.objects.filter(first_name=report_history.patient_id).first()
        patient_name = patient.first_name if patient else "Unknown Patient"
        patient_number = patient.phone_number if patient else "Unknown Number"
        if patient and patient.dob:
            dob = patient.dob
            today = date.today()
            patient_age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        else:
            patient_age = "Unknown"
        
        pdf_reports = generate_pdf_reports_for_all_patterns(user_name, patient_name, patient_age, patient_number, report_history)
        return Response({"pdf_reports": pdf_reports}, status=status.HTTP_200_OK)
