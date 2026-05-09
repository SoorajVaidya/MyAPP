import boto3
import os
from django.conf import settings

def create_backblaze_folder(folder_name):
    """
    Create a folder in Backblaze B2 by uploading a placeholder object with a trailing slash.
    """
    # Load credentials from settings or environment variables
    b2_access_key = getattr(settings, 'BACKBLAZE_ACCESS_KEY_ID', os.getenv('B2_ACCOUNT_ID'))
    b2_secret_key = getattr(settings, 'BACKBLAZE_SECRET_ACCESS_KEY', os.getenv('B2_APPLICATION_KEY'))
    b2_region = getattr(settings, 'BACKBLAZE_BUCKET_REGION', os.getenv('B2_ENDPOINT'))
    b2_bucket_name = getattr(settings, 'BACKBLAZE_BUCKET_NAME', os.getenv('B2_BUCKET_NAME'))

    # Check for missing credentials
    if not all([b2_access_key, b2_secret_key, b2_region, b2_bucket_name]):
        raise ValueError("Missing Backblaze B2 credentials or bucket information.")

    # Initialize the Boto3 S3 client
    s3_client = boto3.client(
        's3',
        aws_access_key_id=b2_access_key,
        aws_secret_access_key=b2_secret_key,
        endpoint_url=b2_region  # Backblaze B2 uses a custom S3 endpoint
    )

    # Create the folder by uploading a dummy object
    try:
        s3_client.put_object(Bucket=b2_bucket_name, Key=f'{folder_name}/')
        print(f"Folder '{folder_name}' created successfully in bucket '{b2_bucket_name}'.")
    except Exception as e:
        print(f"Error creating folder '{folder_name}': {e}")
        raise

def delete_old_image(instance, field_name):
    """Delete the old image if it exists."""
    try:
        old_instance = instance.__class__.objects.get(pk=instance.pk)
        old_image = getattr(old_instance, field_name)
        new_image = getattr(instance, field_name)
        if old_image and old_image != new_image:
            old_image.delete(save=False)
    except instance.__class__.DoesNotExist:
        pass  # If the instance is new, there won't be an old image to delete