from .initialize_b2 import get_b2_api
import os


def delete_from_backblaze(file_name):
    # Define Backblaze configurations
    B2_BUCKET_NAME = os.getenv('B2_BUCKET_NAME')

    # Initialize B2 API
    b2_api = get_b2_api()
    bucket = b2_api.get_bucket_by_name(B2_BUCKET_NAME)

    try:
        # Locate the file version and delete it
        file_version = bucket.get_file_info_by_name(file_name)
        bucket.delete_file_version(file_version.id_, file_name)
        return True
    except Exception as e:
        print(f"Failed to delete file {file_name} from Backblaze: {e}")
        return False
