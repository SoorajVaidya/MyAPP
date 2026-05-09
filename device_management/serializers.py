from rest_framework import serializers
from .models import FactorySenorList, RegisterSensor


class RegisterDeviceSerializer(serializers.ModelSerializer):
    unique_id = serializers.CharField()  # Declare unique_id as a CharField to bypass FK validation

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        self.invalid_device = False

    class Meta:
        model = RegisterSensor
        fields = ['user', 'unique_id', 'comments', 'email', 'phone_number']
        extra_kwargs = {
            'user': {'write_only': True},  # User ID will be passed but not exposed in response
        }

    def validate_unique_id(self, value):
        """
        Validate the unique_id:
        1. Check if it exists in the FactorySensorList.
        """
        # Check if the unique_id is in the FactorySensorList
        if not FactorySenorList.objects.filter(unique_id=value).exists():
            self.invalid_device = True  # Mark as invalid device
        return value

    def validate(self, attrs):
        user = attrs.get('user')
        device_id = attrs.get('unique_id')
        
        # If the device isn't valid, we can skip the duplicate check.
        if self.invalid_device:
            return attrs
        
        # Check if the user has already registered with the same device.
        if RegisterSensor.objects.filter(user=user, unique_id__unique_id=device_id).exists():
            raise serializers.ValidationError({"error": "Device is already registered."})
        
        return attrs

    def create(self, validated_data):
        """
        Create a new RegisterSensor object.
        """
        # Convert unique_id back to FK after manual validation
        validated_data['unique_id'] = FactorySenorList.objects.get(unique_id=validated_data['unique_id'])
        return RegisterSensor.objects.create(**validated_data)
