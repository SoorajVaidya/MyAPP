import os
import time  # New import for timer functionality
from datetime import datetime
from io import BytesIO
import json
import boto3
import logging
from botocore.exceptions import ClientError
from django.db import transaction
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.utils.decorators import method_decorator
from django.views.decorators.clickjacking import xframe_options_exempt
import requests
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView
from sqlalchemy import null
from weasyprint import HTML
from xhtml2pdf import pisa
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import base64
from pypdf import PdfReader, PdfWriter
from rest_framework.request import Request
from dynamic_report_service.utils import image_url_to_base64
from dynamic_report_service.views import (
    GenerateTreatmentReport,
    PurchaseTreatmentReport,
    fetch_resources,
)
from global_utils.service_treatments_map import SERVICE_TREATMENT_MAP
from oohy_product.custom_responses import ErrorResponse, StandardResponse
from pulse_payments.models import MinimumBalance, Service, Wallet
from pulse_service.models import ReportTask
from report_service.models import DiagnosisReportHistory, DiagnosticResource
from report_service.service_utils import get_services_for_history
from report_service.views import GenerateDiagnosisReport
from rest_framework.test import APIRequestFactory, force_authenticate
from django.utils.text import slugify

import uuid
from datetime import datetime


@method_decorator(xframe_options_exempt, name="dispatch")
class MergedPDFView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        logger = logging.getLogger(__name__)
        logger.info(
            f"🧑‍💻 User ID: {request.user.id}, 📞 Phone: {getattr(getattr(request.user, 'profile', None), 'phone_number', 'Unknown')}"
        )

        overall_start_time = time.time()
        timers = {}

        # ============================
        # Step 1: Parameter Validation & Initial Report History Retrieval
        step_start = time.time()
        report_history_id = request.query_params.get("report_history_id")
        if not report_history_id:
            return ErrorResponse(
                errors={"report_history_id": "This field is required."}, status_code=400
            )

        service_id = request.query_params.get("service_id")
        if not service_id:
            return ErrorResponse(
                errors={"service_id": "This field is required."}, status_code=400
            )

        # Convert to integer for ReportTask fields (and further usage)
        try:
            report_history_id_int = int(report_history_id)
            service_id_int = int(service_id)
        except ValueError:
            return ErrorResponse(
                errors={"error": "report_history_id and service_id must be integers."},
                status_code=400,
            )

        # Create ReportTask row with initial data
        task = ReportTask.objects.create(
            task_id=str(uuid.uuid4()),
            task_type="service",  # using the 'Service Report' type
            status="pending",
            history_id=report_history_id_int,
            service_id=service_id_int,
            language="en",
            started_at=datetime.now(),
        )

        try:
            # Try retrieving the report history
            report_history = get_object_or_404(
                DiagnosisReportHistory, report_history_id=report_history_id
            )
        except ValueError:
            task.status = "failure"
            task.completed_at = datetime.now()
            task.error_message = "Invalid report_history_id. It must be an integer."
            task.save()
            return ErrorResponse(
                errors={
                    "report_history_id": "Invalid report_history_id. It must be an integer."
                },
                status_code=400,
            )
        except Http404:
            task.status = "failure"
            task.completed_at = datetime.now()
            task.error_message = "Report history not found for the given ID."
            task.save()
            return ErrorResponse(
                errors={
                    "report_history_id": "Report history not found for the given ID."
                },
                status_code=404,
            )
        timers["parameter_validation"] = time.time() - step_start

        user = request.user
        wallet, created = Wallet.objects.get_or_create(user=user)
        minimum_balance_instance = get_object_or_404(MinimumBalance)
        minimum_balance = minimum_balance_instance.minimum_balance

        # Check wallet balance
        if wallet.balance <= minimum_balance:
            task.status = "failure"
            task.completed_at = datetime.now()
            task.error_message = f"Insufficient balance. Wallet must maintain a minimum balance of ₹{minimum_balance}."
            task.save()
            return ErrorResponse(
                errors={
                    "error": f"Insufficient balance. Wallet must maintain a minimum balance of ₹{minimum_balance}."
                },
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        diagnosis_report = get_object_or_404(
            DiagnosisReportHistory, report_history_id=report_history_id
        )

        try:
            service = Service.objects.get(service_id=service_id)
        except Service.DoesNotExist:
            task.status = "failure"
            task.completed_at = datetime.now()
            task.error_message = f"Invalid service_id: {service_id}"
            task.save()
            return ErrorResponse(
                errors={"message": f"Invalid service_id: {service_id}"},
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        treatment_field = SERVICE_TREATMENT_MAP.get(str(service_id))
        if treatment_field and getattr(diagnosis_report, treatment_field, None):
            task.status = "failure"
            task.completed_at = datetime.now()
            task.error_message = (
                f"{service.name} has already been purchased for this report."
            )
            task.save()
            return ErrorResponse(
                errors={
                    "message": f"{service.name} has already been purchased for this report."
                },
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # ============================
        # Step 2: Generate Treatment Report
        step_start = time.time()
        all_context = {"sections": []}
        treatment_report_view = GenerateTreatmentReport()
        rf = APIRequestFactory()
        wsgi_request = rf.get(
            "/api/v1/dynamic-report-service/generate-treatment-report/",
            {"report_history_id": report_history_id, "service_id": service_id},
        )
        treatment_request = Request(wsgi_request)
        treatment_response = treatment_report_view.get(treatment_request)

        treatment_filtered_data = treatment_response.data.get("data", {}).get(
            "data", [{}]
        )
        if not treatment_filtered_data:
            task.status = "failure"
            task.completed_at = datetime.now()
            task.error_message = f"No data found for service_id {service_id}."
            task.save()
            return ErrorResponse(
                errors={"treatment": f"No data found for service_id {service_id}."},
                status_code=404,
            )
        all_context["sections"].extend(
            treatment_filtered_data
            if isinstance(treatment_filtered_data, list)
            else [treatment_filtered_data]
        )
        timers["treatment_report_generation"] = time.time() - step_start
        
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

        patient_first_name = patient.first_name if patient else "Unknown Patient"
        patient_last_name = patient.last_name if patient else "Unknown Patient"

        patient_name_pdf = f"{patient_first_name} {patient_last_name}"

        all_context["sections"][0]["section_metadata"]["patient_name"] = patient_name_pdf
        # ============================
        # Step 3: Process Images (Convert URLs to Base64)
        step_start = time.time()
        for section in all_context["sections"]:
            for content in section["content"]:
                if content["type"] == "image":
                    image_url = content["value"]
                    content["value"] = image_url_to_base64(image_url)
        timers["image_processing"] = time.time() - step_start

        try:
            # ============================
            # Step 4: Render HTML and Generate Treatment PDF
            step_start = time.time()
            html_template = "diagnostic_resource_weasyprint2.html"
            # Render HTML content from the context
            html_content = render_to_string(html_template, all_context)

            base_url = request.build_absolute_uri(
                "/"
            )  # ensures that static files can be located

            pdf_file = BytesIO()
            HTML(string=html_content, base_url=base_url).write_pdf(target=pdf_file)
            pdf_file.seek(0)

            treatment_pdf_content = pdf_file.getvalue()
            timers["html_render_and_pdf_generation"] = time.time() - step_start

            # ============================
            # Step 5: Retrieve Diagnostic PDF
            step_start = time.time()
            try:
                report_history = get_object_or_404(
                    DiagnosisReportHistory, report_history_id=report_history_id
                )
            except ValueError:
                task.status = "failure"
                task.completed_at = datetime.now()
                task.error_message = "Invalid report_history_id. It must be an integer."
                task.save()
                return ErrorResponse(
                    errors={
                        "report_history_id": "Invalid report_history_id. It must be an integer."
                    },
                    status_code=400,
                )
            except Http404:
                task.status = "failure"
                task.completed_at = datetime.now()
                task.error_message = "Report history not found for the given ID."
                task.save()
                return ErrorResponse(
                    errors={
                        "report_history_id": "Report history not found for the given ID."
                    },
                    status_code=404,
                )

            diagnostic_pdf_url = report_history.pdf_url
            diagnostic_response = requests.get(diagnostic_pdf_url)
            if diagnostic_response.status_code != 200:
                task.status = "failure"
                task.completed_at = datetime.now()
                task.error_message = "Could not retrieve diagnostic PDF."
                task.save()
                return ErrorResponse(
                    errors={"diagnostic_pdf": "Could not retrieve diagnostic PDF."},
                    status_code=500,
                )
            diagnostic_pdf_bytes = BytesIO(diagnostic_response.content)
            diagnostic_pdf_reader = PdfReader(diagnostic_pdf_bytes)
            timers["diagnostic_pdf_retrieval"] = time.time() - step_start

            # ============================
            # Step 6: Merge PDFs (Diagnostic + Treatment)
            step_start = time.time()
            treatment_pdf_bytes = BytesIO(treatment_pdf_content)
            treatment_pdf_reader = PdfReader(treatment_pdf_bytes)
            pdf_writer = PdfWriter()

            for page in diagnostic_pdf_reader.pages:
                pdf_writer.add_page(page)
            for page in treatment_pdf_reader.pages:
                pdf_writer.add_page(page)

            merged_pdf_bytes = BytesIO()
            pdf_writer.write(merged_pdf_bytes)
            merged_pdf_bytes.seek(0)
            merged_pdf_content = merged_pdf_bytes.getvalue()
            timers["pdf_merging"] = time.time() - step_start

            # ============================
            # Step 7: Upload Merged PDF to AWS S3
            step_start = time.time()
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

            

            # Create the filename using the patient name and the current date and time.
            file_name = f"{patient_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            s3_key = f"temp_reports/{file_name}"
            s3_client.put_object(
                Bucket=AWS_STORAGE_BUCKET_NAME,
                Key=s3_key,
                Body=merged_pdf_content,
                ContentType="application/pdf",
            )

            new_download_url = f"https://{AWS_STORAGE_BUCKET_NAME}.s3.{AWS_S3_REGION_NAME}.amazonaws.com/{s3_key}"
            timers["s3_upload"] = time.time() - step_start

            # ============================
            # Step 8: Update DB with New PDF URL
            step_start = time.time()
            service_id_int = int(service_id)
            if service_id_int == 3:

                # If service_id equals 3, update single_seed_page_number with the page number where
                # treatment pages start. This is diagnostic PDF's page count plus one.
                diagnostic_page_count = len(diagnostic_pdf_reader.pages)
                report_history.single_seed_page_number = diagnostic_page_count + 1

            report_history.flag = 1

            report_history.pdf_url = new_download_url
            report_history.download_pdf = new_download_url
            report_history.save()
            timers["db_update"] = time.time() - step_start

            overall_execution_time = time.time() - overall_start_time

            diagnosis_report = get_object_or_404(
                DiagnosisReportHistory, report_history_id=report_history_id
            )

            pdf_report_response = {
                "status": "success",
                "data": {"pdf_url": new_download_url},
                "message": "PDF generated successfully.",
            }

            factory = APIRequestFactory()
            purchase_data = {
                "report_history_id": report_history_id,
                "service_id": service_id,
            }
            purchase_request = factory.post(
                "/api/v1/dynamic-report-service/purchase-treatment-report/",
                purchase_data,
                format="json",
            )
            purchase_request.is_superuser = request.user.is_superuser
            force_authenticate(purchase_request, user=request.user)

            purchase_response = PurchaseTreatmentReport.as_view()(purchase_request)

            if purchase_response.status_code != 200:
                task.status = "failure"
                task.completed_at = datetime.now()
                task.error_message = "Purchase treatment report failed."
                task.save()
                return purchase_response

            wallet_deduction_response = purchase_response.data.get("data", {}).get(
                "wallet_deduction_response"
            )
            services_with_purchased_status = get_services_for_history(report_history_id)

            # Mark the task as successful
            task.status = "success"
            task.completed_at = datetime.now()
            task.save()

            return StandardResponse(
                data={
                    "services": services_with_purchased_status,
                    "pdf_report_response": pdf_report_response,
                    "wallet_response": wallet_deduction_response,
                },
                message="Merged PDF generated successfully.",
                status_code=200,
            )

        except ClientError as e:
            task.status = "failure"
            task.completed_at = datetime.now()
            task.error_message = str(e)
            task.save()
            return ErrorResponse(errors={"s3": str(e)}, status_code=500)
        except Exception as e:
            task.status = "failure"
            task.completed_at = datetime.now()
            task.error_message = str(e)
            task.save()
            return ErrorResponse(errors={"general": str(e)}, status_code=500)


@method_decorator(xframe_options_exempt, name="dispatch")
class MergedPDFDownloadView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Start overall timer
        overall_start_time = time.time()
        timers = {}

        # ============================
        # Step 1: Parameter Validation & Initial Report History Retrieval
        step_start = time.time()
        report_history_id = request.query_params.get("report_history_id")
        if not report_history_id:
            return ErrorResponse(
                errors={"report_history_id": "This field is required."}, status_code=400
            )

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
        timers["parameter_validation"] = time.time() - step_start

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
                item
                for item in purchased_service_ids
                if item in service_ids and item != 3
            ]

        # ============================
        # Step 2: Generate Treatment Report
        step_start = time.time()
        all_context = {"sections": []}
        treatment_report_view = GenerateTreatmentReport()
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
        timers["treatment_report_generation"] = time.time() - step_start

        # ============================
        # Step 3: Process Images (Convert URLs to Base64)
        step_start = time.time()
        for section in all_context["sections"]:
            for content in section["content"]:
                if content["type"] == "image":
                    image_url = content["value"]
                    content["value"] = image_url_to_base64(image_url)
        timers["image_processing"] = time.time() - step_start

        try:
            # ============================
            # Step 4: Render HTML and Generate Treatment PDF
            step_start = time.time()
            html_content = render_to_string(
                "diagnostic_resource_pdf2.html", all_context
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
            treatment_pdf_content = pdf_file.getvalue()
            timers["html_render_and_pdf_generation"] = time.time() - step_start

            # ============================
            # Step 5: Retrieve Diagnostic PDF
            step_start = time.time()
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
            diagnostic_pdf_url = report_history.download_pdf
            diagnostic_response = requests.get(diagnostic_pdf_url)
            if diagnostic_response.status_code != 200:
                return ErrorResponse(
                    errors={"diagnostic_pdf": "Could not retrieve diagnostic PDF."},
                    status_code=500,
                )
            diagnostic_pdf_bytes = BytesIO(diagnostic_response.content)
            diagnostic_pdf_reader = PdfReader(diagnostic_pdf_bytes)
            timers["diagnostic_pdf_retrieval"] = time.time() - step_start

            # ============================
            # Step 6: Merge PDFs (Diagnostic + Treatment)
            step_start = time.time()
            treatment_pdf_bytes = BytesIO(treatment_pdf_content)
            treatment_pdf_reader = PdfReader(treatment_pdf_bytes)
            pdf_writer = PdfWriter()

            # Add all pages from the diagnostic PDF.
            for page in diagnostic_pdf_reader.pages:
                pdf_writer.add_page(page)
            # Add all pages from the treatment PDF.
            for page in treatment_pdf_reader.pages:
                pdf_writer.add_page(page)

            merged_pdf_bytes = BytesIO()
            pdf_writer.write(merged_pdf_bytes)
            merged_pdf_bytes.seek(0)
            merged_pdf_content = merged_pdf_bytes.getvalue()
            timers["pdf_merging"] = time.time() - step_start

            # ============================
            # Step 7: Upload Merged PDF to AWS S3
            step_start = time.time()
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

            merged_file_name = (
                f"MergedDiagnosticReport_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            )
            s3_key = f"temp_reports/{merged_file_name}"
            s3_client.put_object(
                Bucket=AWS_STORAGE_BUCKET_NAME,
                Key=s3_key,
                Body=merged_pdf_content,
                ContentType="application/pdf",
            )

            new_download_url = f"https://{AWS_STORAGE_BUCKET_NAME}.s3.{AWS_S3_REGION_NAME}.amazonaws.com/{s3_key}"
            timers["s3_upload"] = time.time() - step_start

            # ============================
            # Step 8: Update DB with New PDF URL
            step_start = time.time()
            report_history.pdf_url = new_download_url
            report_history.save()
            timers["db_update"] = time.time() - step_start

            # End overall timer.
            overall_execution_time = time.time() - overall_start_time

            diagnosis_report = get_object_or_404(
                DiagnosisReportHistory, report_history_id=report_history_id
            )

            # Constructing the response dictionary
            pdf_report_response = {
                "status": "success",
                "data": {
                    "pdf_url": new_download_url  # Assuming pdf_url is a field in your model
                },
                "message": "PDF generated successfully.",
            }

            # Return the new download URL along with overall and step timings.
            return StandardResponse(
                data={
                    "pdf_url": pdf_report_response,
                    # "execution_time": overall_execution_time,  # Total time in seconds
                    # "step_timings": timers  # Individual step times
                },
                message="Merged PDF generated successfully.",
                status_code=200,
            )

        except ClientError as e:
            return ErrorResponse(errors={"s3": str(e)}, status_code=500)
        except Exception as e:
            return ErrorResponse(errors={"general": str(e)}, status_code=500)


class DownloadReportPDFView(APIView):
    """
    API endpoint which:
      - Checks if a report's single_seed_page_number is set.
      - Downloads the PDF from the report's download_pdf URL.
      - Deletes the page corresponding to single_seed_page_number.
      - Sets single_seed_page_number to None.
      - Uploads the modified PDF to AWS S3.
      - Updates the download_pdf URL in the database.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Retrieve report_history_id from query parameters.
        report_history_id = request.query_params.get("report_history_id")
        if not report_history_id:
            return ErrorResponse(
                errors={"report_history_id": "This field is required."}, status_code=400
            )

        # Get the DiagnosisReportHistory record.
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

        if report_history.flag == 0:
            return StandardResponse(
                data={"pdf_url": report_history.download_pdf},
                message="PDF updated successfully after deleting the specified single seed page.",
                status_code=200,
            )

        # If no single_seed_page_number exists, return the existing download URL.
        if report_history.single_seed_page_number is None:
            return StandardResponse(
                data={"pdf_url": report_history.download_pdf},
                message="No single seed page specified. No modifications were made.",
                status_code=200,
            )

        # Retrieve the current PDF from the download_pdf URL.
        current_pdf_url = report_history.download_pdf
        pdf_response = requests.get(current_pdf_url)
        if pdf_response.status_code != 200:
            return ErrorResponse(
                errors={"pdf": "Could not retrieve the current PDF."}, status_code=500
            )
        pdf_bytes = BytesIO(pdf_response.content)

        # Read the PDF.
        pdf_reader = PdfReader(pdf_bytes)
        pdf_writer = PdfWriter()
        total_pages = len(pdf_reader.pages)

        # Validate that the one-indexed page number is valid.
        if (
            report_history.single_seed_page_number < 1
            or report_history.single_seed_page_number > total_pages
        ):

            return ErrorResponse(
                errors={
                    "single_seed_page_number": "Invalid page number specified in single_seed_page_number."
                },
                status_code=400,
            )

        # Convert the 1-indexed page number to zero-index.
        page_to_remove_index = report_history.single_seed_page_number - 1

        # Copy all pages except the page to be deleted.
        for idx, page in enumerate(pdf_reader.pages):
            if idx == page_to_remove_index:
                continue  # Skip the page to remove.
            pdf_writer.add_page(page)

        # Write the modified PDF to a new buffer.
        new_pdf_buffer = BytesIO()
        pdf_writer.write(new_pdf_buffer)
        new_pdf_buffer.seek(0)
        new_pdf_content = new_pdf_buffer.getvalue()

        # Upload the modified PDF to AWS S3.
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

        s3_key = f"temp_reports/{file_name}"
        s3_client.put_object(
            Bucket=AWS_STORAGE_BUCKET_NAME,
            Key=s3_key,
            Body=new_pdf_content,
            ContentType="application/pdf",
        )
        new_download_url = f"https://{AWS_STORAGE_BUCKET_NAME}.s3.{AWS_S3_REGION_NAME}.amazonaws.com/{s3_key}"

        # Update the record: clear single_seed_page_number and update download_pdf.
        report_history.download_pdf = new_download_url
        report_history.flag = 0
        report_history.save()

        return StandardResponse(
            data={"pdf_url": new_download_url},
            message="PDF updated successfully after deleting the specified single seed page.",
            status_code=200,
        )
