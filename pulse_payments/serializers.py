from rest_framework import serializers
from .models import WalletPayment, TransactionDetails


class WalletPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = WalletPayment
        fields = '__all__'


class TransactionDetailsSerializer(serializers.ModelSerializer):
    class Meta:
        model = TransactionDetails
        fields = '__all__'


class WalletPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = WalletPayment
        fields = "__all__"  # Includes diagnosis