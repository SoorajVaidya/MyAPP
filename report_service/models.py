# Create your models here.
# models.py
from django.db import models
from django.utils import timezone

from oohy_product import settings
from report_service.utils import DiagnosticResourceStorage


# from report_service.utils import BackblazeB2Storage


class DiagnosisReportHistory(models.Model):
    report_history_id = models.AutoField(primary_key=True)
    user_id = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="report_histories",
        db_column="user_id",
    )
    patient_id = models.ForeignKey(
        "patients.PatientsModel",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_column="patient_id",
    )
    pulse_id = models.ForeignKey(
        "pulse_service.PulseData",
        on_delete=models.CASCADE,
        related_name="report_histories",
        null=True,
        db_column="pulse_id",
    )
    report_pattern_type = models.ForeignKey(
        "Patterns",
        to_field="pattern_number",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="report_pattern_type",
        related_name="diagnosis_reports",
    )

    primary = models.CharField(max_length=100, blank=True, null=True)
    secondary = models.CharField(max_length=100, blank=True, null=True)
    tertiary = models.CharField(max_length=100, blank=True, null=True)
    quaternary = models.CharField(max_length=100, blank=True, null=True)
    quinary = models.CharField(max_length=100, blank=True, null=True)  # New field

    # New nutritional fields
    carbohydrate = models.CharField(max_length=50, blank=True, null=True)
    protein = models.CharField(max_length=50, blank=True, null=True)
    fat = models.CharField(max_length=50, blank=True, null=True)

    wind_yin = models.CharField(max_length=50, blank=True, null=True)
    wind_yang = models.CharField(max_length=50, blank=True, null=True)
    heat_yin = models.CharField(max_length=50, blank=True, null=True)
    heat_yang = models.CharField(max_length=50, blank=True, null=True)
    humid_yin = models.CharField(max_length=50, blank=True, null=True)
    humid_yang = models.CharField(max_length=50, blank=True, null=True)
    dry_yin = models.CharField(max_length=50, blank=True, null=True)
    dry_yang = models.CharField(max_length=50, blank=True, null=True)
    cold_yin = models.CharField(max_length=50, blank=True, null=True)
    cold_yang = models.CharField(max_length=50, blank=True, null=True)

    vata = models.CharField(max_length=50, blank=True, null=True)
    pitta = models.CharField(max_length=50, blank=True, null=True)
    kapha = models.CharField(max_length=50, blank=True, null=True)

    heart_rate = models.FloatField(blank=True, null=True)
    heart_yin = models.FloatField(blank=True, null=True)

    comments = models.TextField(blank=True, null=True)
    suggestions = models.TextField(blank=True, null=True)  # New field for suggestions

    auricular_treatment = models.TextField(
        blank=True, null=True
    )  # Auricular treatment field
    seed_treatment = models.TextField(blank=True, null=True)  # Seed treatment field
    single_point_treatment = models.TextField(
        blank=True, null=True
    )  # Single point treatment field
    colour_treatment = models.TextField(blank=True, null=True)  # Colour treatment field
    yoga_treatment = models.TextField(blank=True, null=True)  # Yoga treatment field
    mudra_treatment = models.TextField(blank=True, null=True)  # Mudra treatment field
    pranayama_treatment = models.TextField(
        blank=True, null=True
    )  # Pranayama treatment field
    acupressure_treatment = models.TextField(blank=True, null=True)

    seed_organ = models.CharField(max_length=100, null=True, blank=True)
    seed_yin_yang = models.CharField(max_length=100, null=True, blank=True)

    pdf_url = models.CharField(
        max_length=255,  # Adjust max_length as needed.
        blank=True,  # Field can be empty in forms.
        null=True,  # Field can be NULL in the database.
    )

    download_pdf = models.CharField(
        max_length=255,  # Adjust max_length as needed.
        blank=True,  # Field can be empty in forms.
        null=True,  # Field can be NULL in the database.
    )

    flag = models.BooleanField(
        default=False, help_text="Set to True for Yes (1) and False for No (0)."
    )

    single_seed_page_number = models.IntegerField(
        blank=True,
        null=True,
        help_text="Stores the page number for the single seed page",
    )

    processed = models.IntegerField(default=0)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "diagnosis_report_history"

    def __str__(self):
        return f"Report History ID: {self.report_history_id}"


