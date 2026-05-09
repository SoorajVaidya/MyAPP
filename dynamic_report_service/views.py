import os
from datetime import datetime
from io import BytesIO
import json
import boto3
from botocore.exceptions import ClientError
from django.db import transaction
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.utils.decorators import method_decorator
from django.views.decorators.clickjacking import xframe_options_exempt
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView
from sqlalchemy import null
from xhtml2pdf import pisa
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import base64
from pypdf import PdfReader, PdfWriter
from django.utils.text import slugify
from weasyprint import HTML

from dynamic_report_service.treatementReportAPIs import (
    generate_acupressure_report,
    generate_auricular_report,
    generate_mudra_report,
    generate_pranayama_report,
    generate_single_seed_report,
    generate_yoga_report,
    generate_colour_report,
    generate_multi_seed_report,
)
from global_utils.plotting_graphs import (
    generate_dosha_chart,
    highlight_body_parts,
    plot_diagonal_gradient,
    plot_organ_chart,
    pulse_image,
)
from global_utils.service_treatments_map import (
    SERVICE_TREATMENT_MAP,
    food_metabolism_map,
)
from oohy_product import settings
from oohy_product.custom_responses import ErrorResponse, StandardResponse
from pulse_payments.models import Service
from pulse_payments.views import DeductFromWalletAPIView
from report_service.models import DiagnosisReportHistory, DiagnosticResource
from report_service.views import GenerateDiagnosisReport
from .utils import image_url_to_base64
from django.contrib.staticfiles import finders


# Custom callback to resolve static files
def fetch_resources(uri, rel):
    if uri.startswith(settings.STATIC_URL):
        path = finders.find(uri.replace(settings.STATIC_URL, ""))
        if path:
            return path
    return uri


