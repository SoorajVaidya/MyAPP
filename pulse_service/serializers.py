# serializers.py
from rest_framework import serializers

from .models import PulseData, PulseLog
from .models import PulseDataObservations, PulseDataSymptoms
from rest_framework import serializers

class PulseSignalSerializer(serializers.ModelSerializer):
    class Meta:
        model = PulseData
        fields = ['user', 'signal_data']


class PulseDataObservationsSerializer(serializers.ModelSerializer):
    class Meta:
        model = PulseDataObservations
        fields = [
            'urine_color',
            'night_urination',
            'sleep',
            'backpain',
            'appetite',
            'bowel_movement',
            'numbness',
            'headache'
        ]

    def create(self, validated_data):
        # Extract pulse_id and map it to the PulseData relationship
        return PulseDataObservations.objects.create(**validated_data)


class PulseDataSymptomsSerializer(serializers.ModelSerializer):
    class Meta:
        model = PulseDataSymptoms
        fields = '__all__'  # Include all fields in the serializer


class PulseLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = PulseLog
        fields = ['id', 'pulse_data', 'created_at', 'updated_at']

