import os
import random
import logging

from django.conf import settings
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory, force_authenticate
from rest_framework.views import APIView
import uuid
from datetime import datetime
import time
from dynamic_report_service.views import ReportPDFView
from global_utils.analyse_pulse_filename import generate_analyse_pulse_filename
from oohy_product.custom_responses import ErrorResponse, StandardResponse
from patients.models import PatientsModel
from pulse_payments.models import MinimumBalance, Wallet
from pulse_payments.views import DeductFromWalletAPIView, ServiceListAPIView
from report_service.models import (
    DiagnosisAnswer,
    DiagnosisReportHistory,
    DiagnosticResource,
    Patterns,
    SymptomsQuestions,
)
from report_service.views import (
    GenerateDiagnosisReport,
    CreateDiagnosisHistory,
    GetQuestionsByReportHistoryAPIView,
)
from signal_processing.five_elements_calculate import decision_making, decision_making1
from signal_processing.relevent_questions import get_relevant_questions
from signal_processing.validate_pulse import check_pulse_validation
from .models import PulseDataObservations, PulseData, QuestionsTable, ReportTask
from .serializers import (
    PulseDataObservationsSerializer,
    PulseDataSymptomsSerializer,
    PulseLogSerializer,
)

from .utils import (
    Question_Based,
    deduct_from_wallet,
    generate_diagnosis_report,
    generate_report_pdf,
    get_service_list,
    insert_processed_report_id,
    insert_processed_report_id1,
    rearrange_five_elements,
    upload_to_backblaze,
)  # Import the new database-saving function


