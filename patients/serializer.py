from rest_framework import serializers
from .models import PatientsModel

class PatientsModelSerializer(serializers.ModelSerializer):
    dob = serializers.DateField(format="%d-%m-%Y")  # Formats output as DD-MM-YYYY

    class Meta:
        model = PatientsModel
        fields = '__all__'
