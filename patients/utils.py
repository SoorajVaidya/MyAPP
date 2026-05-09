# utils.py

from b2sdk.v1 import *


def upload_to_backblaze(photo, file_name):
    B2_ACCOUNT_ID = '00555283e76e4350000000002'
    B2_APPLICATION_KEY = 'K005yF/hyaxpUKr3gxxSaaPMub86IDg'
    B2_BUCKET_NAME = 'nadiswara'
    B2_ENDPOINT = 'https://api.backblazeb2.com'

    info = InMemoryAccountInfo()
    b2_api = B2Api(info)
    b2_api.authorize_account("production", B2_ACCOUNT_ID, B2_APPLICATION_KEY)

    bucket = b2_api.get_bucket_by_name(B2_BUCKET_NAME)
    file_data = photo.read()

    # Upload the bytes with the specified file name
    bucket.upload_bytes(file_data, file_name)

    return f"{B2_ENDPOINT}/file/{B2_BUCKET_NAME}/{file_name}"


def delete_from_backblaze(file_name):
    B2_ACCOUNT_ID = '00555283e76e4350000000002'
    B2_APPLICATION_KEY = 'K005yF/hyaxpUKr3gxxSaaPMub86IDg'
    B2_BUCKET_NAME = 'nadiswara'

    info = InMemoryAccountInfo()
    b2_api = B2Api(info)
    b2_api.authorize_account("production", B2_ACCOUNT_ID, B2_APPLICATION_KEY)

    bucket = b2_api.get_bucket_by_name(B2_BUCKET_NAME)

    # Locate the file and delete it
    try:
        file_version = bucket.get_file_info_by_name(file_name)
        bucket.delete_file_version(file_version.id_, file_name)
        return True
    except Exception as e:
        print(f"Failed to delete file {file_name} from Backblaze: {e}")
        return False