class PurchaseTreatmentReport(APIView):
    """
    API endpoint to purchase a treatment service for a diagnosis report.
    """

    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        # Step 1: Extract `report_history_id` and `service_id` from the request.
        report_history_id = request.data.get("report_history_id")
        service_id = request.data.get("service_id")

        # Step 2: Validate if `report_history_id` and `service_id` are provided.
        if not report_history_id or not service_id:
            return ErrorResponse(
                errors={
                    "message": "Both report_history_id and service_id are required."
                },
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # Step 3: Fetch the DiagnosisReportHistory object using `report_history_id`.
        try:
            diagnosis_report = get_object_or_404(
                DiagnosisReportHistory, report_history_id=report_history_id
            )
        except Exception as e:
            return ErrorResponse(
                errors={"message": f"Invalid report_history_id: {e}"},
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # Step 4: Validate if the `service_id` exists in the SERVICE_TREATMENT_MAP.
        try:
            service = Service.objects.get(service_id=service_id)
        except Service.DoesNotExist:
            return ErrorResponse(
                errors={"message": f"Invalid service_id: {service_id}"},
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # Step 5: Check if the treatment for the service already exists.
        treatment_field = SERVICE_TREATMENT_MAP.get(str(service_id))
        if treatment_field and getattr(diagnosis_report, treatment_field, None):
            return ErrorResponse(
                errors={
                    "message": f"{service.name} has already been purchased for this report."
                },
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # Step 6: Deduct the service price from the user's wallet.
        try:
            deduction_request_data = {
                "service_name_or_id": service_id,
                "patient_id": (
                    diagnosis_report.patient_id.id
                    if hasattr(diagnosis_report.patient_id, "id")
                    else diagnosis_report.patient_id
                ),
                "report_history_id": report_history_id,
            }

            deduction_request = request._request
            deduction_request.data = deduction_request_data
            wallet_deduction_response = DeductFromWalletAPIView().post(
                deduction_request
            )

            if wallet_deduction_response.status_code != status.HTTP_200_OK:
                return wallet_deduction_response

        except Exception as e:
            return ErrorResponse(
                errors={"message": f"Error deducting wallet balance: {e}"},
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Step 7: Call GenerateTreatmentReport directly for the respective service.
        try:

            # Create a request with the same user from the original request
            rf = APIRequestFactory()
            wsgi_request = rf.get(
                "/api/v1/dynamic-report-service/generate-treatment-report/",
                {"report_history_id": report_history_id, "service_id": service_id},
            )
            wsgi_request.user = (
                request.user
            )  # Assign the authenticated user to the new request

            # Wrap the WSGIRequest with DRF's Request
            drf_request = Request(wsgi_request)
            generate_treatment_report_api = GenerateTreatmentReport()
            response = generate_treatment_report_api.get(drf_request)

            if response.status_code != status.HTTP_200_OK:
                return response

            report_generation_response = response.data

            # Handle the nested data field
            data_field = report_generation_response.get("data", {})
            if isinstance(data_field, dict):  # 'data' is a dictionary
                nested_data_field = data_field.get("data", [])
            elif isinstance(data_field, list):  # 'data' is already a list
                nested_data_field = data_field
            else:
                nested_data_field = []

            # Ensure the nested data is a list and process the first item
            protocol_details = None
            if isinstance(nested_data_field, list) and nested_data_field:
                metadata = nested_data_field[0].get("section_metadata", {})
                # Try to get 'protocol' first
                protocol_details = metadata.get("protocol")
                # If 'protocol' is not available, check for 'protocols' and use the first entry if available
                if not protocol_details:
                    protocols_list = metadata.get("protocols")
                    if protocols_list and isinstance(protocols_list, list):
                        protocol_details = protocols_list[0]

                if not protocol_details:
                    raise ValueError(
                        "Protocol details not found in the report generation response."
                    )

            # Update the diagnosis report based on the service type
            next_protocol_id = protocol_details
            if str(service_id) == "5":  # Auricular treatment
                diagnosis_report.auricular_treatment = next_protocol_id
            elif str(service_id) == "7":  # Mudra treatment
                diagnosis_report.mudra_treatment = next_protocol_id
            elif str(service_id) == "8":  # Yoga treatment
                diagnosis_report.yoga_treatment = next_protocol_id
            elif str(service_id) == "4":  # Colour treatment
                diagnosis_report.colour_treatment = next_protocol_id
            elif str(service_id) == "6":  # Multi Seed treatment
                diagnosis_report.seed_treatment = next_protocol_id
            elif str(service_id) == "2":  # Acupressure treatment
                diagnosis_report.acupressure_treatment = next_protocol_id
            elif str(service_id) == "3":  # Single Point treatment
                diagnosis_report.single_point_treatment = next_protocol_id
            elif str(service_id) == "9":  # Pranayama treatment
                diagnosis_report.pranayama_treatment = next_protocol_id
            diagnosis_report.save()

        except Exception as e:
            return ErrorResponse(
                errors={"message": f"Error processing service logic: {e}"},
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Step 8: Return a success response with relevant data.
        return StandardResponse(
            data={
                "diagnosis_report": {
                    "report_history_id": diagnosis_report.report_history_id,
                },
                "wallet_deduction_response": wallet_deduction_response.data,
                "report_generation_response": report_generation_response,
            },
            message="Treatment purchased successfully.",
            status_code=status.HTTP_200_OK,
        )


class GenerateTreatmentReport(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Step 1: Extract `report_history_id` and `service_id` from the request body

        report_history_id = request.query_params.get("report_history_id")
        service_id = request.query_params.get("service_id")

        # Step 2: Check if `report_history_id` is provided; return an error if missing or invalid
        if not report_history_id:
            return ErrorResponse(
                errors={"detail": "report_history_id is required."},
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # Check if the `report_history_id` corresponds to a valid `DiagnosisReportHistory`
            report_history = DiagnosisReportHistory.objects.get(
                report_history_id=report_history_id
            )
        except DiagnosisReportHistory.DoesNotExist:
            return ErrorResponse(
                errors={
                    "detail": f"Invalid report_history_id {report_history_id}. This record does not exist."
                },
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # Step 3: Check if `service_id` is provided and valid; return an error if missing or invalid
        if not service_id:
            return ErrorResponse(
                errors={"detail": "service_id is required."},
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # Validate if `service_id` exists in the SERVICE_TREATMENT_MAP
        if service_id not in SERVICE_TREATMENT_MAP:
            return ErrorResponse(
                errors={
                    "detail": f"Invalid service_id {service_id}. Valid options are {', '.join(SERVICE_TREATMENT_MAP.keys())}."
                },
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # Step 6: Extract `report_pattern_type` from the `DiagnosisReportHistory` object
        report_pattern_type = (
            report_history.report_pattern_type_id
        )  # Assuming ForeignKey returns ID
        if not report_pattern_type:
            # Step 7: Return an error if `report_pattern_type` is not found
            return ErrorResponse(
                errors={
                    "detail": "No report_pattern_type found in DiagnosisReportHistory."
                },
                status_code=status.HTTP_404_NOT_FOUND,
            )

        # Step 8: Map `service_id` to the corresponding treatment API using SERVICE_TREATMENT_MAP
        treatment_type = SERVICE_TREATMENT_MAP[service_id]

        # print(282, report_history.seed_organ)

        response = {}
        # Step 9: Call the appropriate report generation API based on the treatment type
        if treatment_type == "auricular_treatment":
            response = generate_auricular_report(
                {
                    "pattern_id": report_history.report_pattern_type,
                    "patient_id": (
                        report_history.patient_id.id
                        if hasattr(report_history.patient_id, "id")
                        else report_history.patient_id
                    ),
                }
            )
        elif treatment_type == "mudra_treatment":
            response = generate_mudra_report(
                {
                    "pattern_id": report_history.report_pattern_type,
                    "patient_id": (
                        report_history.patient_id.id
                        if hasattr(report_history.patient_id, "id")
                        else report_history.patient_id
                    ),
                }
            )
        elif treatment_type == "yoga_treatment":
            response = generate_yoga_report(
                {
                    "pattern_id": report_history.report_pattern_type,
                    "patient_id": (
                        report_history.patient_id.id
                        if hasattr(report_history.patient_id, "id")
                        else report_history.patient_id
                    ),
                }
            )
        elif treatment_type == "colour_treatment":
            response = generate_colour_report(
                {
                    "pattern_id": report_history.report_pattern_type,
                    "patient_id": (
                        report_history.patient_id.id
                        if hasattr(report_history.patient_id, "id")
                        else report_history.patient_id
                    ),
                }
            )
        elif treatment_type == "seed_treatment":
            response = generate_multi_seed_report(
                {
                    "pattern_id": report_history.report_pattern_type,
                    "patient_id": (
                        report_history.patient_id.id
                        if hasattr(report_history.patient_id, "id")
                        else report_history.patient_id
                    ),
                }
            )
        elif treatment_type == "acupressure_treatment":
            response = generate_acupressure_report(
                {
                    "pattern_id": report_history.report_pattern_type,
                    "patient_id": (
                        report_history.patient_id.id
                        if hasattr(report_history.patient_id, "id")
                        else report_history.patient_id
                    ),
                }
            )
        elif treatment_type == "single_point_treatment":
            response = generate_single_seed_report(
                report_history.seed_organ,
                report_history.seed_yin_yang,
                # organ_name = "GB",
                # yin_yang="yang",
            )

        elif treatment_type == "pranayama_treatment":
            response = generate_pranayama_report(
                {
                    "pattern_id": report_history.report_pattern_type,
                    "patient_id": (
                        report_history.patient_id.id
                        if hasattr(report_history.patient_id, "id")
                        else report_history.patient_id
                    ),
                }
            )

        # Step 10: Handle the response from the respective function
        if response["status_code"] == 200:

            # Step 10.1: Return a successful response if the function call succeeded
            return StandardResponse(
                data=response, message="Report generated successfully.", status_code=200
            )
        else:
            # Step 10.2: Return an error response if the function call failed
            return ErrorResponse(
                errors=response.get("errors", {}), status_code=response["status_code"]
            )


@method_decorator(xframe_options_exempt, name="dispatch")
class ReportPDFView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):

        # Step1: Check if service_ids exists
        language = request.query_params.get("language", "").strip().lower() or "eng"  # <<-- corrected
        if not language:
            language = "eng"

        service_ids = []
        if request.query_params.get("service_ids"):
            service_ids = request.query_params.get("service_ids").split(",")
            # Convert the split strings to integers, ignoring invalid entries
            try:
                service_ids = [int(sid) for sid in service_ids]
            except ValueError:
                return ErrorResponse(
                    errors={"service_ids": "All service_ids must be integers."},
                    status_code=400,
                )

        # Step2: Check if history id is valid
        report_history_id = request.query_params.get("report_history_id")
        # Check if report_history_id is provided
        if not report_history_id:
            return ErrorResponse(
                errors={"report_history_id": "This field is required."}, status_code=400
            )

        # Validate and retrieve the object, handle invalid IDs
        try:
            report_history = get_object_or_404(
                DiagnosisReportHistory, report_history_id=report_history_id
            )
        except ValueError:
            return ErrorResponse(
                errors={
                    "report_history_id": "Invalid report_history_id. It must be an integer."
                },
                status_code=400,
            )
        except Http404:
            return ErrorResponse(
                errors={
                    "report_history_id": "Report history not found for the given ID."
                },
                status_code=404,
            )

        pattern_number = report_history.report_pattern_type_id

        # Retrieve the DiagnosticResource object using pattern_number
        diagnostic_resource = get_object_or_404(
            DiagnosticResource, pattern_number=pattern_number
        )

        # Step 3: Finalise the treatment report to be downloaded
        """
        Scenario1: Download all report --> download diagnosis +  purchase treatment report
        Scenario2: Download diagnosis + purchased --> download diagnosis +  purchase treatment report
        Scenario3: Download diagnosis + purchased & non-purchased treatment 
        --> download diagnosis +  purchase treatment report only

        """
        column_to_extract = list(SERVICE_TREATMENT_MAP.values())

        purchased_service_ids = {
            column: getattr(report_history, column, None)
            for column in column_to_extract
            if getattr(report_history, column, None) is not None
        }

        download_service_ids = []
        if purchased_service_ids:
            purchased_service_ids = [
                int(k)
                for k, v in SERVICE_TREATMENT_MAP.items()
                if v in purchased_service_ids
            ]

            # Convert service_ids (query params) to integers
            service_ids = [int(sid) for sid in service_ids] if service_ids else []

            download_service_ids = [
                item for item in purchased_service_ids if item in service_ids
            ]

        # Step 2: GenerateDiagnosisReport view
        diagnosis_report_view = GenerateDiagnosisReport()
        request = request._request  # Make a mutable copy
        request.data = {"regenerate": True, "report_history_id": report_history_id}

        diagnsys_rf = APIRequestFactory()
        diagnsys_wsgi_request = diagnsys_rf.get(
            "/api/v1/dynamic-report-service/download-diagnosis-report/",
            {
                "regenerate": True,
                "report_history_id": report_history_id,
                "language": language,
            },
        )

        # Wrap the WSGIRequest with DRF's Request
        request = Request(diagnsys_wsgi_request)

        diagnosis_response = diagnosis_report_view.get(request)

        if diagnosis_response.status_code != 200:
            return ErrorResponse(
                errors={
                    "diagnosis": diagnosis_response.data.get(
                        "message", "Error generating report."
                    )
                },
                status_code=500,
            )

        # Step 3: Extract the filtered data (which is essentially the treatment report)

        diagnosis_filtered_data = diagnosis_response.data.get("data", [{}])

        if not diagnosis_filtered_data:
            return ErrorResponse(
                errors={
                    "diagnosis": "No data found for the provided report history ID."
                },
                status_code=404,
            )

        all_context = {"sections": []}

        all_context["sections"].extend(
            diagnosis_filtered_data
            if isinstance(diagnosis_filtered_data, list)
            else [diagnosis_filtered_data]
        )

        # NEW: Generate dosha chart using the vata, pitta, and kapha values
        # (Ensure that generate_dosha_chart is imported or defined in your codebase)
        dosha_chart = generate_dosha_chart(
            report_history.vata, report_history.pitta, report_history.kapha
        )

        yin_yang = plot_organ_chart(
            report_history.wind_yin,
            report_history.wind_yang,
            report_history.heat_yin,
            report_history.heat_yang,
            report_history.humid_yin,
            report_history.humid_yang,
            report_history.dry_yin,
            report_history.dry_yang,
            report_history.cold_yin,
            report_history.cold_yang,
        )

        food_metabolism = plot_diagonal_gradient(
            report_history.carbohydrate, report_history.protein, report_history.fat
        )

        pattern_map = next(
            (
                item
                for item in food_metabolism_map
                if item["pattern_number"]
                == report_history.report_pattern_type.pattern_number
            ),
            None,  # default value if not found
        )
        # Extract the values
        carbohydrate = pattern_map["carbo"]
        protein = pattern_map["protein"]
        fat = pattern_map["fat"]

        # Call the function with these values
        food_metabolism = plot_diagonal_gradient(carbohydrate, protein, fat)

        if diagnostic_resource.body_anotations:
            labels_to_highlight = [
                label.strip()
                for label in diagnostic_resource.body_anotations.split(",")
            ]
        else:
            labels_to_highlight = []

        # print(449, diagnostic_resource.body_pdf_image)
        body_image = highlight_body_parts(
            diagnostic_resource.body_pdf_image, labels_to_highlight
        )

        pulse_data = report_history.pulse_id

        if pulse_data and pulse_data.signal_data:
            try:
                pulse_signal_data = json.loads(pulse_data.signal_data)
            except json.JSONDecodeError:
                pulse_signal_data = pulse_data.signal_data
        else:
            pulse_signal_data = []

        # If the data is a string, split it; if it's already a list, proceed accordingly.
        if isinstance(pulse_signal_data, str):
            pulse_signal_data = [
                float(val.strip()) for val in pulse_signal_data.split(",")
            ]
        elif isinstance(pulse_signal_data, list):
            # Optionally, if the list items are strings, convert them to float.
            pulse_signal_data = [float(val) for val in pulse_signal_data]

        pulse_image_plot = pulse_image(pulse_signal_data)

        # print(469, body_image)

        # NEW: Replace the value of 'tridosha_pdf_icon' with the dosha_chart image
        for section in all_context["sections"]:
            for content in section.get("content", []):
                if content.get("title") == "tridosha_pdf_graph":
                    content["value"] = dosha_chart

        for section in all_context["sections"]:
            for content in section.get("content", []):
                if content.get("title") == "yin_yang_pdf_graph":
                    content["value"] = yin_yang

        for section in all_context["sections"]:
            for content in section.get("content", []):
                if content.get("title") == "fm_pdf_graph":
                    content["value"] = food_metabolism

        heart_rate = report_history.heart_rate

        for section in all_context["sections"]:
            for content in section.get("content", []):
                if content.get("title") == "heart_rate":
                    content["value"] = "None"

        for section in all_context["sections"]:
            for content in section.get("content", []):
                if content.get("title") == "body_pdf_image":
                    content["value"] = body_image

        for section in all_context["sections"]:
            for content in section.get("content", []):
                if content.get("title") == "pulse_pdf_image":
                    content["value"] = pulse_image_plot

        # GenerateTreatmentReport is already defined
        treatment_report_view = GenerateTreatmentReport()

        # Loop through each service ID in download_service_ids
        for service_id in download_service_ids:
            # Create the request
            rf = APIRequestFactory()
            wsgi_request = rf.get(
                "/api/v1/dynamic-report-service/generate-treatment-report/",
                {"report_history_id": report_history_id, "service_id": service_id},
            )

            # Wrap the WSGIRequest with DRF's Request
            request = Request(wsgi_request)
            treatment_response = treatment_report_view.get(request)

            # Extract data from the response
            treatment_filtered_data = treatment_response.data.get("data", {}).get(
                "data", [{}]
            )

            # print(536, treatment_filtered_data)

            # Check if data is empty
            if not treatment_filtered_data:
                return ErrorResponse(
                    errors={"treatment": f"No data found for service_id {service_id}."},
                    status_code=404,
                )

            all_context["sections"].extend(
                treatment_filtered_data
                if isinstance(treatment_filtered_data, list)
                else [treatment_filtered_data]
            )

            #    # Prepare a serializable version of all_context
        serializable_context = remove_bytesio(all_context)

        with open("all_context.json", "w") as f:
            json.dump(serializable_context, f, indent=4)

        # print(393, all_context)
        # Process image URLs to base64
        for section in all_context["sections"]:
            for content in section["content"]:
                if content["type"] == "image":
                    image_url = content["value"]
                    content["value"] = image_url_to_base64(image_url)

        try:

            # Choose HTML template based on language
            if language == "kan":
                html_template = "diagnostic_resource_kannada.html"
            else:
                html_template = "diagnostic_resource_weasyprint1.html"
            # Render HTML content from the context
            html_content = render_to_string(html_template, all_context)

            base_url = request.build_absolute_uri(
                "/"
            )  # ensures that static files can be located

            pdf_file = BytesIO()
            HTML(string=html_content, base_url=base_url).write_pdf(target=pdf_file)
            pdf_file.seek(0)

            # NEW: If no treatment report is added, limit the output to the first 6 pages.
            if not download_service_ids:

                reader = PdfReader(pdf_file)
                writer = PdfWriter()
                total_pages = len(reader.pages)
                pages_to_include = min(6, total_pages)
                for i in range(pages_to_include):
                    writer.add_page(reader.pages[i])
                new_pdf_file = BytesIO()
                writer.write(new_pdf_file)
                new_pdf_file.seek(0)
                pdf_content = new_pdf_file.getvalue()
            else:
                pdf_content = pdf_file.getvalue()
            response = HttpResponse(pdf_content, content_type="application/pdf")
            response["Content-Disposition"] = (
                f'inline; filename="DiagnosticReport_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf"'
            )

            if report_history.patient_id:
                patient = report_history.patient_id
                # Combine first name and last name if available; otherwise, use just the first name.
                if patient.last_name:
                    raw_patient_name = f"{patient.first_name}_{patient.last_name}"
                else:
                    raw_patient_name = patient.first_name
            else:
                raw_patient_name = "unknown_patient"

            # Use slugify to ensure a safe filename string
            patient_name = slugify(raw_patient_name)

            # Create the filename using the patient name and the current date and time.
            file_name = f"{patient_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"

            # AWS S3 credentials from environment
            AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
            AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
            AWS_STORAGE_BUCKET_NAME = os.getenv("AWS_STORAGE_BUCKET_NAME")
            AWS_S3_REGION_NAME = os.getenv("AWS_S3_REGION_NAME", "ap-south-1")

            # Initialize S3 client using AWS credentials
            s3_client = boto3.client(
                "s3",
                aws_access_key_id=AWS_ACCESS_KEY_ID,
                aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
                region_name=AWS_S3_REGION_NAME,
            )

            # Upload the PDF to AWS S3 bucket
            s3_client.put_object(
                Bucket=AWS_STORAGE_BUCKET_NAME,
                Key=f"temp_reports/{file_name}",
                Body=pdf_content,
                ContentType="application/pdf",
            )

            # Construct the downloadable URL for AWS S3
            download_url = f"https://{AWS_STORAGE_BUCKET_NAME}.s3.{AWS_S3_REGION_NAME}.amazonaws.com/temp_reports/{file_name}"

            # Return the downloadable link
            return StandardResponse(
                data={"pdf_url": download_url},
                message="PDF generated successfully.",
                status_code=200,
            )

        except ClientError as e:
            # Handle S3 client errors
            return ErrorResponse(errors={"s3": str(e)}, status_code=500)

        except Exception as e:
            # Handle general exceptions
            return ErrorResponse(errors={"general": str(e)}, status_code=500)


class UnpurchaseTreatmentReport(APIView):
    """
    API endpoint to unpurchase a treatment service for a diagnosis report.
    """

    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        # Step 1: Extract `report_history_id` and `service_id` from the request.
        report_history_id = request.data.get("report_history_id")
        service_id = request.data.get("service_id")

        # Step 2: Validate if `report_history_id` and `service_id` are provided.
        if not report_history_id or not service_id:
            return ErrorResponse(
                errors={
                    "message": "Both report_history_id and service_id are required."
                },
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # Step 3: Fetch the DiagnosisReportHistory object using `report_history_id`.
        try:
            diagnosis_report = get_object_or_404(
                DiagnosisReportHistory, report_history_id=report_history_id
            )
        except Exception as e:
            return ErrorResponse(
                errors={"message": f"Invalid report_history_id: {e}"},
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # Step 4: Validate if the `service_id` exists in the SERVICE_TREATMENT_MAP.
        try:
            service = Service.objects.get(service_id=service_id)
        except Service.DoesNotExist:
            return ErrorResponse(
                errors={"message": f"Invalid service_id: {service_id}"},
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # Step 5: Check if the treatment for the service exists.
        treatment_field = SERVICE_TREATMENT_MAP.get(str(service_id))
        if not treatment_field or not getattr(diagnosis_report, treatment_field, None):
            return ErrorResponse(
                errors={
                    "message": f"{service.name} has not been purchased for this report."
                },
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # Step 6: Remove the treatment details from the diagnosis report.
        try:
            if treatment_field:
                setattr(diagnosis_report, treatment_field, None)
                diagnosis_report.save()
        except Exception as e:
            return ErrorResponse(
                errors={"message": f"Error removing treatment details: {e}"},
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Step 8: Return a success response with relevant data.
        return StandardResponse(
            data={
                "diagnosis_report": {
                    "report_history_id": diagnosis_report.report_history_id,
                },
            },
            message="Treatment unpurchased successfully.",
            status_code=status.HTTP_200_OK,
        )


@method_decorator(xframe_options_exempt, name="dispatch")
class ReportPDFViewBuffer(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):

        # Step1: Check if service_ids exists
        service_ids = []
        if request.query_params.get("service_ids"):
            service_ids = request.query_params.get("service_ids").split(",")
            # Convert the split strings to integers, ignoring invalid entries
            try:
                service_ids = [int(sid) for sid in service_ids]
            except ValueError:
                return ErrorResponse(
                    errors={"service_ids": "All service_ids must be integers."},
                    status_code=400,
                )

        # Step2: Check if history id is valid
        report_history_id = request.query_params.get("report_history_id")
        # Check if report_history_id is provided
        if not report_history_id:
            return ErrorResponse(
                errors={"report_history_id": "This field is required."}, status_code=400
            )

        # Validate and retrieve the object, handle invalid IDs
        try:
            report_history = get_object_or_404(
                DiagnosisReportHistory, report_history_id=report_history_id
            )
        except ValueError:
            return ErrorResponse(
                errors={
                    "report_history_id": "Invalid report_history_id. It must be an integer."
                },
                status_code=400,
            )
        except Http404:
            return ErrorResponse(
                errors={
                    "report_history_id": "Report history not found for the given ID."
                },
                status_code=404,
            )

        pattern_number = report_history.report_pattern_type_id

        # Retrieve the DiagnosticResource object using pattern_number
        diagnostic_resource = get_object_or_404(
            DiagnosticResource, pattern_number=pattern_number
        )
        # NEW: Generate dosha chart using the vata, pitta, and kapha values
        # (Ensure that generate_dosha_chart is imported or defined in your codebase)
        dosha_chart = generate_dosha_chart(
            report_history.vata, report_history.pitta, report_history.kapha
        )

        yin_yang = plot_organ_chart(
            report_history.wind_yin,
            report_history.wind_yang,
            report_history.heat_yin,
            report_history.heat_yang,
            report_history.humid_yin,
            report_history.humid_yang,
            report_history.dry_yin,
            report_history.dry_yang,
            report_history.cold_yin,
            report_history.cold_yang,
        )

        food_metabolism = plot_diagonal_gradient(
            report_history.carbohydrate, report_history.protein, report_history.fat
        )

        if diagnostic_resource.body_anotations:
            labels_to_highlight = [
                label.strip()
                for label in diagnostic_resource.body_anotations.split(",")
            ]
        else:
            labels_to_highlight = []

        body_image = highlight_body_parts(
            diagnostic_resource.body_pdf_image, labels_to_highlight
        )

        pulse_data = report_history.pulse_id

        if pulse_data and pulse_data.signal_data:
            try:
                pulse_signal_data = json.loads(pulse_data.signal_data)
            except json.JSONDecodeError:
                pulse_signal_data = pulse_data.signal_data
        else:
            pulse_signal_data = []

        # If the data is a string, split it; if it's already a list, proceed accordingly.
        if isinstance(pulse_signal_data, str):
            pulse_signal_data = [
                float(val.strip()) for val in pulse_signal_data.split(",")
            ]
        elif isinstance(pulse_signal_data, list):
            # Optionally, if the list items are strings, convert them to float.
            pulse_signal_data = [float(val) for val in pulse_signal_data]

        pulse_image_plot = pulse_image(pulse_signal_data)

        # Step 3: Finalise the treatment report to be downloaded
        """
        Scenario1: Download all report --> download diagnosis +  purchase treatment report
        Scenario2: Download diagnosis + purchased --> download diagnosis +  purchase treatment report
        Scenario3: Download diagnosis + purchased & non-purchased treatment 
        --> download diagnosis +  purchase treatment report only

        """
        column_to_extract = list(SERVICE_TREATMENT_MAP.values())

        purchased_service_ids = {
            column: getattr(report_history, column, None)
            for column in column_to_extract
            if getattr(report_history, column, None) is not None
        }

        download_service_ids = []
        if purchased_service_ids:
            purchased_service_ids = [
                int(k)
                for k, v in SERVICE_TREATMENT_MAP.items()
                if v in purchased_service_ids
            ]

            # Convert service_ids (query params) to integers
            service_ids = [int(sid) for sid in service_ids] if service_ids else []

            download_service_ids = [
                item for item in purchased_service_ids if item in service_ids
            ]

        # Step 2: GenerateDiagnosisReport view
        diagnosis_report_view = GenerateDiagnosisReport()
        request = request._request  # Make a mutable copy
        request.data = {"regenerate": True, "report_history_id": report_history_id}

        diagnsys_rf = APIRequestFactory()
        diagnsys_wsgi_request = diagnsys_rf.get(
            "/api/v1/dynamic-report-service/download-diagnosis-report/",
            {"regenerate": True, "report_history_id": report_history_id},
        )

        # Wrap the WSGIRequest with DRF's Request
        request = Request(diagnsys_wsgi_request)

        diagnosis_response = diagnosis_report_view.get(request)

        if diagnosis_response.status_code != 200:
            return ErrorResponse(
                errors={
                    "diagnosis": diagnosis_response.data.get(
                        "message", "Error generating report."
                    )
                },
                status_code=500,
            )

        # Step 3: Extract the filtered data (which is essentially the treatment report)

        diagnosis_filtered_data = diagnosis_response.data.get("data", [{}])

        if not diagnosis_filtered_data:
            return ErrorResponse(
                errors={
                    "diagnosis": "No data found for the provided report history ID."
                },
                status_code=404,
            )

        all_context = {"sections": []}

        all_context["sections"].extend(
            diagnosis_filtered_data
            if isinstance(diagnosis_filtered_data, list)
            else [diagnosis_filtered_data]
        )

        # NEW: Replace the value of 'tridosha_pdf_icon' with the dosha_chart image
        for section in all_context["sections"]:
            for content in section.get("content", []):
                if content.get("title") == "tridosha_pdf_graph":
                    content["value"] = dosha_chart

        for section in all_context["sections"]:
            for content in section.get("content", []):
                if content.get("title") == "yin_yang_pdf_graph":
                    content["value"] = yin_yang

        for section in all_context["sections"]:
            for content in section.get("content", []):
                if content.get("title") == "fm_pdf_graph":
                    content["value"] = food_metabolism

        heart_rate = report_history.heart_rate

        for section in all_context["sections"]:
            for content in section.get("content", []):
                if content.get("title") == "heart_rate":
                    content["value"] = "None"

        for section in all_context["sections"]:
            for content in section.get("content", []):
                if content.get("title") == "body_pdf_image":
                    content["value"] = body_image

        for section in all_context["sections"]:
            for content in section.get("content", []):
                if content.get("title") == "pulse_pdf_image":
                    content["value"] = pulse_image_plot

        # GenerateTreatmentReport is already defined
        treatment_report_view = GenerateTreatmentReport()

        # Loop through each service ID in download_service_ids
        for service_id in download_service_ids:
            # Create the request
            rf = APIRequestFactory()
            wsgi_request = rf.get(
                "/api/v1/dynamic-report-service/generate-treatment-report/",
                {"report_history_id": report_history_id, "service_id": service_id},
            )

            # Wrap the WSGIRequest with DRF's Request
            request = Request(wsgi_request)
            treatment_response = treatment_report_view.get(request)

            # Extract data from the response
            treatment_filtered_data = treatment_response.data.get("data", {}).get(
                "data", [{}]
            )

            # Check if data is empty
            if not treatment_filtered_data:
                return ErrorResponse(
                    errors={"treatment": f"No data found for service_id {service_id}."},
                    status_code=404,
                )

            all_context["sections"].extend(
                treatment_filtered_data
                if isinstance(treatment_filtered_data, list)
                else [treatment_filtered_data]
            )

        #    # Prepare a serializable version of all_context
        #     serializable_context = remove_bytesio(all_context)

        #     with open("all_context.json", "w") as f:
        #         json.dump(serializable_context, f, indent=4)

        # print(620, all_context)

        # Process image URLs to base64

        for section in all_context["sections"]:
            for content in section["content"]:
                if content["type"] == "image":
                    image_url = content["value"]
                    content["value"] = image_url_to_base64(image_url)

        try:

            html_content = render_to_string(
                "diagnostic_resource_pdf1.html", all_context
            )

            pdf_file = BytesIO()
            pisa_status = pisa.CreatePDF(
                html_content, dest=pdf_file, link_callback=fetch_resources
            )

            if pisa_status.err:
                return ErrorResponse(
                    errors={"pdf_generation": "Error creating PDF."}, status_code=500
                )

            pdf_file.seek(0)

            # NEW: If no treatment report is added, limit the output to the first 6 pages.
            if not download_service_ids:

                reader = PdfReader(pdf_file)
                writer = PdfWriter()
                total_pages = len(reader.pages)
                pages_to_include = min(6, total_pages)
                for i in range(pages_to_include):
                    writer.add_page(reader.pages[i])
                new_pdf_file = BytesIO()
                writer.write(new_pdf_file)
                new_pdf_file.seek(0)
                pdf_content = new_pdf_file.getvalue()
            else:
                pdf_content = pdf_file.getvalue()
            response = HttpResponse(pdf_content, content_type="application/pdf")
            response["Content-Disposition"] = (
                f'inline; filename="DiagnosticReport_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf"'
            )

            return response

        except Exception as e:
            return ErrorResponse(errors={"general": str(e)}, status_code=500)


def remove_bytesio(obj):
    if isinstance(obj, BytesIO):
        # Remove or replace BytesIO instances (here we choose to replace with None)
        return None
    elif isinstance(obj, dict):
        return {key: remove_bytesio(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [remove_bytesio(item) for item in obj]
    else:
        return obj


@method_decorator(xframe_options_exempt, name="dispatch")
class ReportPDFViewTimer(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        import time

        timers = {}
        overall_start = time.time()

        # Step 1: Check if service_ids exists
        step1_start = time.time()
        service_ids = []
        if request.query_params.get("service_ids"):
            service_ids = request.query_params.get("service_ids").split(",")
            try:
                service_ids = [int(sid) for sid in service_ids]
            except ValueError:
                return ErrorResponse(
                    errors={"service_ids": "All service_ids must be integers."},
                    status_code=400,
                )
        timers["step1_service_ids"] = time.time() - step1_start

        # Step 2: Check if history id is valid and retrieve report_history
        step2_start = time.time()
        report_history_id = request.query_params.get("report_history_id")
        if not report_history_id:
            return ErrorResponse(
                errors={"report_history_id": "This field is required."}, status_code=400
            )
        try:
            report_history = get_object_or_404(
                DiagnosisReportHistory, report_history_id=report_history_id
            )
        except ValueError:
            return ErrorResponse(
                errors={
                    "report_history_id": "Invalid report_history_id. It must be an integer."
                },
                status_code=400,
            )
        except Http404:
            return ErrorResponse(
                errors={
                    "report_history_id": "Report history not found for the given ID."
                },
                status_code=404,
            )
        timers["step2_report_history_lookup"] = time.time() - step2_start

        # Step 3: Retrieve DiagnosticResource using pattern_number
        step3_start = time.time()
        pattern_number = report_history.report_pattern_type_id
        diagnostic_resource = get_object_or_404(
            DiagnosticResource, pattern_number=pattern_number
        )
        timers["step3_diagnostic_resource"] = time.time() - step3_start

        # Step 4: Finalise the treatment report to be downloaded
        step4_start = time.time()
        column_to_extract = list(SERVICE_TREATMENT_MAP.values())
        purchased_service_ids = {
            column: getattr(report_history, column, None)
            for column in column_to_extract
            if getattr(report_history, column, None) is not None
        }
        download_service_ids = []
        if purchased_service_ids:
            purchased_service_ids = [
                int(k)
                for k, v in SERVICE_TREATMENT_MAP.items()
                if v in purchased_service_ids
            ]
            service_ids = [int(sid) for sid in service_ids] if service_ids else []
            download_service_ids = [
                item for item in purchased_service_ids if item in service_ids
            ]
        timers["step4_finalize_treatment_report"] = time.time() - step4_start

        # Step 5: Generate Diagnosis Report view
        step5_start = time.time()
        diagnosis_report_view = GenerateDiagnosisReport()
        request = request._request  # Make a mutable copy
        request.data = {"regenerate": True, "report_history_id": report_history_id}
        diagnsys_rf = APIRequestFactory()
        diagnsys_wsgi_request = diagnsys_rf.get(
            "/api/v1/dynamic-report-service/download-diagnosis-report/",
            {"regenerate": True, "report_history_id": report_history_id},
        )
        request = Request(diagnsys_wsgi_request)
        diagnosis_response = diagnosis_report_view.get(request)
        if diagnosis_response.status_code != 200:
            return ErrorResponse(
                errors={
                    "diagnosis": diagnosis_response.data.get(
                        "message", "Error generating report."
                    )
                },
                status_code=500,
            )
        diagnosis_filtered_data = diagnosis_response.data.get("data", [{}])
        if not diagnosis_filtered_data:
            return ErrorResponse(
                errors={
                    "diagnosis": "No data found for the provided report history ID."
                },
                status_code=404,
            )
        all_context = {"sections": []}
        all_context["sections"].extend(
            diagnosis_filtered_data
            if isinstance(diagnosis_filtered_data, list)
            else [diagnosis_filtered_data]
        )
        timers["step5_generate_diagnosis_report"] = time.time() - step5_start

        # Step 6: Generate charts and update the context
        step6_start = time.time()
        step6_1_start = time.time()
        dosha_chart = generate_dosha_chart(
            report_history.vata, report_history.pitta, report_history.kapha
        )
        timers["step6_1_generate_charts"] = time.time() - step6_1_start
        step6_2_start = time.time()
        yin_yang = plot_organ_chart(
            report_history.wind_yin,
            report_history.wind_yang,
            report_history.heat_yin,
            report_history.heat_yang,
            report_history.humid_yin,
            report_history.humid_yang,
            report_history.dry_yin,
            report_history.dry_yang,
            report_history.cold_yin,
            report_history.cold_yang,
        )
        timers["step6_2_generate_charts"] = time.time() - step6_2_start
        step6_3_start = time.time()
        food_metabolism = plot_diagonal_gradient(
            report_history.carbohydrate, report_history.protein, report_history.fat
        )
        timers["step6_3_generate_charts"] = time.time() - step6_3_start
        step6_4_start = time.time()
        if diagnostic_resource.body_anotations:
            labels_to_highlight = [
                label.strip()
                for label in diagnostic_resource.body_anotations.split(",")
            ]
        else:
            labels_to_highlight = []
        body_image = highlight_body_parts(
            diagnostic_resource.body_pdf_image, labels_to_highlight
        )
        timers["step6_4_generate_charts"] = time.time() - step6_4_start

        pulse_data = report_history.pulse_id

        if pulse_data and pulse_data.signal_data:
            try:
                pulse_signal_data = json.loads(pulse_data.signal_data)
            except json.JSONDecodeError:
                pulse_signal_data = pulse_data.signal_data
        else:
            pulse_signal_data = []

        # If the data is a string, split it; if it's already a list, proceed accordingly.
        if isinstance(pulse_signal_data, str):
            pulse_signal_data = [
                float(val.strip()) for val in pulse_signal_data.split(",")
            ]
        elif isinstance(pulse_signal_data, list):
            # Optionally, if the list items are strings, convert them to float.
            pulse_signal_data = [float(val) for val in pulse_signal_data]

        pulse_image_plot = pulse_image(pulse_signal_data)

        for section in all_context["sections"]:
            for content in section.get("content", []):
                if content.get("title") == "tridosha_pdf_graph":
                    content["value"] = dosha_chart
                if content.get("title") == "yin_yang_pdf_graph":
                    content["value"] = yin_yang
                if content.get("title") == "fm_pdf_graph":
                    content["value"] = food_metabolism
                if content.get("title") == "heart_rate":
                    content["value"] = report_history.heart_rate
                if content.get("title") == "body_pdf_image":
                    content["value"] = body_image
                if content.get("title") == "pulse_pdf_image":
                    content["value"] = pulse_image_plot
        timers["step6_generate_charts"] = time.time() - step6_start

        # Step 7: Process Treatment Report(s)
        step7_start = time.time()
        treatment_report_view = GenerateTreatmentReport()
        for service_id in download_service_ids:
            rf = APIRequestFactory()
            wsgi_request = rf.get(
                "/api/v1/dynamic-report-service/generate-treatment-report/",
                {"report_history_id": report_history_id, "service_id": service_id},
            )
            request = Request(wsgi_request)
            treatment_response = treatment_report_view.get(request)
            treatment_filtered_data = treatment_response.data.get("data", {}).get(
                "data", [{}]
            )
            if not treatment_filtered_data:
                return ErrorResponse(
                    errors={"treatment": f"No data found for service_id {service_id}."},
                    status_code=404,
                )
            all_context["sections"].extend(
                treatment_filtered_data
                if isinstance(treatment_filtered_data, list)
                else [treatment_filtered_data]
            )
        timers["step7_treatment_reports"] = time.time() - step7_start

        # Step 8: Convert image URLs to base64
        step8_start = time.time()
        for section in all_context["sections"]:
            for content in section["content"]:
                if content["type"] == "image":
                    image_url = content["value"]
                    content["value"] = image_url_to_base64(image_url)
        timers["step8_image_conversion"] = time.time() - step8_start

        # Step 9: Render HTML, convert to PDF, and upload to S3
        step9_start = time.time()
        html_content = render_to_string("diagnostic_resource_pdf1.html", all_context)
        pdf_file = BytesIO()
        pisa_status = pisa.CreatePDF(html_content, dest=pdf_file)
        if pisa_status.err:
            return ErrorResponse(
                errors={"pdf_generation": "Error creating PDF."}, status_code=500
            )
        pdf_file.seek(0)
        pdf_content = pdf_file.getvalue()
        file_name = f"DiagnosticReport_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"

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
        s3_client.put_object(
            Bucket=AWS_STORAGE_BUCKET_NAME,
            Key=f"temp_reports/{file_name}",
            Body=pdf_content,
            ContentType="application/pdf",
        )
        download_url = f"https://{AWS_STORAGE_BUCKET_NAME}.s3.{AWS_S3_REGION_NAME}.amazonaws.com/temp_reports/{file_name}"
        timers["step9_html_pdf_s3"] = time.time() - step9_start

        timers["total"] = time.time() - overall_start

        # Return the response with the timer information included
        return StandardResponse(
            data={"pdf_url": download_url, "timers": timers},
            message="PDF generated successfully.",
            status_code=200,
        )
