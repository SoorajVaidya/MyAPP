from .models import RegisterSensor


def validate_device_against_user(device_id, user_id):
    
    register_sensor = RegisterSensor.objects.filter(unique_id=device_id).first()
    if (register_sensor and register_sensor.user_id == user_id):
        ret = True
    else:
        ret = False

    return ret