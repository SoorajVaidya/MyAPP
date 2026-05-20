import uuid

from django.db import models
from django.utils import timezone

from oohy_product import settings
from user_profile.models import UserProfile  # Import UserProfile model
from patients.models import PatientsModel  # Import PatientsModel


class PulseData(models.Model):
    created = models.DateTimeField(default=timezone.now)  # Timestamp when the pulse data is created
    updated = models.DateTimeField(auto_now=True)  # Timestamp for the last update of the pulse data
    pulse_uri = models.URLField(max_length=200)  # Store the URL of the uploaded pulse data
    signal_data = models.TextField(null=True, blank=True)  # Store the pulse signal data (e.g., JSON or text)
    patient = models.ForeignKey(PatientsModel, on_delete=models.CASCADE, default=999999)  # Link to a patient
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)  # Directly link to the user

    class Meta:
        db_table = 'pulse_data'  # Specifies the name of the database table

    def __str__(self):
        return f"Pulse data for Patient ID: {self.patient.id}, User ID: {self.user.id}"


class PulseDataObservations(models.Model):
    # One-to-one relationship with Pulse
    pulse = models.OneToOneField(PulseData, on_delete=models.CASCADE, related_name='details')

    # Fields for the mandatory questions
    urine_color = models.CharField(
        max_length=50,
        choices=[
            ('white_transparent_occasional', 'White Transparent Occasionally'),
            ('white_transparent_always', 'White Transparent Always'),
            ('pale_yellow', 'Pale Yellow'),
            ('yellow_occasional', 'Yellow Occasionally'),
            ('yellow_always', 'Yellow Always')
        ]
    )
    night_urination = models.PositiveSmallIntegerField()  # Range: 1-6

    sleep = models.CharField(
        max_length=50,
        choices=[
            ('disturbed_occasionally', 'Disturbed Occasionally'),
            ('late_sleep', 'Late Sleep'),
            ('normal_sleep', 'Normal Sleep'),
            ('hard_to_sleep', 'Hard to Get Sleep')
        ]
    )
    backpain = models.CharField(
        max_length=50,
        choices=[
            ('sometimes', 'Sometimes'),
            ('always', 'Always'),
            ('no', 'No')
        ]
    )
    appetite = models.CharField(
        max_length=50,
        choices=[
            ('no_hunger', 'No Hunger'),
            ('less_hunger', 'Less Hunger'),
            ('normal_hunger', 'Normal Hunger'),
            ('more_hunger', 'More Hunger')
        ]
    )
    bowel_movement = models.CharField(
        max_length=50,
        choices=[
            ('constipated_sometimes', 'Constipated Sometimes'),
            ('constipated_always', 'Constipated Always'),
            ('normal_bowel', 'Normal Bowel'),
            ('sometimes_loose_stools', 'Sometimes Loose Stools'),
            ('always_loose_stools', 'Always Loose Stools')
        ]
    )
    numbness = models.CharField(
        max_length=50,
        choices=[
            ('not_feeling_numbness', 'Not Feeling Numbness'),
            ('sometimes_numbness', 'Sometimes Numbness'),
            ('always_numbness', 'Always Numbness')
        ]
    )
    headache = models.CharField(
        max_length=50,
        choices=[
            ('no_headache', 'Not Feeling Headache'),
            ('back_of_head', 'Back of the Head'),
            ('one_side_head', 'One Side of the Head'),
            ('top_of_head', 'Top of the Head'),
            ('forehead', 'Forehead Headache'),
            ('whole_head', 'Whole Head')
        ]
    )

    created = models.DateTimeField(default=timezone.now)  # Timestamp when the pulse data is created
    updated = models.DateTimeField(auto_now=True)  #
    class Meta:
        db_table = 'pulse_data_observations'  # Specifies the name of the database table

    def __str__(self):
        return f"Details for Pulse ID {self.pulse.id}"


class PulseDataSymptoms(models.Model):
    pulse = models.ForeignKey(PulseData, on_delete=models.CASCADE, related_name='ob')  # Link to PulseData
    organ = models.CharField(max_length=50)
    symptoms = models.CharField(max_length=50)
    created = models.DateTimeField(default=timezone.now)  # Timestamp when the pulse data is created
    updated = models.DateTimeField(auto_now=True)  #


    class Meta:
        db_table = 'pulse_data_symptoms'  # Specifies the name of the database table

    def __str__(self):
        return f"Pulse"

class QuestionsTable(models.Model):
    pulse_id = models.ForeignKey(PulseData, on_delete=models.CASCADE)

    # Dynamically generate 50 question fields
    for i in range(1, 51):
        locals()[f'question_{i}'] = models.TextField()
    
    class Meta:
        db_table = 'questions_table'

    def __str__(self):
        return f"Questions for Pulse ID {self.pulse_id.id}"