class Patterns(models.Model):
    # Choices for pattern_number field (1 to 60)
    PATTERN_NUMBER_CHOICES = [(i, str(i)) for i in range(1, 61)]

    FIVE_ELEMENTS = [
        ("wind", "Wind"),
        ("heat", "Heat"),
        ("cold", "Cold"),
        ("dry", "Dry"),
        ("humid", "Humid"),
    ]

    YIN_YANG_CHOICES = [
        ("yin", "Yin"),
        ("yang", "Yang"),
    ]

    pattern_id = models.AutoField(primary_key=True)  # Primary key
    pattern_number = models.IntegerField(
        choices=PATTERN_NUMBER_CHOICES,
        blank=False,
        null=False,
        unique=True,  # Ensuring pattern_number is unique
    )
    pattern_name = models.CharField(
        max_length=255, blank=True, null=True
    )  # Pattern name
    primary = models.CharField(
        max_length=255, choices=FIVE_ELEMENTS, blank=True, null=True
    )  # Primary field dropdown
    secondary = models.CharField(
        max_length=255, choices=FIVE_ELEMENTS, blank=True, null=True
    )  # Secondary field dropdown
    tertiary = models.CharField(
        max_length=255, choices=FIVE_ELEMENTS, blank=True, null=True
    )  # Tertiary field dropdown
    quaternary = models.CharField(
        max_length=255, choices=FIVE_ELEMENTS, blank=True, null=True
    )  # Quaternary field dropdown
    quinary = models.CharField(
        max_length=255, choices=FIVE_ELEMENTS, blank=True, null=True
    )  # Quinary field dropdown

    yin_yang = models.CharField(
        max_length=10, choices=YIN_YANG_CHOICES, blank=True, null=True
    )  # Yin/Yang dropdown

    # Audit fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="patterns_created",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="patterns_updated",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    def __str__(self):
        # Returning both pattern_name and pattern_number for a more meaningful string representation
        return f"{self.pattern_name} ({self.pattern_number})"

    class Meta:
        db_table = "patterns"


class TreatmentReportHistory(models.Model):
    # Linking each TreatmentReport to a DiagnosisReportHistory
    diagnosis_report = models.ForeignKey(
        "DiagnosisReportHistory",  # Corrected the model name
        on_delete=models.CASCADE,  # When a diagnosis report is deleted, delete related treatment reports
        related_name="treatment_reports",  # Reverse relationship from DiagnosisReportHistory to TreatmentReports
    )

    # Additional fields for the treatment report
    service_id = models.ForeignKey(
        "pulse_payments.Service",
        on_delete=models.CASCADE,
        related_name="report_histories",
        null=False,
        blank=False,
    )
    comments = models.TextField(blank=True, null=True)
    suggestions = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "treatment_report"

    def _str_(self):
        return f"Treatment Report for Diagnosis Report {self.diagnosis_report.report_history_id} - Treatment: {self.treatment_name}"


class QuestionBank(models.Model):
    QUESTION_NUMBER_CHOICES = [(i, str(i)) for i in range(1, 101)]

    question_number = models.IntegerField(
        choices=QUESTION_NUMBER_CHOICES, unique=True, verbose_name="Question Number"
    )
    question = models.TextField(verbose_name="Question")

    class Meta:
        db_table = "question_bank"

    def __str__(self):
        return f"Q{self.question_number}: {self.question}"


