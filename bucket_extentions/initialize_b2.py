from b2sdk.v1 import InMemoryAccountInfo, B2Api
import os
from dotenv import load_dotenv

load_dotenv()

def get_b2_api():
    B2_ACCOUNT_ID = os.getenv('B2_ACCOUNT_ID')
    B2_APPLICATION_KEY = os.getenv('B2_APPLICATION_KEY')
    info = InMemoryAccountInfo()
    b2_api = B2Api(info)
    b2_api.authorize_account("production", B2_ACCOUNT_ID, B2_APPLICATION_KEY)
    return b2_api
