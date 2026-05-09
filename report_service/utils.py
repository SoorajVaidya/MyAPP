import uuid
from storages.backends.s3boto3 import S3Boto3Storage
import os
import boto3


class DiagnosticResourceStorage(S3Boto3Storage):
    """Custom storage for DiagnosticResource images in AWS S3 based on model field names."""

    def __init__(self, *args, **kwargs):
        self.bucket_name = os.getenv("AWS_STORAGE_BUCKET_NAME")
        region = os.getenv("AWS_S3_REGION_NAME", "ap-south-1")

        # AWS S3 Public URL
        self.custom_domain = f"{self.bucket_name}.s3.{region}.amazonaws.com"
        kwargs["access_key"] = os.getenv("AWS_ACCESS_KEY_ID")
        kwargs["secret_key"] = os.getenv("AWS_SECRET_ACCESS_KEY")

        # Remove "location" to avoid duplication
        kwargs.pop("location", None)

        super().__init__(*args, **kwargs)

        # Initialize S3 client
        self.s3_client = boto3.client(
            "s3",
            aws_access_key_id=kwargs["access_key"],
            aws_secret_access_key=kwargs["secret_key"],
            region_name=region,  # AWS Region
        )

    def _save(self, name, content):
        """
        Custom _save method to dynamically adjust the S3 file path using the model field name.
        """
        # Extract field name from the upload path
        field_name = name.split("/")[-2]  # Get field name from Django `upload_to`

        # Generate a unique file name
        unique_filename = f"{uuid.uuid4().hex}.png"  # Change `.png` if needed

        # Construct new path based on model field name
        name = f"DiagnosticResource/{field_name}/{unique_filename}"

        return super()._save(name, content)

    def url(self, name):
        """
        Generate the public URL for a file stored in the bucket.
        Ensures correct prefix for direct access.
        """
        return f"https://{self.custom_domain}/{name}"

    def delete(self, name):
        """
        Deletes an object from AWS S3.
        """
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=name)
        except self.s3_client.exceptions.NoSuchKey:
            pass  # Handle case where the file does not exist
        except Exception as e:
            print(f"Error deleting file {name}: {e}")
            raise