class PreAnalysePulseView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        logger = logging.getLogger(__name__)
        logger.info(
            f"🧑‍💻 User ID: {request.user.id}, 📞 Phone: {getattr(getattr(request.user, 'profile', None), 'phone_number', 'Unknown')}"
        )

        try:
            # Get signal_data and patient_id from the request
            signal_data = request.data.get("signal_data")
            patient_id = request.data.get("patient_id")
            language = (
                request.data.get("language", "English").strip().lower() or "english"
            )

            if not signal_data:
                return ErrorResponse(
                    errors={"signal_data": "Signal data is required."}, status_code=400
                )

            if not patient_id:
                return ErrorResponse(
                    errors={"patient_id": "Patient ID is required."}, status_code=400
                )

            # Fetch the patient, ensuring it belongs to the current user
            patient = PatientsModel.objects.filter(id=patient_id).first()
            if not patient or patient.user_profile != request.user:
                logger.error(
                    f"❌ Patient not found or does not belong to user_id={request.user.id}"
                )
                return ErrorResponse(
                    errors={
                        "patient": "Patient not found or does not belong to the current user."
                    },
                    status_code=404,
                )

            user = request.user
            wallet, created = Wallet.objects.get_or_create(user=user)
            # Fetch the dynamic minimum balance
            minimum_balance_instance = get_object_or_404(MinimumBalance)

            # Assign the actual balance value to a variable.
            minimum_balance = minimum_balance_instance.minimum_balance

            # Check if sufficient balance exists, considering the minimum balance requirement
            if wallet.balance <= minimum_balance:
                return ErrorResponse(
                    errors={
                        "error": f"Insufficient balance. Wallet must maintain a minimum balance of ₹{minimum_balance}."
                    },
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            # Validate the pulse
            if not check_pulse_validation(signal_data):
                return ErrorResponse(
                    errors={"pulse_validation": "Please retake the pulse"},
                    status_code=400,
                )

            # Generate and save signal data to a file
            filename = generate_analyse_pulse_filename(patient_id, request.user.id)
            file_path = os.path.join(settings.BASE_DIR, "pulse_data", filename).replace(
                "\\", "/"
            )
            os.makedirs(os.path.dirname(file_path), exist_ok=True)

            with open(file_path, "w") as file:
                file.write(signal_data)

            # Upload file to Backblaze
            with open(file_path, "rb") as file_to_upload:
                pulse_uri = upload_to_backblaze(file_to_upload, filename)

            # Remove the local file after uploading
            os.remove(file_path)

            # Save pulse data to the database
            pulse = PulseData.objects.create(
                pulse_uri=pulse_uri,
                signal_data=signal_data,
                patient=patient,
                user=request.user,
            )
            pulse_id = pulse.id

            # Decision-making
            decision = decision_making(signal_data)

            if not decision:
                return ErrorResponse(
                    errors={"pulse_validation": "Please retake the pulse"},
                    status_code=400,
                )

            # Extract primary, secondary, and tertiary values from the decision result.
            primary = decision.get("primary", "").split("_")[0].lower()
            secondary = decision.get("secondary", "").split("_")[0].lower()
            tertiary = decision.get("tertiary", "").split("_")[0].lower()

            # Query the Patterns model using the extracted values.
            pattern_instance = Patterns.objects.filter(
                primary__iexact=primary,
                secondary__iexact=secondary,
                tertiary__iexact=tertiary,
            ).first()

            if pattern_instance:
                pattern_number = pattern_instance.pattern_number
            else:
                # Optionally, handle the case where no matching pattern is found.
                pattern_number = None
                print("No matching pattern found for the given signal data.")

            # You can now use pattern_number to fetch a DiagnosticResource instance
            # For example:
            if pattern_number is not None:
                diagnostic_instance = DiagnosticResource.objects.filter(
                    pattern_number=pattern_number
                ).first()

            # pattern_number = 1
            # print(135, pattern_number)
            try:
                pattern_type = DiagnosticResource.objects.get(
                    pattern_number=pattern_number
                )
            except DiagnosticResource.DoesNotExist:
                return ErrorResponse(
                    errors={"pattern_type": "No matching diagnostic resource found."},
                    status_code=404,
                )

            if not pattern_type:
                return ErrorResponse(
                    errors={"pattern_type": "No matching diagnostic resource found."},
                    status_code=404,
                )

            factory = APIRequestFactory()

            # Call CreateDiagnosisHistory to save the report history
            diagnosis_report_history_request_data = {
                "patient_id": pulse.patient.id,
                "primary": decision["primary"],
                "secondary": decision["secondary"],
                "tertiary": decision["tertiary"],
                "quaternary": decision["quaternary"],
                "quinary": decision.get("quinary", None),
                "carbohydrate": decision.get("carbohydrate", None),
                "protein": decision.get("protein", None),
                "fat": decision.get("fat", None),
                "wind_yin": decision.get("wind_yin", None),
                "wind_yang": decision.get("wind_yang", None),
                "heat_yin": decision.get("heat_yin", None),
                "heat_yang": decision.get("heat_yang", None),
                "humid_yin": decision.get("humid_yin", None),
                "humid_yang": decision.get("humid_yang", None),
                "dry_yin": decision.get("dry_yin", None),
                "dry_yang": decision.get("dry_yang", None),
                "cold_yin": decision.get("cold_yin", None),
                "cold_yang": decision.get("cold_yang", None),
                "vata": decision.get("vata", None),
                "pitta": decision.get("pitta", None),
                "kapha": decision.get("kapha", None),
                "heart_rate": decision.get("heart_rate", None),
                "heart_yin": decision.get("heart_yin", None),
                "pulse_id": pulse_id,
                "report_pattern_type": pattern_type.pattern_number,
            }

            diagnosis_report_history_request = factory.post(
                "/diagnosis-report-history/",
                diagnosis_report_history_request_data,
                format="json",
            )
            force_authenticate(diagnosis_report_history_request, user=request.user)

            diagnosis_report_history_response = CreateDiagnosisHistory.as_view()(
                diagnosis_report_history_request
            )
            if diagnosis_report_history_response.status_code != 201:
                return ErrorResponse(
                    errors={
                        "message": "Failed to create diagnosis report history.",
                        "details": diagnosis_report_history_response.data,
                    },
                    status_code=diagnosis_report_history_response.status_code,
                )

            # Call GetQuestionsByReportHistoryAPIView with the created report_history_id
            report_history_id = diagnosis_report_history_response.data.get(
                "data", {}
            ).get("report_history_id")

            if not report_history_id:
                return ErrorResponse(
                    errors={
                        "report_history_id": "Diagnosis report history id not found."
                    },
                    status_code=500,
                )

            questions_request_data = {
                "report_history_id": report_history_id,
                "language": language,
            }
            questions_request = factory.post(
                "/get-questions-by-report-history/",
                questions_request_data,
                format="json",
            )
            force_authenticate(questions_request, user=request.user)
            questions_response = GetQuestionsByReportHistoryAPIView.as_view()(
                questions_request
            )
            if questions_response.status_code != 200:
                return ErrorResponse(
                    errors={
                        "message": "Failed to get questions by report history.",
                        "details": questions_response.data,
                    },
                    status_code=questions_response.status_code,
                )

            return StandardResponse(
                data={
                    "message": "Pulse analysis, diagnosis report, and report history successfully processed.",
                    "diagnosis_report_history": diagnosis_report_history_response.data,
                    "questions": questions_response.data,
                    "pulse_id": pulse_id,
                },
                message="Pulse analysis completed successfully.",
                status_code=200,
            )

        except Exception as e:
            return ErrorResponse(errors={"error": str(e)}, status_code=500)


class PostAnalysePulseView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        logger = logging.getLogger(__name__)
        logger.info(
            f"🧑‍💻 User ID: {request.user.id}, 📞 Phone: {getattr(getattr(request.user, 'profile', None), 'phone_number', 'Unknown')}"
        )

        # Initialize task variable
        task = None
        try:
            timing = {}
            extraction_start = time.time()
            report_history_id = request.data.get("report_hystory_id")
            if not report_history_id:
                return ErrorResponse(
                    errors={"report_hystory_id": "Report history ID is required."},
                    status_code=400,
                )

            language = request.data.get("language", "").strip().lower()
            if not language:
                language = "eng"

            # Convert report_history_id to integer
            try:
                report_history_id_int = int(report_history_id)
            except ValueError:
                return ErrorResponse(
                    errors={"report_hystory_id": "Invalid report history ID."},
                    status_code=400,
                )

            # Create a ReportTask record for the PDF task.
            task = ReportTask.objects.create(
                task_id=str(uuid.uuid4()),
                task_type="pdf",  # task type is pdf
                status="pending",
                history_id=report_history_id_int,
                language="en",
                started_at=datetime.now(),
            )

            answers = request.data.get("answers")
            if not answers:
                task.status = "failure"
                task.completed_at = datetime.now()
                task.error_message = "Answers are required."
                task.save()
                return ErrorResponse(
                    errors={"answers": "Answers are required."}, status_code=400
                )

            try:
                history_instance = DiagnosisReportHistory.objects.get(
                    report_history_id=report_history_id
                )
            except DiagnosisReportHistory.DoesNotExist:
                task.status = "failure"
                task.completed_at = datetime.now()
                task.error_message = "Diagnosis report history not found."
                task.save()
                return ErrorResponse(
                    errors={"report_hystory_id": "Diagnosis report history not found."},
                    status_code=404,
                )

            pulse_id = history_instance.pulse_id_id
            patient_id = history_instance.patient_id_id

            if not pulse_id or not patient_id:
                task.status = "failure"
                task.completed_at = datetime.now()
                task.error_message = (
                    "Pulse ID or Patient ID not found in diagnosis report history."
                )
                task.save()
                return ErrorResponse(
                    errors={
                        "data": "Pulse ID or Patient ID not found in diagnosis report history."
                    },
                    status_code=500,
                )
            extraction_end = time.time()
            timing["data_extraction"] = extraction_end - extraction_start

            # Initialize the request factory
            factory = APIRequestFactory()

            # --- Step 3: Service List Call ---
            service_start = time.time()
            service_response = get_service_list(request)
            service_end = time.time()
            timing["service_list_call"] = service_end - service_start

            if service_response.status_code != 200:
                task.status = "failure"
                task.completed_at = datetime.now()
                task.error_message = (
                    f"Failed to fetch service list. Details: {service_response.data}"
                )
                task.save()
                return ErrorResponse(
                    errors={
                        "message": "Failed to fetch service list.",
                        "details": service_response.data,
                    },
                    status_code=service_response.status_code,
                )

            # --- Step 4: Save "Yes" Answers ---
            save_answers_start = time.time()
            for cycle, question_list in answers.items():
                for question_item in question_list:
                    question_id = question_item.get("question_id")
                    answer_value = question_item.get("answer")
                    # Process only answers that are "Yes"
                    if answer_value != "Yes":
                        continue
                    if not question_id:
                        continue
                    try:
                        symptom_question = SymptomsQuestions.objects.get(
                            question_number=question_id
                        )
                    except SymptomsQuestions.DoesNotExist:
                        continue
                    exists = DiagnosisAnswer.objects.filter(
                        diagnosis_report_history=history_instance,
                        symptom_question=symptom_question,
                    ).exists()
                    if exists:
                        continue
                    DiagnosisAnswer.objects.create(
                        diagnosis_report_history=history_instance,
                        symptom_question=symptom_question,
                        answer=answer_value,
                    )
            save_answers_end = time.time()
            timing["save_answers"] = save_answers_end - save_answers_start

            # Call rearrange_five_elements to get the mapping
            new_mapping = rearrange_five_elements(
                report_history_id, answers, request.user
            )
            primary = new_mapping.get("primary", "")
            secondary = new_mapping.get("secondary", "")
            tertiary = new_mapping.get("tertiary", "")
            seed_organ = new_mapping.get("Organ", "")
            seed_yin_yang = new_mapping.get("Yin_Yang", "")

            # print(442)
            # Call Question_Based function to get mapping dataframe
            mapping_df = Question_Based(primary, secondary, tertiary)

            try:
                with transaction.atomic():  # <- add this inner atomic block
                    updated_instance = insert_processed_report_id1(
                        report_history_id, mapping_df, seed_organ, seed_yin_yang
                    )
            except Exception as e:
                task.status = "failure"
                task.completed_at = datetime.now()
                task.error_message = f"Failed to insert processed report: {str(e)}"
                task.save()
                return ErrorResponse(
                    errors={
                        "message": "Failed to insert processed report",
                        "details": str(e),
                    },
                    status_code=500,
                )
            # print(448)
            # --- Step 2: Generate Diagnosis Report ---
            diagnosis_start = time.time()
            diagnosis_response = generate_diagnosis_report(
                request, updated_instance.report_history_id, answers
            )
            diagnosis_end = time.time()
            timing["diagnosis_report_generation"] = diagnosis_end - diagnosis_start
            # print(456)
            if diagnosis_response.status_code != 200:
                task.status = "failure"
                task.completed_at = datetime.now()
                task.error_message = f"Failed to generate diagnosis report. Details: {diagnosis_response.data}"
                task.save()
                return ErrorResponse(
                    errors={
                        "message": "Failed to generate diagnosis report.",
                        "details": diagnosis_response.data,
                    },
                    status_code=diagnosis_response.status_code,
                )

            # --- Step 2b: Generate PDF Report ---
            pdf_start = time.time()
            # print(language)
            report_pdf_response = generate_report_pdf(
                request,
                updated_instance.report_history_id,
                language,
            )
            pdf_end = time.time()
            timing["pdf_report_generation"] = pdf_end - pdf_start

            if report_pdf_response.status_code != 200:
                task.status = "failure"
                task.completed_at = datetime.now()
                task.error_message = f"Failed to generate diagnosis report PDF. Details: {report_pdf_response.data}"
                task.save()
                return ErrorResponse(
                    errors={
                        "message": "Failed to generate diagnosis report PDF.",
                        "details": report_pdf_response.data,
                    },
                    status_code=report_pdf_response.status_code,
                )

            # Update the processed report instance with the PDF URL.
            updated_instance.pdf_url = report_pdf_response.data["data"]["pdf_url"]
            updated_instance.download_pdf = report_pdf_response.data["data"]["pdf_url"]
            updated_instance.save()

            # --- Step 1: Deduct from Wallet ---
            wallet_start = time.time()
            wallet_response = deduct_from_wallet(
                request, pulse_id, patient_id, updated_instance.report_history_id
            )
            wallet_end = time.time()
            timing["wallet_deduction"] = wallet_end - wallet_start

            if wallet_response.status_code != 200:
                task.status = "failure"
                task.completed_at = datetime.now()
                task.error_message = (
                    f"Failed to deduct from wallet. Details: {wallet_response.data}"
                )
                task.save()
                return ErrorResponse(
                    errors={
                        "message": "Failed to deduct from wallet.",
                        "details": wallet_response.data,
                    },
                    status_code=wallet_response.status_code,
                )

            response_data = {
                "message": "Diagnosis report generated and wallet deducted successfully.",
                "pdf_report_response": report_pdf_response.data,
                "service_response": service_response.data,
                "wallet_response": wallet_response.data,
                "diagnosis_report_history": {
                    "status": "success",
                    "data": {"report_history_id": updated_instance.report_history_id},
                },
                "nwe_mapping": new_mapping,
                "timing": timing,
            }

            # Update ReportTask as successful.
            task.status = "success"
            task.completed_at = datetime.now()
            task.save()

            return StandardResponse(
                data=response_data,
                message="Post analysis completed successfully.",
                status_code=200,
            )

        except Exception as e:
            if task:
                task.status = "failure"
                task.completed_at = datetime.now()
                task.error_message = str(e)
                task.save()
            return ErrorResponse(errors={"error": str(e)}, status_code=500)


class AnalysePulseView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        try:
            # Get signal_data and patient_id from the request
            signal_data = request.data.get("signal_data")
            patient_id = request.data.get("patient_id")

            if not signal_data:
                return ErrorResponse(
                    errors={"signal_data": "Signal data is required."}, status_code=400
                )

            if not patient_id:
                return ErrorResponse(
                    errors={"patient_id": "Patient ID is required."}, status_code=400
                )

            # Fetch the patient, ensuring it belongs to the current user
            patient = PatientsModel.objects.filter(id=patient_id).first()
            if not patient or patient.user_profile != request.user:
                return ErrorResponse(
                    errors={
                        "patient": "Patient not found or does not belong to the current user."
                    },
                    status_code=404,
                )

            # Validate the pulse
            if not check_pulse_validation(signal_data):
                return ErrorResponse(
                    errors={"pulse_validation": "Please retake the pulse"},
                    status_code=400,
                )

            # Generate and save signal data to a file
            filename = generate_analyse_pulse_filename(patient_id, request.user.id)
            file_path = os.path.join(settings.BASE_DIR, "pulse_data", filename).replace(
                "\\", "/"
            )
            os.makedirs(os.path.dirname(file_path), exist_ok=True)

            with open(file_path, "w") as file:
                file.write(signal_data)

            # Upload file to Backblaze
            with open(file_path, "rb") as file_to_upload:
                pulse_uri = upload_to_backblaze(file_to_upload, filename)

            # Remove the local file after uploading
            os.remove(file_path)

            # Save pulse data to the database
            pulse = PulseData.objects.create(
                pulse_uri=pulse_uri,
                signal_data=signal_data,
                patient=patient,
                user=request.user,
            )

            pulse_id = pulse.id

            # Decision-making
            decision = decision_making(signal_data)

            # Extract primary, secondary, and tertiary values from the decision result.
            primary = decision.get("primary", "").split("_")[0].lower()
            secondary = decision.get("secondary", "").split("_")[0].lower()
            tertiary = decision.get("tertiary", "").split("_")[0].lower()

            # Query the Patterns model using the extracted values.
            pattern_instance = Patterns.objects.filter(
                primary__iexact=primary,
                secondary__iexact=secondary,
                tertiary__iexact=tertiary,
            ).first()

            if pattern_instance:
                pattern_number = pattern_instance.pattern_number
            else:
                # Optionally, handle the case where no matching pattern is found.
                pattern_number = None
                print("No matching pattern found for the given signal data.")

            # You can now use pattern_number to fetch a DiagnosticResource instance
            # For example:
            if pattern_number is not None:
                diagnostic_instance = DiagnosticResource.objects.filter(
                    pattern_number=pattern_number
                ).first()

            pattern_number = 1

            try:
                pattern_type = DiagnosticResource.objects.get(
                    pattern_number=pattern_number
                )
            except DiagnosticResource.DoesNotExist:
                return ErrorResponse(
                    errors={"pattern_type": "No matching diagnostic resource found."},
                    status_code=404,
                )

            if not pattern_type:
                return ErrorResponse(
                    errors={"pattern_type": "No matching diagnostic resource found."},
                    status_code=404,
                )

            # Prepare request data for GenerateDiagnosisReport as query parameters
            diagnosis_query_params = {
                "primary": decision["primary"],
                "secondary": decision["secondary"],
                "tertiary": decision["tertiary"],
                "quaternary": decision["quaternary"],
                "quinary": decision["quinary"],
            }

            factory = APIRequestFactory()
            diagnosis_request = factory.get(
                "/generate-diagnosis-report/", data=diagnosis_query_params
            )
            force_authenticate(diagnosis_request, user=request.user)

            diagnosis_response = GenerateDiagnosisReport.as_view()(diagnosis_request)

            if diagnosis_response.status_code != 200:
                return ErrorResponse(
                    errors={
                        "message": "Failed to generate diagnosis report.",
                        "details": diagnosis_response.data,
                    },
                    status_code=diagnosis_response.status_code,
                )

            report_response = diagnosis_response.data

            # Call CreateDiagnosisHistory to save the report history
            diagnosis_report_history_request_data = {
                "patient_id": pulse.patient.id,
                "primary": decision["primary"],
                "secondary": decision["secondary"],
                "tertiary": decision["tertiary"],
                "quaternary": decision["quaternary"],
                "quinary": decision.get(
                    "quinary", None
                ),  # Ensure all fields are included
                "carbohydrate": decision.get("carbohydrate", None),
                "protein": decision.get("protein", None),
                "fat": decision.get("fat", None),
                "wind_yin": decision.get("wind_yin", None),
                "wind_yang": decision.get("wind_yang", None),
                "heat_yin": decision.get("heat_yin", None),
                "heat_yang": decision.get("heat_yang", None),
                "humid_yin": decision.get("humid_yin", None),
                "humid_yang": decision.get("humid_yang", None),
                "dry_yin": decision.get("dry_yin", None),
                "dry_yang": decision.get("dry_yang", None),
                "cold_yin": decision.get("cold_yin", None),
                "cold_yang": decision.get("cold_yang", None),
                "vata": decision.get("vata", None),
                "pitta": decision.get("pitta", None),
                "kapha": decision.get("kapha", None),
                "heart_rate": decision.get("heart_rate", None),
                "heart_yin": decision.get("heart_yin", None),
                "pulse_id": pulse_id,
                "report_pattern_type": pattern_type.pattern_number,
            }

            diagnosis_report_history_request = factory.post(
                "/diagnosis-report-history/",
                diagnosis_report_history_request_data,
                format="json",
            )
            force_authenticate(diagnosis_report_history_request, user=request.user)

            diagnosis_report_history_response = CreateDiagnosisHistory.as_view()(
                diagnosis_report_history_request
            )

            if diagnosis_report_history_response.status_code != 201:
                return ErrorResponse(
                    errors={
                        "message": "Failed to create diagnosis report history.",
                        "details": diagnosis_report_history_response.data,
                    },
                    status_code=diagnosis_report_history_response.status_code,
                )

            # Call DeductFromWalletAPIView
            wallet_request_data = {
                "service_name_or_id": report_response.get("report", {}).get(
                    "primary", "Diagnosis Report"
                ),
                "pulse_id": pulse_id,
                "patient_id": patient_id,
            }

            wallet_request = factory.post(
                "/deduct-wallet/", wallet_request_data, format="json"
            )
            wallet_request.is_superuser = request.user.is_superuser
            force_authenticate(wallet_request, user=request.user)

            wallet_response = DeductFromWalletAPIView.as_view()(wallet_request)

            if wallet_response.status_code != 200:
                return ErrorResponse(
                    errors={
                        "message": "Failed to deduct from wallet.",
                        "details": wallet_response.data,
                    },
                    status_code=wallet_response.status_code,
                )

            return StandardResponse(
                data={
                    "message": "Pulse analysis, diagnosis report, wallet deduction, and report history successfully processed.",
                    "decision": decision,
                    "diagnosis_report": report_response,
                    "wallet_response": wallet_response.data,
                    "diagnosis_report_history": diagnosis_report_history_response.data,
                    "pulse_id": pulse_id,
                },
                message="Pulse analysis completed successfully.",
                status_code=200,
            )

        except Exception as e:
            return ErrorResponse(errors={"error": str(e)}, status_code=500)


class UploadObservationsView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pulse_id, *args, **kwargs):
        try:
            pulse = PulseData.objects.get(id=pulse_id)
        except PulseData.DoesNotExist:
            return ErrorResponse(
                errors={"error": f"PulseData with ID {pulse_id} does not exist."},
                status_code=404,
            )

        serializer = PulseDataObservationsSerializer(data=request.data)
        if serializer.is_valid():
            try:
                observation = serializer.save(pulse=pulse)
                return StandardResponse(
                    message="Observations uploaded successfully.",
                    data={"observation_id": observation.id},
                    status_code=201,
                )
            except IntegrityError:
                return ErrorResponse(
                    errors={"error": "An observation for this pulse already exists."},
                    status_code=400,
                )

        return ErrorResponse(errors=serializer.errors, status_code=400)

    def delete(self, request, pulse_id, *args, **kwargs):
        try:
            observation = PulseDataObservations.objects.get(pulse__id=pulse_id)
            observation.delete()
            return StandardResponse(
                message=f"Observation for pulse ID {pulse_id} deleted successfully.",
                data={"observation_id": observation.id},
                status_code=200,
            )
        except PulseDataObservations.DoesNotExist:
            return ErrorResponse(
                errors={"error": f"No observation found for pulse ID {pulse_id}."},
                status_code=404,
            )


class PulseDataSymptomsCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pulse_id):
        pulse = get_object_or_404(PulseData, id=pulse_id)

        if not isinstance(request.data, list):
            return ErrorResponse(
                errors={"error": "Data must be a list of symptom entries."},
                status_code=400,
            )

        results = []
        errors = []

        for entry in request.data:
            entry["pulse"] = pulse.id
            serializer = PulseDataSymptomsSerializer(data=entry)
            if serializer.is_valid():
                serializer.save()
                results.append(serializer.data)
            else:
                errors.append({"entry": entry, "errors": serializer.errors})

        if errors:
            return ErrorResponse(
                errors={"success": results, "errors": errors}, status_code=400
            )

        return StandardResponse(
            data={"success": results},
            message="Symptoms uploaded successfully.",
            status_code=201,
        )


class PulseLogView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = PulseLogSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()  # Save to database
            return StandardResponse(
                data=serializer.data,
                message="Pulse data successfully recorded.",
                status_code=status.HTTP_201_CREATED,
            )
        return ErrorResponse(
            errors=serializer.errors, status_code=status.HTTP_400_BAD_REQUEST
        )


class ChangePatternAPIView(APIView):
    def post(self, request, *args, **kwargs):
        data = request.data

        # Retrieve the report_history_id from the request.
        report_history_id = data.get("report_history_id")
        if not report_history_id:
            return ErrorResponse(
                errors="report_history_id is required.", status_code=400
            )
        try:
            diagnosis_report = DiagnosisReportHistory.objects.get(
                report_history_id=report_history_id
            )
        except DiagnosisReportHistory.DoesNotExist:
            return ErrorResponse(errors="Invalid report_history_id.", status_code=400)

        # Ensure exactly 6 answers are provided.
        answers = data.get("answers", {}).get("cycle_1", [])
        if len(answers) != 6:
            return ErrorResponse(
                errors="Exactly 6 answers are expected.", status_code=400
            )

        transformed = []
        # Process each answer: retrieve question details from the model,
        # set answer status, and assign an initial group ("pulse") based on index.
        for index, answer_obj in enumerate(answers):
            question_id = answer_obj.get("question_id")
            answer_value = answer_obj.get("answer", "")

            # Retrieve question details from SymptomsQuestions using question_number.
            question_instance = SymptomsQuestions.objects.filter(
                question_number=question_id, disable=False
            ).first()

            if question_instance:
                details = {
                    "question": question_instance.question_number,
                    "Energy": question_instance.yin_yang,  # "yin" or "yang"
                    "Organ": question_instance.organ,
                }
            else:
                details = {
                    "question": question_id,
                    "Energy": None,
                    "Organ": None,
                }

            # Determine answer status ("answered" if "Yes", otherwise "not answered").
            answer_status = (
                "answered" if answer_value.lower() == "yes" else "not answered"
            )
            transformed_item = details.copy()
            transformed_item["status"] = answer_status

            # Assign an initial group ("pulse") based on index:
            # indexes 0-1 -> "primary", 2-3 -> "secondary", 4-5 -> "tertiary".
            if index < 2:
                transformed_item["pulse"] = "primary"
            elif index < 4:
                transformed_item["pulse"] = "secondary"
            else:
                transformed_item["pulse"] = "tertiary"

            transformed.append(transformed_item)

        # Group the six answers into three groups.
        group1 = transformed[0:2]
        group2 = transformed[2:4]
        group3 = transformed[4:6]

        # Count answered items in each group.
        group1_count = sum(1 for item in group1 if item["status"] == "answered")
        group2_count = sum(1 for item in group2 if item["status"] == "answered")
        group3_count = sum(1 for item in group3 if item["status"] == "answered")

        # Get the first answered item from each group (if available).
        group1_first = next(
            (item for item in group1 if item["status"] == "answered"), None
        )
        group2_first = next(
            (item for item in group2 if item["status"] == "answered"), None
        )
        group3_first = next(
            (item for item in group3 if item["status"] == "answered"), None
        )

        weightage_item = None

        # Weightage Rule Set 1: If any group has both answered, choose that group's first answered item.

        if group1_count == 2:
            weightage_item = group1_first
        elif group2_count == 2:
            weightage_item = group2_first
        elif group3_count == 2:
            weightage_item = group3_first
        # Weightage Rule Set 2: If no group has both answered.
        elif group1_count == 1 and group2_count == 0 and group3_count == 0:
            weightage_item = group1_first
        elif group2_count == 1 and group1_count == 0 and group3_count == 0:
            weightage_item = group2_first
        elif group3_count == 1 and group1_count == 0 and group2_count == 0:
            weightage_item = group3_first
        elif group1_count == 1 and group2_count == 1 and group3_count == 1:
            weightage_item = group1_first
        elif group1_count == 0 and group2_count == 1 and group3_count == 1:
            weightage_item = group2_first
        elif group1_count == 0 and group3_count == 1:
            weightage_item = group3_first
        else:
            # Fallback: choose the first available answered item in group order.
            weightage_item = group1_first or group2_first or group3_first

        # Final fallback if no answered item is found: default to the first item of group1.
        if not weightage_item:
            weightage_item = group1[0]

        # Determine which group the weightage item came from.
        weightage_group = weightage_item.get(
            "pulse"
        )  # "primary", "secondary", or "tertiary"

        # Define the initial pulse mapping using only the primary, secondary, tertiary fields
        # from DiagnosisReportHistory.
        if weightage_group == "primary":
            pulse_mapping = {
                "primary": diagnosis_report.primary,
                "secondary": diagnosis_report.secondary,
                "tertiary": diagnosis_report.tertiary,
            }
        elif weightage_group == "secondary":
            pulse_mapping = {
                "primary": diagnosis_report.secondary,
                "secondary": diagnosis_report.primary,
                "tertiary": diagnosis_report.tertiary,
            }
        elif weightage_group == "tertiary":
            pulse_mapping = {
                "primary": diagnosis_report.tertiary,
                "secondary": diagnosis_report.primary,
                "tertiary": diagnosis_report.secondary,
            }
        else:
            pulse_mapping = {
                "primary": diagnosis_report.primary,
                "secondary": diagnosis_report.secondary,
                "tertiary": diagnosis_report.tertiary,
            }

        # --- Begin Patterns adjustments for Yin "heat", then wind/humid ---
        # Only perform these adjustments if the weightage Energy (Yin_Yang) is "yin".
        yin_yang_value = weightage_item.get("Energy")
        if yin_yang_value and yin_yang_value.lower() == "yin":
            # === First Priority: Adjust "Heat" ===
            # Step 1: Query Patterns with the current mapping.
            pattern = Patterns.objects.filter(
                primary=pulse_mapping["primary"],
                secondary=pulse_mapping["secondary"],
                tertiary=pulse_mapping["tertiary"],
            ).first()
            if pattern and pattern.yin_yang and pattern.yin_yang.lower() == "yang":
                # Interchange secondary and tertiary.
                pulse_mapping["secondary"], pulse_mapping["tertiary"] = (
                    pulse_mapping["tertiary"],
                    pulse_mapping["secondary"],
                )

            # Step 2: Query Patterns again with the current mapping.
            pattern = Patterns.objects.filter(
                primary=pulse_mapping["primary"],
                secondary=pulse_mapping["secondary"],
                tertiary=pulse_mapping["tertiary"],
            ).first()
            if pattern and pattern.yin_yang and pattern.yin_yang.lower() == "yang":
                # If secondary or tertiary is "Heat", replace it with "Dry".
                if pulse_mapping["secondary"].lower() == "heat":
                    pulse_mapping["secondary"] = "Dry"
                if pulse_mapping["tertiary"].lower() == "heat":
                    pulse_mapping["tertiary"] = "Dry"

            # Step 3: Query Patterns once more.
            pattern = Patterns.objects.filter(
                primary=pulse_mapping["primary"],
                secondary=pulse_mapping["secondary"],
                tertiary=pulse_mapping["tertiary"],
            ).first()
            if pattern and pattern.yin_yang and pattern.yin_yang.lower() == "yang":
                # Interchange secondary and tertiary.
                pulse_mapping["secondary"], pulse_mapping["tertiary"] = (
                    pulse_mapping["tertiary"],
                    pulse_mapping["secondary"],
                )

            # === Second Priority: Between "Wind" and "Humid" ===
            # Count occurrences among transformed answers using the current mapping.
            wind_count = sum(
                1 for item in transformed if item["pulse"].lower() == "wind"
            )
            humid_count = sum(
                1 for item in transformed if item["pulse"].lower() == "humid"
            )
            # Decide which candidate to adjust.
            if wind_count < humid_count:
                candidate = "wind"
            elif humid_count < wind_count:
                candidate = "humid"
            else:
                candidate = random.choice(["wind", "humid"])
            # Step 4: Query Patterns with the current mapping.
            pattern = Patterns.objects.filter(
                primary=pulse_mapping["primary"],
                secondary=pulse_mapping["secondary"],
                tertiary=pulse_mapping["tertiary"],
            ).first()
            if pattern and pattern.yin_yang and pattern.yin_yang.lower() == "yang":
                # If secondary or tertiary equals the chosen candidate (case-insensitive), replace it with "Dry".
                if pulse_mapping["secondary"].lower() == candidate:
                    pulse_mapping["secondary"] = "Dry"
                if pulse_mapping["tertiary"].lower() == candidate:
                    pulse_mapping["tertiary"] = "Dry"
            # Step 5: Query Patterns one more time.
            pattern = Patterns.objects.filter(
                primary=pulse_mapping["primary"],
                secondary=pulse_mapping["secondary"],
                tertiary=pulse_mapping["tertiary"],
            ).first()
            if pattern and pattern.yin_yang and pattern.yin_yang.lower() == "yang":
                # Interchange secondary and tertiary.
                pulse_mapping["secondary"], pulse_mapping["tertiary"] = (
                    pulse_mapping["tertiary"],
                    pulse_mapping["secondary"],
                )

        # --- End Patterns adjustments ---

        # Reassign the pulse field for all transformed answers using the final pulse_mapping.
        for item in transformed:
            original_group = item.get("pulse")  # "primary", "secondary", or "tertiary"
            item["pulse"] = pulse_mapping.get(original_group, original_group)

        # Instead of returning a protocol string, return Organ and Yin_Yang separately from the weightage item.
        organ_value = weightage_item.get("Organ")

        response_data = {
            # "transformed_answers": transformed,
            "Organ": organ_value,
            "Yin_Yang": yin_yang_value,
            "pulse_mapping": pulse_mapping,  # Contains the final mapping for primary, secondary, and tertiary.
        }
        return StandardResponse(
            data=response_data, message="Transformation successful", status_code=200
        )
