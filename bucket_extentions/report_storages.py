from storages.backends.s3boto3 import S3Boto3Storage
import os
import boto3


class ReportsStorage(S3Boto3Storage):
    """Custom storage for files in the Reports path on Backblaze B2."""

    def __init__(self, *args, **kwargs):
        # Retrieve credentials and region from environment variables
        bucket_name = os.getenv("B2_BUCKET_NAME")  # Bucket name
        region = os.getenv("B2_REGION", "us-east-005")  # Default to 'us-east-005'

        # Configure S3-compatible settings
        self.bucket_name = bucket_name
        self.custom_domain = f"{bucket_name}.s3.{region}.backblazeb2.com"  # Custom domain for public access
        kwargs["access_key"] = os.getenv("B2_ACCOUNT_ID")
        kwargs["secret_key"] = os.getenv("B2_APPLICATION_KEY")
        kwargs["endpoint_url"] = f"https://s3.{region}.backblazeb2.com"  # Correct S3-compatible endpoint

        # Set the base location to "Reports/"
        kwargs["location"] = "Reports"
        super().__init__(*args, **kwargs)

        self.s3_client = boto3.client(
            "s3",
            aws_access_key_id=kwargs["access_key"],
            aws_secret_access_key=kwargs["secret_key"],
            endpoint_url=kwargs["endpoint_url"],
        )

    def url(self, name):
        """
        Generate the public URL for a file stored in the bucket.
        Ensures `Reports/` prefix is included in the URL.
        """
        # Prepend 'Reports/' if it's not already in the name
        if not name.startswith("Reports/"):
            name = f"Reports/{name}"
        return f"https://{self.custom_domain}/{name}"

    def delete(self, name):
        """
        Deletes all versions of a file from Backblaze B2 storage to avoid "hidden" files.
        """
        # Prepend 'Reports/' if it's not already in the name
        if not name.startswith("Reports/"):
            name = f"Reports/{name}"

        # List all versions of the file
        try:
            response = self.s3_client.list_object_versions(Bucket=self.bucket_name, Prefix=name)
            versions = response.get("Versions", []) + response.get("DeleteMarkers", [])

            # Iterate through all versions and delete them
            for version in versions:
                version_id = version.get("VersionId")
                self.s3_client.delete_object(Bucket=self.bucket_name, Key=name, VersionId=version_id)

        except self.s3_client.exceptions.NoSuchKey:
            # Handle case where the file does not exist
            pass
        except Exception as e:
            # Log any unexpected errors
            print(f"Error deleting file {name}: {e}")
            raise