class DiagnosticResource(models.Model):
    pattern_number = models.CharField(max_length=50)
    pattern_name = models.CharField(max_length=255)

    pulse_pdf_image = models.ImageField(
        upload_to="diagnostic/pulse_images/pdf/",
        storage=DiagnosticResourceStorage(),
        null=True,
        blank=True,
    )
    language = models.CharField(
        max_length=3,
        choices=[
            ("eng", "eng"),
            ("kan", "kan"),
            ("tel", "tel"),
            ("hin", "hin"),
            # Add more languages as needed
        ],
        default="eng",
        null=True,
        blank=True,
    )
    pulse_pdf_icon_1 = models.ImageField(
        upload_to="diagnostic/pulse_icons/pdf/",
        storage=DiagnosticResourceStorage(),
        null=True,
        blank=True,
    )
    pulse_pdf_icon_2 = models.ImageField(
        upload_to="diagnostic/pulse_icons/pdf/",
        storage=DiagnosticResourceStorage(),
        null=True,
        blank=True,
    )
    pulse_mobile_icon_1 = models.ImageField(
        upload_to="diagnostic/pulse_icons/mobile/",
        storage=DiagnosticResourceStorage(),
        null=True,
        blank=True,
    )
    pulse_mobile_icon_2 = models.ImageField(
        upload_to="diagnostic/pulse_icons/mobile/",
        storage=DiagnosticResourceStorage(),
        null=True,
        blank=True,
    )

    pulse_explanation = models.TextField()

    heart_rate = models.IntegerField(null=True, blank=True)

    tridosha_pdf_graph = models.ImageField(
        upload_to="diagnostic/tridosha_graph/pdf/",
        storage=DiagnosticResourceStorage(),
        null=True,
        blank=True,
    )
    tridosha_mobile_graph = models.ImageField(
        upload_to="diagnostic/tridosha_graph/pdf/",
        storage=DiagnosticResourceStorage(),
        null=True,
        blank=True,
    )
    tridosha_pdf_icon_1 = models.ImageField(
        upload_to="diagnostic/tridosha_icons/pdf/",
        storage=DiagnosticResourceStorage(),
        null=True,
        blank=True,
    )
    tridosha_mobile_icon_1 = models.ImageField(
        upload_to="diagnostic/tridosha_icons/mobile/",
        storage=DiagnosticResourceStorage(),
        null=True,
        blank=True,
    )
    tridosha_pdf_sloka_icon_1 = models.ImageField(
        upload_to="diagnostic/tridosha_sloka_icons/pdf/",
        storage=DiagnosticResourceStorage(),
        null=True,
        blank=True,
    )
    tridosha_mobile_sloka_icon_1 = models.ImageField(
        upload_to="diagnostic/tridosha_sloka_icons/mobile/",
        storage=DiagnosticResourceStorage(),
        null=True,
        blank=True,
    )
    tridosha_values = models.JSONField(null=True, blank=True)
    tridosha_text_1 = models.TextField()
    tridosha_pdf_sloka_icon_2 = models.ImageField(
        upload_to="diagnostic/tridosha_sloka_icons/pdf/",
        storage=DiagnosticResourceStorage(),
        null=True,
        blank=True,
    )
    tridosha_mobile_sloka_icon_2 = models.ImageField(
        upload_to="diagnostic/tridosha_sloka_icons/mobile/",
        storage=DiagnosticResourceStorage(),
        null=True,
        blank=True,
    )
    tridosha_text_2 = models.TextField(null=True, blank=True)
    tridosha_pdf_icon_2 = models.ImageField(
        upload_to="diagnostic/tridosha_icons/pdf/",
        storage=DiagnosticResourceStorage(),
        null=True,
        blank=True,
    )
    tridosha_mobile_icon_2 = models.ImageField(
        upload_to="diagnostic/tridosha_icons/mobile/",
        storage=DiagnosticResourceStorage(),
        null=True,
        blank=True,
    )
    tridosha_text_3 = models.TextField(null=True, blank=True)
    tridosha_pdf_icon_3 = models.ImageField(
        upload_to="diagnostic/tridosha_icons/pdf/",
        storage=DiagnosticResourceStorage(),
        null=True,
        blank=True,
    )
    tridosha_mobile_icon_3 = models.ImageField(
        upload_to="diagnostic/tridosha_icons/mobile/",
        storage=DiagnosticResourceStorage(),
        null=True,
        blank=True,
    )

    yin_yang_pdf_graph = models.ImageField(
        upload_to="diagnostic/yin_yang_graph/pdf/",
        storage=DiagnosticResourceStorage(),
        null=True,
        blank=True,
    )
    yin_yang_mobile_graph = models.ImageField(
        upload_to="diagnostic/tridosha_icons/mobile/",
        storage=DiagnosticResourceStorage(),
        null=True,
        blank=True,
    )
    yin_yang = models.JSONField(null=True, blank=True)

    organ_rel_pdf_image = models.ImageField(
        upload_to="diagnostic/organ_rel/pdf/",
        storage=DiagnosticResourceStorage(),
        null=True,
        blank=True,
    )
    organ_rel_mobile_image = models.ImageField(
        upload_to="diagnostic/organ_rel/mobile/",
        storage=DiagnosticResourceStorage(),
        null=True,
        blank=True,
    )

    organ_rel_text1 = models.TextField()
    organ_rel_text2 = models.TextField()
    organ_rel_text3 = models.TextField()
    organ_rel_text4 = models.TextField()
    organ_rel_pdf_icon1 = models.ImageField(
        upload_to="diagnostic/organ_images/pdf/",
        storage=DiagnosticResourceStorage(),
        null=True,
        blank=True,
    )
    organ_rel_mobile_icon1 = models.ImageField(
        upload_to="diagnostic/organ_images/mobile/",
        storage=DiagnosticResourceStorage(),
        null=True,
        blank=True,
    )
    organ_rel_pdf_icon2 = models.ImageField(
        upload_to="diagnostic/organ_images/pdf/",
        storage=DiagnosticResourceStorage(),
        null=True,
        blank=True,
    )
    organ_rel_mobile_icon2 = models.ImageField(
        upload_to="diagnostic/organ_images/mobile/",
        storage=DiagnosticResourceStorage(),
        null=True,
        blank=True,
    )
    organ_rel_pdf_icon3 = models.ImageField(
        upload_to="diagnostic/organ_images/pdf/",
        storage=DiagnosticResourceStorage(),
        null=True,
        blank=True,
    )
    organ_rel_mobile_icon3 = models.ImageField(
        upload_to="diagnostic/organ_images/mobile/",
        storage=DiagnosticResourceStorage(),
        null=True,
        blank=True,
    )

    nature_correlation_text = models.TextField()
    nature_correlation_pdf_image = models.ImageField(
        upload_to="diagnostic/nature_correlation/pdf/",
        storage=DiagnosticResourceStorage(),
        null=True,
        blank=True,
    )
    nature_correlation_mobile_image = models.ImageField(
        upload_to="diagnostic/nature_correlation/mobile/",
        storage=DiagnosticResourceStorage(),
        null=True,
        blank=True,
    )

    thought_pattern_text = models.TextField()
    thought_pattern_pdf_image = models.ImageField(
        upload_to="diagnostic/thought_patterns/pdf/",
        storage=DiagnosticResourceStorage(),
        null=True,
        blank=True,
    )
    thought_pattern_mobile_image = models.ImageField(
        upload_to="diagnostic/thought_patterns/mobile/",
        storage=DiagnosticResourceStorage(),
        null=True,
        blank=True,
    )

    fm_pdf_graph = models.ImageField(
        upload_to="diagnostic/fm_graph/pdf/",
        storage=DiagnosticResourceStorage(),
        null=True,
        blank=True,
    )
    fm_mobile_graph = models.ImageField(
        upload_to="diagnostic/fm_graph/mobile/",
        storage=DiagnosticResourceStorage(),
        null=True,
        blank=True,
    )
    fm_values = models.JSONField(null=True, blank=True)
    fm_text = models.TextField()
    fm_pdf_icon = models.ImageField(
        upload_to="diagnostic/fm_icons/pdf/",
        storage=DiagnosticResourceStorage(),
        null=True,
        blank=True,
    )
    fm_mobile_icon = models.ImageField(
        upload_to="diagnostic/fm_icons/mobile/",
        storage=DiagnosticResourceStorage(),
        null=True,
        blank=True,
    )

    ai_prediction_text1 = models.TextField(null=True, blank=True)
    ai_prediction_text2 = models.TextField(null=True, blank=True)
    ai_prediction_text3 = models.TextField(null=True, blank=True)
    ai_prediction_text4 = models.TextField(null=True, blank=True)
    ai_prediction_text5 = models.TextField(null=True, blank=True)
    ai_prediction_text6 = models.TextField(null=True, blank=True)
    ai_prediction_text7 = models.TextField(null=True, blank=True)
    ai_prediction_text8 = models.TextField(null=True, blank=True)
    ai_prediction_pdf_icon1 = models.ImageField(
        upload_to="diagnostic/ai_predictions/pdf/",
        storage=DiagnosticResourceStorage(),
        null=True,
        blank=True,
    )
    ai_prediction_mobile_icon1 = models.ImageField(
        upload_to="diagnostic/ai_predictions/mobile/",
        storage=DiagnosticResourceStorage(),
        null=True,
        blank=True,
    )

    ai_prediction_pdf_icon2 = models.ImageField(
        upload_to="diagnostic/ai_predictions/pdf/",
        storage=DiagnosticResourceStorage(),
        null=True,
        blank=True,
    )
    ai_prediction_mobile_icon2 = models.ImageField(
        upload_to="diagnostic/ai_predictions/mobile/",
        storage=DiagnosticResourceStorage(),
        null=True,
        blank=True,
    )
    ai_prediction_pdf_icon3 = models.ImageField(
        upload_to="diagnostic/ai_predictions/pdf/",
        storage=DiagnosticResourceStorage(),
        null=True,
        blank=True,
    )
    ai_prediction_mobile_icon3 = models.ImageField(
        upload_to="diagnostic/ai_predictions/mobile/",
        storage=DiagnosticResourceStorage(),
        null=True,
        blank=True,
    )

    ai_prediction_pdf_icon4 = models.ImageField(
        upload_to="diagnostic/ai_predictions/pdf/",
        storage=DiagnosticResourceStorage(),
        null=True,
        blank=True,
    )
    ai_prediction_mobile_icon4 = models.ImageField(
        upload_to="diagnostic/ai_predictions/mobile/",
        storage=DiagnosticResourceStorage(),
        null=True,
        blank=True,
    )

    body_pdf_image = models.ImageField(
        upload_to="diagnostic/body_images/pdf/",
        storage=DiagnosticResourceStorage(),
        null=True,
        blank=True,
    )
    body_mobile_image = models.ImageField(
        upload_to="diagnostic/body_images/mobile/",
        storage=DiagnosticResourceStorage(),
        null=True,
        blank=True,
    )
    body_anotations = models.CharField(
        max_length=255, blank=True, help_text="Enter comma-separated annotations."
    )

    # Dietary Solutions (6 text fields)
    dietary_solution_1 = models.TextField(blank=True, null=True)
    dietary_solution_2 = models.TextField(blank=True, null=True)
    dietary_solution_3 = models.TextField(blank=True, null=True)
    dietary_solution_4 = models.TextField(blank=True, null=True)
    dietary_solution_5 = models.TextField(blank=True, null=True)
    dietary_solution_6 = models.TextField(blank=True, null=True)

    # ...then the corresponding icon fields.
    dietary_solution_pdf_icon_1 = models.ImageField(
        upload_to="diagnostic/dietary_solution_icons/pdf/",
        storage=DiagnosticResourceStorage(),
        null=True,
        blank=True,
    )
    dietary_solution_mobile_icon_1 = models.ImageField(
        upload_to="diagnostic/dietary_solution_icons/mobile/",
        storage=DiagnosticResourceStorage(),
        null=True,
        blank=True,
    )
    dietary_solution_pdf_icon_2 = models.ImageField(
        upload_to="diagnostic/dietary_solution_icons/pdf/",
        storage=DiagnosticResourceStorage(),
        null=True,
        blank=True,
    )
    dietary_solution_mobile_icon_2 = models.ImageField(
        upload_to="diagnostic/dietary_solution_icons/mobile/",
        storage=DiagnosticResourceStorage(),
        null=True,
        blank=True,
    )
    dietary_solution_pdf_icon_3 = models.ImageField(
        upload_to="diagnostic/dietary_solution_icons/pdf/",
        storage=DiagnosticResourceStorage(),
        null=True,
        blank=True,
    )
    dietary_solution_mobile_icon_3 = models.ImageField(
        upload_to="diagnostic/dietary_solution_icons/mobile/",
        storage=DiagnosticResourceStorage(),
        null=True,
        blank=True,
    )
    dietary_solution_pdf_icon_4 = models.ImageField(
        upload_to="diagnostic/dietary_solution_icons/pdf/",
        storage=DiagnosticResourceStorage(),
        null=True,
        blank=True,
    )
    dietary_solution_mobile_icon_4 = models.ImageField(
        upload_to="diagnostic/dietary_solution_icons/mobile/",
        storage=DiagnosticResourceStorage(),
        null=True,
        blank=True,
    )
    dietary_solution_pdf_icon_5 = models.ImageField(
        upload_to="diagnostic/dietary_solution_icons/pdf/",
        storage=DiagnosticResourceStorage(),
        null=True,
        blank=True,
    )
    dietary_solution_mobile_icon_5 = models.ImageField(
        upload_to="diagnostic/dietary_solution_icons/mobile/",
        storage=DiagnosticResourceStorage(),
        null=True,
        blank=True,
    )
    dietary_solution_pdf_icon_6 = models.ImageField(
        upload_to="diagnostic/dietary_solution_icons/pdf/",
        storage=DiagnosticResourceStorage(),
        null=True,
        blank=True,
    )
    dietary_solution_mobile_icon_6 = models.ImageField(
        upload_to="diagnostic/dietary_solution_icons/mobile/",
        storage=DiagnosticResourceStorage(),
        null=True,
        blank=True,
    )

    # Added: Emotional & Lifestyle Corrections (4 text fields)
    emotional_lifestyle_correction_1 = models.TextField(blank=True, null=True)
    emotional_lifestyle_correction_2 = models.TextField(blank=True, null=True)
    emotional_lifestyle_correction_3 = models.TextField(blank=True, null=True)
    emotional_lifestyle_correction_4 = models.TextField(blank=True, null=True)

    # Added: Corresponding PDF icons for Emotional & Lifestyle Corrections (4 fields)
    emotional_lifestyle_correction_pdf_icon_1 = models.ImageField(
        upload_to="diagnostic/emotional_lifestyle_correction_icons/pdf/",
        storage=DiagnosticResourceStorage(),
        null=True,
        blank=True,
    )
    emotional_lifestyle_correction_pdf_icon_2 = models.ImageField(
        upload_to="diagnostic/emotional_lifestyle_correction_icons/pdf/",
        storage=DiagnosticResourceStorage(),
        null=True,
        blank=True,
    )
    emotional_lifestyle_correction_pdf_icon_3 = models.ImageField(
        upload_to="diagnostic/emotional_lifestyle_correction_icons/pdf/",
        storage=DiagnosticResourceStorage(),
        null=True,
        blank=True,
    )
    emotional_lifestyle_correction_pdf_icon_4 = models.ImageField(
        upload_to="diagnostic/emotional_lifestyle_correction_icons/pdf/",
        storage=DiagnosticResourceStorage(),
        null=True,
        blank=True,
    )

    def __str__(self):
        return self.pattern_name

    class Meta:
        db_table = "diagnostic_resource"


