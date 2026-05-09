from .initialize_b2 import get_b2_api
import os

def fetch_file_from_backblaze(file_name_or_url):
    """
    Fetches a file's content from Backblaze B2 bucket.
    If a URL is provided, it extracts the file name and retrieves the content.
    """
    B2_BUCKET_NAME = os.getenv('B2_BUCKET_NAME')
    B2_ENDPOINT = os.getenv('B2_ENDPOINT')

    b2_api = get_b2_api()
    bucket = b2_api.get_bucket_by_name(B2_BUCKET_NAME)

    # Extract the file name if a URL is provided
    if file_name_or_url.startswith("http"):
        file_name = file_name_or_url.replace(f"{B2_ENDPOINT}/file/{B2_BUCKET_NAME}/", "")
    else:
        file_name = file_name_or_url

    try:
        # Fetch the file content
        download_version = bucket.download_file_by_name(file_name)
        file_content = download_version.read()

        return file_content  # Return the actual file content

    except Exception as e:
        print(f"Failed to fetch file {file_name} from Backblaze: {e}")
        return None
