from twilio.rest import Client

# Your Account SID and Auth Token from twilio.com/console
account_sid = 'AC73a02adc792dc6aff8b072549d27b0e1'
auth_token = '46929e52496f2a1ab849840e3b3e5ab9'
client = Client(account_sid, auth_token)

# Valid Twilio phone number
from_phone_number = '+16812068306'  # Replace with your Twilio number
to_phone_number = '+91 7892974551'  # Replace with the recipient's number

message = client.messages.create(
    body='one time otp',
    from_=from_phone_number,
    to=to_phone_number
)

print(message.sid)
