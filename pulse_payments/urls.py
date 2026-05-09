from django.urls import path
from .views import (
    CreateOrderAPIView,
    CreateOrderView,
    TransactionHistoryAPIView,
    VerifyPaymentAPIView,
    WalletBalanceAPIView,
    DeductFromWalletAPIView,
    WalletServiceHistoryAPIView, ServiceListAPIView,
    razorpay_webhook,
)

urlpatterns = [
    # Endpoint to create a payment order
    path('payment/create-order/', CreateOrderAPIView.as_view(), name='create_order'),

    # Endpoint to verify the payment
    path('payment/verify/', VerifyPaymentAPIView.as_view(), name='verify_payment'),

    # Test payment page
    path('payment/test/', CreateOrderView.as_view(), name='test_payment'),

    # Endpoint to view transaction history
    path('payment/history/', TransactionHistoryAPIView.as_view(), name='transaction_history'),

    # Endpoint to view wallet balance
    path('payment/balance/', WalletBalanceAPIView.as_view(), name='payment_balance'),

    # Endpoint to deduct from wallet
    path('wallet/deduct-service/', DeductFromWalletAPIView.as_view(), name='wallet_deduct'),

    path('wallet/service-history', WalletServiceHistoryAPIView.as_view(), name='wallet-service-history'),

    path('services/', ServiceListAPIView.as_view(), name='list_services'),
    
   path('webhooks/razorpay/', razorpay_webhook),

]
