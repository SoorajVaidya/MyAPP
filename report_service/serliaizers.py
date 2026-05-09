from patients.models import PatientsModel
from pulse_payments.models import Service
from pulse_service.models import PulseData
from .models import DiagnosticResource
from rest_framework import serializers
from .models import DiagnosisReportHistory, TreatmentReportHistory

from rest_framework import serializers
from .models import DiagnosticResource


class DiagnosticResourceSerializer(serializers.ModelSerializer):
    """Ensures image fields return properly formatted Backblaze B2 URLs"""

    # quick_solutions = QuickSolutionSerializer(many=True, read_only=True)

    # Define image fields outside the Meta class
    image_fields = [
        "pulse_picture_mobile", "pulse_picture_pdf", "pulse_explanation_icon_mobile", "pulse_explanation_icon_pdf",
        "vpk_icon_mobile", "vpk_icon_pdf", "organ_relation_image_mobile", "organ_relation_image_pdf",
        "organ_relation_icon1_mobile", "organ_relation_icon1_pdf", "organ_relation_icon2_mobile",
        "organ_relation_icon2_pdf", "organ_relation_icon3_mobile", "organ_relation_icon3_pdf",
        "nature_correlation_image_mobile", "nature_correlation_image_pdf", "thought_pattern_image_mobile",
        "thought_pattern_image_pdf", "ai_prediction_image1_mobile", "ai_prediction_image1_pdf",
        "ai_prediction_image2_mobile", "ai_prediction_image2_pdf", "cfp_icon_mobile", "cfp_icon_pdf",
        "body_image_mobile", "body_image_pdf"
    ]

    def get_b2_url(self, obj, field_name):
        """Helper function to return the correct Backblaze B2 URL format"""
        field = getattr(obj, field_name, None)
        if field:
            url = field.url if hasattr(field, 'url') else None
            if url:
                # Ensure URL always uses `https://f005.backblazeb2.com`
                url = url.replace("s3.us-east-005.backblazeb2.com", "f005.backblazeb2.com")
                return url
        return None

    class Meta:
        model = DiagnosticResource
        fields = '__all__'

    # Dynamically create serializer methods for image fields
    for field in image_fields:
        locals()[f"get_{field}"] = lambda self, obj, f=field: self.get_b2_url(obj, f)


class DiagnosisReportHistorySerializer(serializers.ModelSerializer):
    patient_id = serializers.IntegerField(write_only=True)  # Explicitly handle patient_id as an integer
    pulse_id = serializers.IntegerField(write_only=True)   # Explicitly handle pulse_id as an integer

    class Meta:
        model = DiagnosisReportHistory
        exclude = ['user_id']

    def validate_patient_id(self, value):
        """
        Validate and resolve the patient_id to a PatientsModel instance.
        """
        request = self.context['request']
        user = request.user

        # Check if the patient exists and belongs to the authenticated user
        try:
            patient = PatientsModel.objects.get(id=value, user_profile=user)
        except PatientsModel.DoesNotExist:
            raise serializers.ValidationError(f"Patient with id {value} does not exist or does not belong to this user.")

        return patient  # Return the PatientsModel instance

    def validate_pulse_id(self, value):
        """
        Validate the pulse_id field and resolve it to a PulseData instance.
        """
        try:
            pulse = PulseData.objects.get(id=value)
        except PulseData.DoesNotExist:
            raise serializers.ValidationError(f"Pulse with id {value} doesn't exist.")

        return pulse  # Return the PulseData instance

    def validate(self, data):
        """
        Custom cross-field validation.
        """
        # Remove user_id from validation since it is handled by the view
        data.pop('user_id', None)

        # Check for duplicate pulse_id entries for the same user
        if DiagnosisReportHistory.objects.filter(pulse_id=data['pulse_id'], user_id=self.context['request'].user).exists():
            raise serializers.ValidationError("A report already exists for this pulse ID and user.")

        return data

    def create(self, validated_data):
        """
        Override create to handle patient_id and pulse_id as resolved instances.
        """
        patient = validated_data.pop('patient_id')  # Use resolved PatientsModel instance
        pulse = validated_data.pop('pulse_id')  # Use resolved PulseData instance
        validated_data['patient_id'] = patient
        validated_data['pulse_id'] = pulse
        return super().create(validated_data)




class TreatmentReportHistorySerializer(serializers.ModelSerializer):
    diagnosis_report = serializers.IntegerField(write_only=True)  # Accept diagnosis_report as an integer ID
    service_id = serializers.IntegerField(write_only=True)  # Accept service_id as an integer ID

    class Meta:
        model = TreatmentReportHistory
        fields = '__all__'

    def validate_diagnosis_report(self, value):
        """
        Validate the diagnosis_report field and check if it exists.
        """
        try:
            diagnosis_report = DiagnosisReportHistory.objects.get(report_history_id=value)
        except DiagnosisReportHistory.DoesNotExist:
            raise serializers.ValidationError(f"Diagnosis report with id {value} doesn't exist.")

        # Return the valid DiagnosisReportHistory instance
        return diagnosis_report

    def validate_service_id(self, value):
        """
        Validate the service_id field and check if it exists.
        """
        try:
            service = Service.objects.get(service_id=value)
        except Service.DoesNotExist:
            raise serializers.ValidationError(f"Service with id {value} doesn't exist.")

        # Return the valid Service instance
        return service

class TreatmentHistoryDateTimeSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    patient_id = serializers.IntegerField()
    diagnosis_reports_count = serializers.IntegerField()
    treatment_reports_count = serializers.IntegerField()
    report_dates_times = serializers.ListField(child=serializers.DateTimeField())

class ReportPageMetdataSerializer(serializers.ModelSerializer):
    purchased = serializers.BooleanField(default=False)
    service_name = serializers.CharField(source='name')
    service_id = serializers.IntegerField()

    class Meta:
        model = Service
        # Use 'fields' to explicitly list the fields and order them
        fields = [
            'service_id',
            'service_name',
            'price',
            'description',
            'number_of_pages',
            'purchased',  # purchased comes at the end
            'image_url',
        ]
        
