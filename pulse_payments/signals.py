from django.db.models.signals import post_save
from django.dispatch import receiver
from authentication.models import CustomUser  # Update this to your actual user model path
from pulse_payments.models import Wallet  # Update this to your actual Wallet model path

@receiver(post_save, sender=CustomUser)
def create_user_wallet(sender, instance, created, **kwargs):
    if created:
        # Create a Wallet for the user if it doesn't exist
        Wallet.objects.get_or_create(user=instance)

@receiver(post_save, sender=CustomUser)
def save_user_wallet(sender, instance, **kwargs):
    if hasattr(instance, 'wallet'):
        instance.wallet.save()
