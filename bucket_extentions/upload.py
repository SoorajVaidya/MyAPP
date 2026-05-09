from .initialize_b2 import get_b2_api
import os


def upload_to_backblaze(photo, file_name):
    # Define Backblaze configurations
    B2_BUCKET_NAME = os.getenv('B2_BUCKET_NAME')
    B2_ENDPOINT = os.getenv('B2_ENDPOINT')

    # Initialize B2 API
    b2_api = get_b2_api()
    bucket = b2_api.get_bucket_by_name(B2_BUCKET_NAME)

    # Read the file data
    file_data = photo.read()

    # Upload the file data with the specified file name
    bucket.upload_bytes(file_data, file_name)

    # Construct the URL for the uploaded file
    return f"{B2_ENDPOINT}/file/{B2_BUCKET_NAME}/{file_name}"
