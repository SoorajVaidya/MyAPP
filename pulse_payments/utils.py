# payments /utils.py

import razorpay
from pulse_payments import constants
import hmac
import hashlib

razorpay_client = razorpay.Client(
    auth=(constants.RAZORPAY_KEY_ID, constants.RAZORPAY_KEY_SECRET)
)


def generate_signature(order_id, payment_id, razorpay_key_secret):
    message = f"{order_id}|{payment_id}"
    return hmac.new(
        bytes(razorpay_key_secret, "utf-8"),
        msg=bytes(message, "utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()


ALLOWED_PAYMENTS = {
    1.18: 1,
    590: 500,
    1180: 1000,
    2360: 2000,
    5900: 5000,
}