class PulseLog(models.Model):
    pulse_data = models.TextField()  # Storing pulse data as text
    created_at = models.DateTimeField(auto_now_add=True)  # Automatically set on creation
    updated_at = models.DateTimeField(auto_now=True)  # Automatically updated on save

    class Meta:
        db_table = 'pulse_log'

    def __str__(self):
        return f"PulseLog(id={self.id}, created_at={self.created_at})"






class ReportTask(models.Model):
    TASK_TYPES = [
        ('pdf', 'PDF Report'),
        ('service', 'Service Report'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('started', 'Started'),
        ('success', 'Success'),
        ('failure', 'Failure'),
    ]

    LANG_CHOICES = [
        ('en', 'English'),
        ('hi', 'Hindi'),
        ('ta', 'Tamil'),
        ('te', 'Telugu'),
        ('mr', 'Marathi'),
        # Add more as needed
    ]

    task_id = models.CharField(max_length=255, unique=True)
    task_type = models.CharField(max_length=20, choices=TASK_TYPES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    history_id = models.IntegerField(null=True, blank=True)  # or use FK
    service_id = models.IntegerField(null=True, blank=True)
    language = models.CharField(max_length=10, choices=LANG_CHOICES, default='en')
    download_url = models.URLField(null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    result = models.JSONField(null=True, blank=True)  # Stores full task result
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    elapsed_time = models.FloatField(null=True, blank=True)  # Elapsed time in seconds
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        # Ensure status is always stored in lowercase.
        if self.status:
            self.status = self.status.lower()
        # Calculate elapsed time if both start and complete times are set.
        if self.started_at and self.completed_at:
            self.elapsed_time = (self.completed_at - self.started_at).total_seconds()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.task_type} - {self.task_id} ({self.language})"


class AnalysisJob(models.Model):
    STATE_RECEIVED = "RECEIVED"
    STATE_PROCESSING_SIGNAL = "PROCESSING_SIGNAL"
    STATE_ANALYSIS_COMPLETE = "ANALYSIS_COMPLETE"
    STATE_REPORT_GENERATING = "REPORT_GENERATING"
    STATE_COMPLETED = "COMPLETED"
    STATE_FAILED = "FAILED"

    STATE_CHOICES = [
        (STATE_RECEIVED, "Received"),
        (STATE_PROCESSING_SIGNAL, "Processing signal"),
        (STATE_ANALYSIS_COMPLETE, "Analysis complete"),
        (STATE_REPORT_GENERATING, "Report generating"),
        (STATE_COMPLETED, "Completed"),
        (STATE_FAILED, "Failed"),
    ]

    # Directed graph of legal transitions. Anything not listed here is rejected
    # by transition_to() and raises IllegalTransition.
    ALLOWED_TRANSITIONS = {
        STATE_RECEIVED: {STATE_PROCESSING_SIGNAL, STATE_FAILED},
        STATE_PROCESSING_SIGNAL: {STATE_ANALYSIS_COMPLETE, STATE_FAILED},
        STATE_ANALYSIS_COMPLETE: {STATE_REPORT_GENERATING, STATE_FAILED},
        STATE_REPORT_GENERATING: {STATE_COMPLETED, STATE_FAILED},
        STATE_COMPLETED: set(),
        STATE_FAILED: set(),
    }

    job_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    patient = models.ForeignKey(
        PatientsModel, on_delete=models.PROTECT, related_name="analysis_jobs"
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    idempotency_token = models.CharField(max_length=128, unique=True)
    state = models.CharField(
        max_length=32, choices=STATE_CHOICES, default=STATE_RECEIVED
    )
    language = models.CharField(max_length=16, default="english")

    signal_object_key = models.CharField(max_length=512, null=True, blank=True)
    report_object_key = models.CharField(max_length=512, null=True, blank=True)
    analysis_result = models.JSONField(null=True, blank=True)

    error_code = models.CharField(max_length=64, null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "pulse_analysis_job"
        indexes = [
            models.Index(fields=["state"]),
            models.Index(fields=["patient", "-created_at"]),
        ]

    class IllegalTransition(Exception):
        pass

    def transition_to(self, new_state: str, **fields) -> "AnalysisJob":
        if new_state not in self.ALLOWED_TRANSITIONS.get(self.state, set()):
            raise AnalysisJob.IllegalTransition(
                f"cannot transition {self.state} -> {new_state}"
            )
        self.state = new_state
        for key, value in fields.items():
            setattr(self, key, value)
        self.save(update_fields=["state", "updated_at", *fields.keys()])
        return self

    def __str__(self) -> str:
        return f"AnalysisJob {self.job_id} ({self.state})"