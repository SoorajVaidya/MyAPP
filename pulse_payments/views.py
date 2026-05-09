import json
import logging
import hmac
import hashlib
from datetime import datetime
from decimal import Decimal
import uuid
from django.http import HttpResponse, HttpResponseForbidden
import razorpay
from django.db import transaction
from django.shortcuts import get_object_or_404, render
from django.utils.timezone import make_aware
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.views.decorators.csrf import csrf_exempt
from oohy_product.custom_responses import ErrorResponse, StandardResponse
from patients.models import PatientsModel
from pulse_payments.utils import ALLOWED_PAYMENTS
from user_profile.models import UserProfile
from .models import (
    MinimumBalance,
    WalletPaymentsDetails,
    WalletTransactionDetails,
    Wallet,
    Service,
    ServiceTransactionDetails,
)
from dotenv import load_dotenv
import os
from device_management.models import RegisterSensor

# Load environment variables
load_dotenv()
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_SECRET_KEY = os.getenv("RAZORPAY_SECRET_KEY")

razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_SECRET_KEY))
logger = logging.getLogger(__name__)


class CreateOrderAPIView(APIView):
    """
    Creates a Razorpay order.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        data = request.data
        amount = data.get("amount")

        if not amount:
            return Response(
                {"error": "Amount is required"}, status=status.HTTP_400_BAD_REQUEST
            )
        try:
            # Convert amount to a float for comparison
            amount_value = float(amount)
        except ValueError:
            return Response(
                {"error": "Invalid amount format"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate that the requested amount is one of the allowed options.
        if amount_value not in ALLOWED_PAYMENTS:
            return Response(
                {
                    "error": "Invalid payment amount. Allowed options are 575, 1150, 2300, and 5750 Rs."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        order_data = {
            "amount": int(amount_value * 100),  # Razorpay expects amount in paise
            "currency": "INR",
            "receipt": "receipt#1",
            "payment_capture": "1",  # Auto capture
            "notes": {
                "user_id": request.user.id,
                # Optionally, you could also store the original amount for cross-checking later.
                "order_amount": amount_value,
            },
        }

        try:
            razorpay_order = razorpay_client.order.create(data=order_data)
        except Exception as e:
            logger.error(f"Error creating Razorpay order: {e}")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        return Response(
            {
                "order_id": razorpay_order["id"],
                "amount": amount_value,
                "currency": "INR",
                "key": RAZORPAY_KEY_ID,  # Pass key securely from backend
            }
        )


class VerifyPaymentAPIView(APIView):
    """
    Verifies Razorpay payment and updates wallet balance.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        payment_id = request.data.get("razorpay_payment_id")
        order_id = request.data.get("razorpay_order_id")
        signature = request.data.get("razorpay_signature")
        amount = Decimal(request.data.get("amount"))

        if not all([payment_id, order_id, signature]):
            return Response(
                {"error": "Missing payment details"}, status=status.HTTP_400_BAD_REQUEST
            )

        if self.verify_signature(order_id, payment_id, signature):
            new_balance = self.add_to_wallet(request.user, amount)

            WalletPaymentsDetails.objects.create(
                user=request.user,
                amount=amount,
                payment_method="Razorpay",
                transaction_id=payment_id,
                status="Completed",
                wallet_amount=new_balance,
            )

            WalletTransactionDetails.objects.create(
                user=request.user,
                amount=amount,
                payment_method="Razorpay",
                transaction_id=payment_id,
                status="Success",
            )

            return Response(
                {
                    "status": "Payment verified successfully!",
                    "wallet_balance": new_balance,
                },
                status=status.HTTP_200_OK,
            )
        else:
            return Response(
                {"error": "Signature verification failed"},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @staticmethod
    def verify_signature(order_id, payment_id, razorpay_signature):
        key = RAZORPAY_SECRET_KEY.encode()
        message = f"{order_id}|{payment_id}".encode()
        expected_signature = hmac.new(key, message, hashlib.sha256).hexdigest()
        return expected_signature == razorpay_signature

    @staticmethod
    @transaction.atomic
    def add_to_wallet(user, amount):
        wallet, created = Wallet.objects.get_or_create(user=user)
        wallet.balance += Decimal(amount)
        wallet.save()
        return wallet.balance


class TransactionHistoryAPIView(APIView):
    """
    Lists all transactions for the authenticated user along with the user's name.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        if user.is_authenticated:
            # Fetch user's profile to get user_name
            try:
                user_profile = (
                    user.profile
                )  # Accessing the related UserProfile using `related_name`
                user_name = user_profile.user_name
            except UserProfile.DoesNotExist:
                return ErrorResponse(
                    errors={
                        "status": "error",
                        "message": "User profile not found for this user.",
                    },
                    status_code=status.HTTP_404_NOT_FOUND,
                )

            # Fetch user's wallet transactions
            wallet_transactions = WalletTransactionDetails.objects.filter(
                user=user
            ).order_by("-created_at")
            transaction_list = [
                {
                    "transaction_id": txn.transaction_id,
                    "amount": str(txn.amount),
                    "payment_method": txn.payment_method,
                    "status": txn.status,
                    "purchased_at": txn.created_at.isoformat(),
                }
                for txn in wallet_transactions
            ]

            # Add logic to differentiate "Analyse Pulse"
            for txn in transaction_list:
                if "analyse_" in txn["transaction_id"]:
                    txn["description"] = "Analyse Pulse"
                else:
                    txn["description"] = "Other Wallet Transaction"

            # Include the user's name in the response
            return StandardResponse(
                data={
                    "status": "success",
                    "user_name": user_name,
                    "transactions": transaction_list,
                },
                message="Transaction history retrieved successfully.",
            )

        else:
            return ErrorResponse(
                errors={"status": "error", "message": "User is not authenticated."},
                status_code=status.HTTP_401_UNAUTHORIZED,
            )


class WalletBalanceAPIView(APIView):
    """
    Retrieves the user's wallet balance.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        wallet, created = Wallet.objects.get_or_create(user=request.user)
        return StandardResponse(
            data={"wallet_balance": wallet.balance},
            message="Wallet balance retrieved successfully.",
        )


class CreateOrderView(APIView):
    """
    Renders a test payment page.
    """

    # permission_classes = [IsAuthenticated]

    def get(self, request):
        return render(
            request,
            "create_order.html",
            context={"your_razorpay_key_id": RAZORPAY_KEY_ID},
        )


class DeductFromWalletAPIView(APIView):
    """
    Deducts the price of a service from the user's wallet based on the service name or ID provided.
    """

    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        try:
            data = request.data
            service_name_or_id = data.get("service_name_or_id")
            patient_id = data.get("patient_id")
            report_history_id = data.get("report_history_id", None)
            user = request.user

            if not service_name_or_id:
                return ErrorResponse(
                    errors={"error": "Service name or ID is required."},
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            if not patient_id:
                return ErrorResponse(
                    errors={"error": "Patient ID is required."},
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            # Try to fetch the service by name or ID
            service = None
            if service_name_or_id.isdigit():
                service = Service.objects.filter(
                    service_id=int(service_name_or_id)
                ).first()
            else:
                service = Service.objects.filter(name=service_name_or_id).first()

            if not service:
                return ErrorResponse(
                    errors={
                        "error": f"Service with name or ID '{service_name_or_id}' not found."
                    },
                    status_code=status.HTTP_404_NOT_FOUND,
                )

            # Fetch the patient details
            patient = PatientsModel.objects.filter(id=patient_id).first()
            if not patient:
                return ErrorResponse(
                    errors={"error": f"Patient with ID '{patient_id}' not found."},
                    status_code=status.HTTP_404_NOT_FOUND,
                )

            # Fetch the user profile to get the username
            user_profile = getattr(user, "profile", None)
            user_name = user_profile.user_name if user_profile else "Unknown User"

            # Check if the user is a superuser
            if getattr(request, "is_superuser", False):
                return StandardResponse(
                    data={
                        "status": "success",
                        "message": f"Service {service.name} availed successfully (no charge for superusers).",
                        "patient_name": patient.name,
                        "username": user_name,
                    },
                    message=f"Superuser accessed the service {service.name} without any charges.",
                    status_code=status.HTTP_200_OK,
                )

            # Proceed with wallet deduction for non-superusers
            amount_to_deduct = service.price

            # Get or create the user's wallet
            wallet, created = Wallet.objects.get_or_create(user=user)

            # Fetch the dynamic minimum balance
            minimum_balance_instance = get_object_or_404(MinimumBalance)
            minimum_balance = minimum_balance_instance.minimum_balance

            # Allow transaction only if wallet's current balance is at least the minimum balance.
            if wallet.balance < minimum_balance:
                return ErrorResponse(
                    errors={
                        "error": f"Insufficient balance. Wallet must maintain a minimum balance of ₹{minimum_balance}."
                    },
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            # Also check that the wallet has enough funds for the service cost.
            if wallet.balance < amount_to_deduct:
                return ErrorResponse(
                    errors={
                        "error": "Insufficient wallet funds to cover the service cost."
                    },
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            # Deduct the amount (even if it causes the wallet to go below the minimum balance)
            wallet.balance -= amount_to_deduct
            wallet.save()

            # Generate a unique transaction ID
            transaction_id = f"deduction_{user.id}_{wallet.id}_{uuid.uuid4().hex[:8]}"

            # Record the transaction
            # print(366, service.id)
            ServiceTransactionDetails.objects.create(
                user=user,
                service=service,
                amount=amount_to_deduct,
                status="Completed",
                payment_method="Wallet",
                transaction_id=transaction_id,
                wallet_amount=wallet.balance,
                diagnosis=service.name,
                report_history_id=report_history_id,
                patient_id=patient_id,
            )

            return StandardResponse(
                data={
                    "status": "success",
                    "message": f"₹{amount_to_deduct} deducted from wallet for {service.name}.",
                    "service_name": service.name,
                    "amount_deducted": amount_to_deduct,
                    "wallet_balance": wallet.balance,
                    "patient_name": patient.first_name,
                    "username": user_name,
                },
                message="Amount deducted successfully from wallet.",
                status_code=status.HTTP_200_OK,
            )

        except Exception as e:
            return ErrorResponse(
                errors={"error": "Internal server error.", "details": str(e)},
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class WalletServiceHistoryAPIView(APIView):
    """
    Retrieves the history of all wallet deductions and related details for the authenticated user.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        logger = logging.getLogger(__name__)
        logger.info(
            f"🧑‍💻 User ID: {request.user.id}, 📞 Phone: {getattr(getattr(request.user, 'profile', None), 'phone_number', 'Unknown')}"
        )

        try:
            user = request.user
            date_str = request.query_params.get(
                "date"
            )  # Get the date from query params

            # Fetch all service transactions for the user
            service_transactions = ServiceTransactionDetails.objects.filter(
                user=user
            ).order_by("-created_at")

            # Filter transactions if date is provided
            if date_str:
                try:
                    filter_date = make_aware(datetime.strptime(date_str, "%Y-%m-%d"))
                    service_transactions = service_transactions.filter(
                        created_at__date=filter_date.date()
                    )
                except ValueError:
                    return ErrorResponse(
                        errors={"error": "Invalid date format. Use YYYY-MM-DD."},
                        status_code=400,
                    )

            # If no transactions found, return a meaningful response
            if not service_transactions.exists():
                return StandardResponse(
                    data=[],
                    message=(
                        "No service transactions found for the given date."
                        if date_str
                        else "No service transactions found."
                    ),
                    status_code=200,
                )

            # Prepare the transaction history response
            service_history = []
            for txn in service_transactions:
                # Fetch the Patient's ID from PatientsModel
                patient = None
                # Fetch patient details solely based on the patient_id from the transaction
                if txn.patient_id:
                    patient = PatientsModel.objects.filter(id=txn.patient_id).first()
                patient_id = patient.id if patient else None
                patient_first_name = patient.first_name if patient else None
                patient_last_name = patient.last_name if patient else None
                patient_phone = patient.phone_number if patient else None

                # Safely handle transactions with no associated service
                service_name = txn.service.name if txn.service else "Analyse Pulse"

                service_history.append(
                    {
                        "transaction_id": txn.transaction_id,
                        "service_name": service_name,
                        "patient_first_name": patient_first_name,
                        "patient_last_name": patient_last_name,
                        "patient_ph_no": patient_phone,
                        "amount_deducted": str(txn.amount),
                        "wallet_balance_after_transaction": str(txn.wallet_amount),
                        "status": txn.status,
                        "payment_method": txn.payment_method,
                        "deducted_at": txn.created_at.isoformat(),
                    }
                )

            return StandardResponse(
                data=service_history,
                message="Wallet service history retrieved successfully.",
                status_code=200,
            )

        except Exception as e:
            return ErrorResponse(
                errors={"error": "Internal server error.", "details": str(e)},
                status_code=500,
            )


class ServiceListAPIView(APIView):
    """
    Lists all available services.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        logger = logging.getLogger(__name__)
        logger.info(
            f"🧑‍💻 User ID: {request.user.id}, 📞 Phone: {getattr(getattr(request.user, 'profile', None), 'phone_number', 'Unknown')}"
        )

        try:
            # Fetch all services
            services = Service.objects.exclude(name="Diagnosis Report").order_by(
                "service_id"
            )
            service_list = [
                {
                    "service_id": service.service_id,
                    "service_name": service.name,
                    "description": service.description,
                    "img_url": service.image_url,
                    "price": str(
                        service.price
                    ),  # Convert Decimal to string for JSON serialization
                    "created_at": service.created_at.isoformat(),
                    "updated_at": service.updated_at.isoformat(),
                }
                for service in services
            ]
            return StandardResponse(
                data=service_list,
                message="Services retrieved successfully.",
                status_code=status.HTTP_200_OK,
            )
        except Exception as e:
            return ErrorResponse(
                errors={"message": "Could not fetch services.", "details": str(e)},
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


@csrf_exempt
def razorpay_webhook(request):
    if request.method != "POST":
        return HttpResponse("Only POST allowed", status=405)

    #logger.info("✅ Webhook reached Django function view!")

    logger = logging.getLogger(__name__)
    logger.info(
        f"🧑‍💻 User ID: {request.user.id}, 📞 Phone: {getattr(getattr(request.user, 'profile', None), 'phone_number', 'Unknown')}"
    )

    webhook_secret = os.getenv("RAZORPAY_WEBHOOK_SECRET")
    received_signature = request.headers.get("X-Razorpay-Signature")

    if not received_signature:
        return HttpResponseForbidden("Missing signature")

    payload = request.body
    computed_signature = hmac.new(
        webhook_secret.encode(), payload, hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(received_signature, computed_signature):
        return HttpResponseForbidden("Invalid signature")

    event = json.loads(payload)

    if event.get("event") == "payment.captured":
        payment_entity = event["payload"]["payment"]["entity"]
        payment_id = payment_entity.get("id")
        # The payment amount is returned in paise, so convert to rupees.
        payment_amount_rupees = float(Decimal(payment_entity.get("amount")) / 100)
        notes = payment_entity.get("notes", {})
        logger.info(f"Payment notes: {notes}")
        user_id = notes.get("user_id")

        # Determine wallet credit based on payment amount.
        if payment_amount_rupees == 5900.0:
            # Override mapping for 5750 rupees so that credit becomes 6000.
            wallet_credit = 6000.0
        else:
            wallet_credit = ALLOWED_PAYMENTS.get(payment_amount_rupees)
            if wallet_credit is None:
                # Log unexpected amounts and skip processing.
                logger.error(
                    f"Unexpected payment amount received: {payment_amount_rupees} rupees."
                )
                return HttpResponse(status=200)

        if user_id:
            try:
                user_profile = UserProfile.objects.get(user_id=user_id)
                wallet, _ = Wallet.objects.get_or_create(user=user_profile.user_id)
                # Use the mapped wallet_credit instead of the full payment amount
                wallet.balance += Decimal(wallet_credit)
                wallet.save()

                if WalletPaymentsDetails.objects.filter(
                    transaction_id=payment_id
                ).exists():
                    logger.info(f"Transaction {payment_id} already processed.")
                    return HttpResponse(status=200)

                WalletPaymentsDetails.objects.create(
                    user=user_profile.user_id,
                    amount=wallet_credit,
                    payment_method="Razorpay",
                    transaction_id=payment_id,
                    status="Completed",
                    wallet_amount=wallet.balance,
                )

                WalletTransactionDetails.objects.create(
                    user=user_profile.user_id,
                    amount=wallet_credit,
                    payment_method="Razorpay",
                    transaction_id=payment_id,
                    status="Success",
                )
            except UserProfile.DoesNotExist:
                logger.error(f"UserProfile not found for user id: {user_id}")
                # return HttpResponse(status=200) to avoid repeated webhook calls if not found.
                return HttpResponse(status=200)

    return HttpResponse(status=200)
