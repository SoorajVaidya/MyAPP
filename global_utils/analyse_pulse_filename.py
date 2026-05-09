# global_utils/analyse_pulse_filename.py
import re
from datetime import datetime


def generate_analyse_pulse_filename(patient_id, user_id):
    """
    Generates a sanitized filename for analyse pulse data.
    :param patient_id: ID of the patient
    :param user_id: ID of the user
    :return: Sanitized filename as a string
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{patient_id}_{user_id}_{timestamp}.txt"
    sanitized_filename = re.sub(r'[\\/:*?"<>|]', '_', filename)
    return sanitized_filename