class SymptomsQuestions(models.Model):

    YIN_YANG_CHOICES = (
        ("yin", "Yin"),
        ("yang", "Yang"),
    )

    ORGAN_CHOICES = (
        ("Lv", "Lv"),
        ("GB", "GB"),
        ("Heart", "Heart"),
        ("SI", "SI"),
        ("Sp", "Sp"),
        ("St", "St"),
        ("Lun", "Lun"),
        ("LI", "LI"),
        ("Kidney", "Kidney"),
        ("UB", "UB"),
    )

    name = models.CharField(
        max_length=100, help_text="Category name, e.g., 'wind yin', 'cold yin', etc."
    )
    yin_yang = models.CharField(
        max_length=10, choices=YIN_YANG_CHOICES, help_text="Either 'yin' or 'yang'"
    )
    organ = models.CharField(
        max_length=10,
        choices=ORGAN_CHOICES,
        null=True,
        blank=True,
        help_text="Select an organ: Lv, GB, Heart, SI, Sp, St, Lun, LI, v",
    )
    question_number = models.IntegerField(
        unique=True, null=False, help_text="The sequential number for the question"
    )
    question = models.TextField(help_text="The text of the question")
    question_kannada = models.TextField(
        help_text="The text of the Kannada question",
        null=True,
        blank=True,
    )
    options = models.JSONField(
        default=list, help_text="List of options, e.g., ['Yes', 'No']"
    )
    picture_url = models.URLField(
        blank=True, null=True, help_text="Optional URL of a related picture"
    )
    disable = models.BooleanField(
        default=False, help_text="Disable this question. Check to disable."
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="created_symptomsquestions",
        help_text="Authenticated user who created the question",
    )
    # Reference to the authenticated user who last updated this record
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="updated_symptomsquestions",
        help_text="Authenticated user who last updated the question",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} - {self.question[:50]}"

    class Meta:
        db_table = "symptomsquestions"


class DiagnosisAnswer(models.Model):
    diagnosis_report_history = models.ForeignKey(
        "DiagnosisReportHistory",
        on_delete=models.CASCADE,
        db_column="report_history_id",
        related_name="diagnosis_answers",
    )
    # Assuming that question_number is unique in SymptomsQuestions and can serve as a foreign key
    symptom_question = models.ForeignKey(
        "SymptomsQuestions",
        on_delete=models.CASCADE,
        to_field="question_number",
        db_column="question_number",
        related_name="diagnosis_answers",
    )
    answer = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Report {self.diagnosis_report_history.report_history_id} - Question {self.symptom_question.question_number}: {self.answer}"
