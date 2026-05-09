from decimal import Decimal

from django.conf import settings
from django.db import models
from django.core.exceptions import ValidationError


class Wallet(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    def __str__(self):
        return f"{self.user}'s Wallet with balance {self.balance}"

    @staticmethod
    def get_minimum_balance():
        """
        Fetch the minimum balance for wallet deductions.
        If the 'Minimum Balance' service does not exist, default to ₹5.00.
        """
        from .models import (
            Service,
        )  # Import Service model here to avoid circular imports

        minimum_balance_service = Service.objects.filter(name="Minimum Balance").first()
        return (
            minimum_balance_service.price
            if minimum_balance_service
            else Decimal("5.00")
        )

    def can_deduct(self, amount):
        """
        Check if the wallet has sufficient balance to deduct the given amount.
        """
        minimum_balance = Wallet.get_minimum_balance()
        return self.balance - amount >= minimum_balance

    def deduct_balance(self, amount):
        """
        Deduct the specified amount from the wallet if the balance is sufficient.
        """
        if not self.can_deduct(amount):
            raise ValueError(
                f"Insufficient balance. Wallet must maintain a minimum balance of {Wallet.get_minimum_balance()}."
            )
        self.balance -= amount
        self.save()


class MinimumBalance(models.Model):
    minimum_balance = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="minimum_balance_created",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="minimum_balance_updated",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    def clean(self):
        # When creating a new instance, ensure no instance already exists.
        if not self.pk and MinimumBalance.objects.exists():
            raise ValidationError("There can be only one MinimumBalance instance.")

    def save(self, *args, **kwargs):
        # Validate before saving.
        self.clean()
        super(MinimumBalance, self).save(*args, **kwargs)

    def __str__(self):
        return f"Minimum Balance: {self.minimum_balance}"

    class Meta:
        verbose_name = "Minimum Balance"
        verbose_name_plural = "Minimum Balance"
        db_table = "minimum_balance"


class WalletPaymentsDetails(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(
        max_length=20
    )  # e.g., 'Credit Card', 'Debit Card', 'UPI'
    transaction_id = models.CharField(max_length=100, unique=True)
    status = models.CharField(
        max_length=20,
        choices=[
            ("Completed", "Completed"),
            ("Pending", "Pending"),
            ("Failed", "Failed"),
        ],
    )
    diagnosis = models.CharField(
        max_length=255, null=True, blank=True
    )  # Reference to the diagnosis
    wallet_amount = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )  # New column
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "wallet_payment_details"

    def _str_(self):
        return f"Wallet Payment {self.transaction_id} by {self.user}"


class WalletTransactionDetails(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=20)
    transaction_id = models.CharField(max_length=100, unique=True)
    status = models.CharField(
        max_length=20,
        choices=[("Pending", "Pending"), ("Success", "Success"), ("Failed", "Failed")],
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def _str_(self):
        return f"Transaction {self.transaction_id} by {self.user}"

    class Meta:
        db_table = "wallet_transaction_details"


class Service(models.Model):
    service_id = models.PositiveIntegerField(unique=True)
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_services",
    )
    number_of_pages = models.PositiveIntegerField(null=True, blank=True)  # New field
    image_url = models.URLField(max_length=500, null=True, blank=True)  # New field

    class Meta:
        db_table = "nadiswara_services"

    def __str__(self):
        return self.name

    @staticmethod
    def get_minimum_balance():
        """
        Fetch the minimum balance for wallet deductions.
        If the 'Minimum Balance' service does not exist, default to ₹5.00.
        """
        minimum_balance_service = Service.objects.filter(name="Minimum Balance").first()
        return (
            minimum_balance_service.price
            if minimum_balance_service
            else Decimal("5.00")
        )


class ServiceTransactionDetails(models.Model):
    STATUS_CHOICES = [
        ("Pending", "Pending"),
        ("Success", "Success"),
        ("Failed", "Failed"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    service = models.ForeignKey(
        Service,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        to_field="service_id",  # This tells Django to use the 'service_id' field from Service
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="Pending")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    payment_method = models.CharField(
        max_length=50, null=True, blank=True
    )  # Add payment method
    transaction_id = models.CharField(
        max_length=100, unique=True, null=True, blank=True
    )  # Add transaction ID
    wallet_amount = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )  # Add wallet amount
    diagnosis = models.CharField(max_length=255, null=True, blank=True)  # Add diagnosis
    report_history_id = models.CharField(
        max_length=100, null=True, blank=True
    )  
    patient_id = models.CharField(max_length=50, null=True, blank=True)  # New column: patient_id


    def __str__(self):
        return f"Transaction {self.id} by {self.user} for {self.service.name}"

    class Meta:
        db_table = "service_transaction_details"
