import os
from functools import partial
from b2sdk.v1 import InMemoryAccountInfo, B2Api
from django.core.exceptions import ValidationError
from django.db import models
from django.db import models
from django.core.exceptions import ValidationError
from bucket_extentions.report_storages import ReportsStorage
from django.core.files.base import ContentFile
from django.db import models
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from dynamic_report_service.utils import TreatmentResourceStorage
from oohy_product import settings
from patients.models import PatientsModel
from report_service.models import DiagnosisReportHistory
from report_service.utils import DiagnosticResourceStorage

# Backblaze B2 handles are initialized lazily instead of at import time.
# ``authorize_account`` performs a network round-trip; running it while Django
# populates the app registry made startup — and the entire test suite — crash
# whenever B2 was unreachable or credentials were absent. The module-level
# names ``info`` / ``b2_api`` / ``bucket`` are preserved through PEP 562
# ``__getattr__`` so any caller still referencing them keeps working, but the
# network call now happens on first access rather than on import.
_b2_cache: dict = {}


def _get_b2() -> dict:
    if not _b2_cache:
        info = InMemoryAccountInfo()
        b2_api = B2Api(info)
        b2_api.authorize_account(
            "production", os.getenv("B2_ACCOUNT_ID"), os.getenv("B2_APPLICATION_KEY")
        )
        _b2_cache["info"] = info
        _b2_cache["b2_api"] = b2_api
        _b2_cache["bucket"] = b2_api.get_bucket_by_name(os.getenv("B2_BUCKET_NAME"))
    return _b2_cache


def __getattr__(name):
    # PEP 562 lazy module attribute access for the B2 handles above.
    if name in ("info", "b2_api", "bucket"):
        return _get_b2()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def dynamic_upload_to(instance, filename):
    """
    Dynamically construct the upload path for the images.
    Path format: <InheritedClassName>/Base/<field_name>/<filename>
    """
    class_name = instance.__class__.__name__
    field_name = filename.split(".")[0]  # Get base filename without extension
    return f"{class_name}/Base/{field_name}/{filename}"


class TreatmentHistory(models.Model):
    report_history_id = models.ForeignKey(
        DiagnosisReportHistory,
        on_delete=models.CASCADE,
        related_name="treatment_histories",
    )
    patient_id = models.ForeignKey(
        PatientsModel,
        on_delete=models.CASCADE,
        null=True,
        related_name="treatment_histories",
    )
    auricular_protocol = models.CharField(max_length=255, blank=True, null=True)
    seed_protocol = models.CharField(max_length=255, blank=True, null=True)
    single_point_protocol = models.CharField(max_length=255, blank=True, null=True)
    colour_protocol = models.CharField(max_length=255, blank=True, null=True)
    yoga_protocol = models.CharField(max_length=255, blank=True, null=True)
    mudra_protocol = models.CharField(max_length=255, blank=True, null=True)
    pranayama_protocol = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f"TreatmentHistory for {self.report_history_id}"

    class Meta:
        db_table = "treatment_history"


class TreatmentBase(models.Model):
    """
    Abstract model to store common treatment fields and logic.

    - Ensures only one record can exist.
    - Automatically creates folders specific to the inheriting class in Backblaze storage.
    - Uploads `base_image_1` and `base_image_2` directly into the Base folder with fixed names.
    """

    def upload_to_base_image(instance, filename):
        # Return the fixed path for the image
        return f"{instance.__class__.__name__}/Base/base_image_1.png"

    treatment_note = models.TextField(null=True, blank=True, help_text="Details of the treatment note")
    base_image_1 = models.ImageField(
        blank=True,
        null=True,
        help_text="Image of the treatment base",
        storage=TreatmentResourceStorage(),
        upload_to=upload_to_base_image,
    )
    base_image_2 = models.ImageField(
        blank=True,
        null=True,
        help_text="Another image of the treatment base",
        storage=TreatmentResourceStorage(),
        upload_to=upload_to_base_image,
    )

    def __str__(self):
        return f"Treatment Note: {self.treatment_note[:50]}"  # Returns first 50 characters of the note

    def save(self, *args, **kwargs):
        """
        Overrides save to handle file replacement.
        Deletes the old file in storage if it exists and is being replaced.
        """
        if self.pk:  # Check if the object already exists in the database
            # Get the current instance from the database
            old_instance = self.__class__.objects.filter(pk=self.pk).first()

            if old_instance:
                # Check and delete old file for base_image_1
                if self.base_image_1 and old_instance.base_image_1 != self.base_image_1:
                    old_instance.base_image_1.delete(save=False)

                # Check and delete old file for base_image_2
                if self.base_image_2 and old_instance.base_image_2 != self.base_image_2:
                    old_instance.base_image_2.delete(save=False)

        # Proceed with saving the new instance and new files
        super().save(*args, **kwargs)

    def ensure_folders_exist(self):
        """
        Creates 'Protocols' and 'Base' folders for the inheriting class in Backblaze.
        """
        # Get custom storage instance
        storage = TreatmentResourceStorage()

        # Use the name of the inheriting class to construct folder paths
        class_name = self.__class__.__name__

        # Create folders specific to the inheriting class
        folders = [f"{class_name}/Base", f"{class_name}/Protocols"]
        for folder in folders:
            placeholder_path = f"{folder}/placeholder.txt"
            if not storage.exists(placeholder_path):
                storage.save(placeholder_path, ContentFile("Placeholder file"))

    def delete(self, *args, **kwargs):
        """
        Deletes the model instance and associated images from storage.
        """
        for field_name in ["base_image_1", "base_image_2"]:
            image_field = getattr(self, field_name, None)
            if image_field:
                image_field.delete(save=False)
        super().delete(*args, **kwargs)

    class Meta:
        abstract = True


def upload_to_protocol_image(instance, filename, protocol_image_name):
    return f"{instance.get_related_folder()}/Protocols/Protocol {instance.protocol_number}/{protocol_image_name}.png"


class ProtocolBase(models.Model):

    protocol_number = models.PositiveIntegerField(
        unique=True,
        choices=[(i, str(i)) for i in range(1, 61)],
        null=True,  # Allow null values
        blank=True,
        help_text="Select a unique protocol number (1 to 60).",
    )

    protocol = models.TextField(
        blank=True,
        help_text="Select multiple protocols for Protocol 1 (comma-separated values).",
    )

    disable_root_base_image = models.BooleanField(
        default=False, help_text="Check this box to disable root base image."
    )

    disable_treatment_notes = models.BooleanField(
        default=False, help_text="Check this box to disable base notes."
    )

    protocol_notes = models.TextField(
        blank=True, null=True, help_text="Additional notes for the protocol."
    )

    @staticmethod
    def create_image_field(field_name, protocol_image_name):
        return models.ImageField(
            blank=True,
            null=True,
            help_text=f"Image of the treatment base ({field_name})",
            storage=TreatmentResourceStorage(),
            upload_to=partial(
                upload_to_protocol_image, protocol_image_name=protocol_image_name
            ),
        )

    # Using the helper method to define fields
    base_image_1 = create_image_field.__func__("base_image_1", "base_image_1")
    base_image_2 = create_image_field.__func__("base_image_2", "base_image_2")
    reference_image_1 = create_image_field.__func__(
        "reference_image_1", "reference_image_1"
    )
    reference_image_2 = create_image_field.__func__(
        "reference_image_2", "reference_image_2"
    )
    reference_image_3 = create_image_field.__func__(
        "reference_image_3", "reference_image_3"
    )
    reference_image_4 = create_image_field.__func__(
        "reference_image_4", "reference_image_4"
    )
    reference_image_5 = create_image_field.__func__(
        "reference_image_5", "reference_image_5"
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="%(class)s_created_by",
    )

    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="%(class)s_updated_by",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    def __str__(self):
        return f"{self.__class__.__name__} Protocol"

    def save(self, *args, **kwargs):
        """
        Overrides save to handle file replacement.
        Deletes the old file in storage permanently if it exists and is being replaced.
        """
        if self.pk:  # Check if the object already exists in the database
            old_instance = self.__class__.objects.filter(pk=self.pk).first()

            if not old_instance:
                self.ensure_folders_exist()

            image_fields = [
                "base_image_1",
                "base_image_2",
                "reference_image_1",
                "reference_image_2",
                "reference_image_3",
                "reference_image_4",
                "reference_image_5",
            ]

            # Iterate through the fields and perform the check-and-delete operation
            for field_name in image_fields:
                old_file = (
                    getattr(old_instance, field_name, None) if old_instance else None
                )
                new_file = getattr(self, field_name, None)

                if old_file and old_file != new_file:
                    # Permanently delete the old file
                    old_file.storage.delete(old_file.name)

        super().save(*args, **kwargs)

    def ensure_folders_exist(self):
        """
        Ensures that folders are created dynamically within pre-existing Protocols folders.
        """
        if not self.protocol_number:
            return  # Skip folder creation if protocol_number is not set

        # Get custom storage instance
        storage = TreatmentResourceStorage()

        # Get the related folder name
        related_folder = self.get_related_folder()

        # Construct the specific protocol folder path directly inside the pre-existing Protocols folder
        protocol_folder = f"{related_folder}/Protocols/Protocol {self.protocol_number}"

        # Ensure the specific protocol folder exists
        if not storage.exists(protocol_folder):
            storage.save(
                f"{protocol_folder}/placeholder.txt",
                ContentFile("Placeholder for Protocol"),
            )

    def get_related_folder(self):
        """
        Returns the folder name related to the class.
        """
        if isinstance(self, AuricularProtocolBank):
            return "Auricular"
        elif isinstance(self, MudraProtocolBank):
            return "mudra"
        elif isinstance(self, YogaProtocolBank):
            return "yoga"
        elif isinstance(self, SingleSeedProtocolBank):
            return "singleseed"
        elif isinstance(self, SeedtherapyProtocolBank):
            return "seedtherapy"
        elif isinstance(self, ColourProtocolBank):
            return "colour"
        elif isinstance(self, AcupressureProtocolBank):
            return "acupressure"
        elif isinstance(self, PranayamaProtocolBank):
            return "pranayama"
        raise ValueError("Unknown ProtocolBase subclass")

    def delete(self, *args, **kwargs):
        """
        Deletes the model instance and associated images from storage.
        """
        for field_name in [
            "base_image_1",
            "base_image_2",
            "reference_image_1",
            "reference_image_2",
            "reference_image_3",
            "reference_image_4",
            "reference_image_5",
        ]:
            image_field = getattr(self, field_name, None)
            if image_field:
                image_field.delete(save=False)
        super().delete(*args, **kwargs)


class BaseReportSystem(models.Model):
    report = models.ForeignKey(
        "report_service.Patterns",
        on_delete=models.CASCADE,
        to_field="pattern_number",
        related_name="%(class)s_related_reports",
        help_text="Select the diagnostic report.",
    )
    protocols = models.TextField(
        blank=True,
        help_text="Select multiple protocols as comma-separated values (stored as IDs).",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="%(class)s_created_by",
    )

    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="%(class)s_updated_by",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    def __str__(self):
        return f"{self.__class__.__name__} for Report {self.report}"


class Auricular(TreatmentBase):
    """Model to store treatment notes and base image."""

    class Meta:
        db_table = "auricular"
        verbose_name = "Auricular"
        verbose_name_plural = "Auricular"


class AuricularProtocolBank(ProtocolBase):
    PROTOCOL_CHOICES = [
        ("IH6", "IH6"),
        ("IH7", "IH7"),
        ("IH8", "IH8"),
        ("IH-9", "IH-9"),
        ("SP-5", "SP-5"),
        ("SP-6", "SP-6"),
        ("SP-7", "SP-7"),
        ("SP-8", "SP-8"),
        ("SP-9", "SP-9"),
    ]

    class Meta:
        db_table = "auricular_protocol_bank"
        verbose_name = "Auricular Protocol Bank"
        verbose_name_plural = "Auricular Protocol Bank"


class AuricularReportSystem(BaseReportSystem):
    class Meta:
        db_table = "auricular_report_system"
        verbose_name = "Auricular Report System"
        verbose_name_plural = "Auricular Report System"


class Mudra(TreatmentBase):
    """Model to store Mudra treatment notes and base image."""

    class Meta:
        db_table = "mudra"
        verbose_name = "Mudra"
        verbose_name_plural = "Mudra"


class MudraProtocolBank(ProtocolBase):
    PROTOCOL_CHOICES = [
        ("Aakash Mudra", "Aakash Mudra"),
        ("Adi Mudra", "Adi Mudra"),
        ("Apaan Mudra", "Apaan Mudra"),
    ]

    class Meta:
        db_table = "mudra_protocol_bank"
        verbose_name = "Mudra Protocol Bank"
        verbose_name_plural = "Mudra Protocol Bank"


class MudraReportSystem(BaseReportSystem):
    class Meta:
        db_table = "mudra_report_system"
        verbose_name = "Mudra Report System"
        verbose_name_plural = "Mudra Report System"


class Yoga(TreatmentBase):
    """Model to store Mudra treatment notes and base image."""

    class Meta:
        db_table = "yoga"
        verbose_name = "Yoga"
        verbose_name_plural = "Yoga"


class YogaProtocolBank(ProtocolBase):
    PROTOCOL_CHOICES = [
        ("Yoga 1", "Yoga 1"),
        ("Yoga 2", "Yoga 2"),
        ("Yoga 3", "Yoga 3"),
    ]

    class Meta:
        db_table = "yoga_protocol_bank"
        verbose_name = "Yoga Protocol Bank"
        verbose_name_plural = "Yoga Protocol Bank"


class YogaReportSystem(BaseReportSystem):
    class Meta:
        db_table = "yoga_report_system"
        verbose_name = "Yoga Report System"
        verbose_name_plural = "Yoga Report System"


class Colour(TreatmentBase):
    """Model to store Mudra treatment notes and base image."""

    class Meta:
        db_table = "colour"
        verbose_name = "Colour"
        verbose_name_plural = "Colour"


class ColourProtocolBank(ProtocolBase):

    class Meta:
        db_table = "colour_protocol_bank"
        verbose_name = "Colour Protocol Bank"
        verbose_name_plural = "Colour Protocol Bank"


class ColourReportSystem(BaseReportSystem):
    class Meta:
        db_table = "colour_report_system"
        verbose_name = "Colour Report System"
        verbose_name_plural = "Colour Report System"


class SingleSeed(TreatmentBase):
    """Model to store Mudra treatment notes and base image."""

    class Meta:
        db_table = "single_seed"
        verbose_name = "Single Seed"
        verbose_name_plural = "Single Seed"


class SingleSeedProtocolBank(ProtocolBase):


    ORGAN_CHOICES = [
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
    ]
    YIN_YANG_CHOICES = [
        ("yin", "yin"),
        ("yang", "yang"),
    ]

    organ = models.CharField(
        max_length=20,
        choices=ORGAN_CHOICES,
        help_text="Select an organ",
        null=True,
        blank=True,
    )
    yin_yang = models.CharField(
        max_length=10,
        choices=YIN_YANG_CHOICES,
        help_text="Select either yin or yang",
        null=True,
        blank=True,
    )

    class Meta:
        db_table = "single_seed_protocol_bank"
        verbose_name = "Single Seed Protocol Bank"
        verbose_name_plural = "Single Seed Protocol Bank"


class SingleSeedReportSystem(BaseReportSystem):
    class Meta:
        db_table = "single_seed_report_system"
        verbose_name = "Single Seed Report System"
        verbose_name_plural = "Single Seed Report System"


class Seedtherapy(TreatmentBase):
    """Model to store Mudra treatment notes and base image."""

    class Meta:
        db_table = "seed_therapy"
        verbose_name = "Seed therapy"
        verbose_name_plural = "Seed therapy"


class SeedtherapyProtocolBank(ProtocolBase):

    class Meta:
        db_table = "seed_therapy_protocol_bank"
        verbose_name = "Seed therapy Protocol Bank"
        verbose_name_plural = "Seed therapy Protocol Bank"


class SeedtherapyReportSystem(BaseReportSystem):
    class Meta:
        db_table = "seed_therapy_report_system"
        verbose_name = "Seed therapy Report System"
        verbose_name_plural = "Seed therapy Report System"


class Acupressure(TreatmentBase):
    """Model to store Mudra treatment notes and base image."""

    class Meta:
        db_table = "acupressure"
        verbose_name = "Acupressure"
        verbose_name_plural = "Acupressure"


class AcupressureProtocolBank(ProtocolBase):

    class Meta:
        db_table = "acupressure_protocol_bank"
        verbose_name = "Acupressure Protocol Bank"
        verbose_name_plural = "Acupressure Protocol Bank"


class AcupressureReportSystem(BaseReportSystem):
    class Meta:
        db_table = "acupressure_report_system"
        verbose_name = "Acupressure Report System"
        verbose_name_plural = "Acupressure Report System"


class Pranayama(TreatmentBase):
    """Model to store Mudra treatment notes and base image."""

    class Meta:
        db_table = "pranayama"
        verbose_name = "Pranayama"
        verbose_name_plural = "Pranayama"


class PranayamaProtocolBank(ProtocolBase):
    PROTOCOL_CHOICES = [
        ("Pranayama 1", "Pranayama 1"),
        ("Pranayama 2", "Pranayama 2"),
        ("Pranayama 3", "Pranayama 3"),
    ]

    class Meta:
        db_table = "pranayama_protocol_bank"
        verbose_name = "Pranayama Protocol Bank"
        verbose_name_plural = "Pranayama Protocol Bank"


class PranayamaReportSystem(BaseReportSystem):
    class Meta:
        db_table = "pranayama_report_system"
        verbose_name = "Pranayama Report System"
        verbose_name_plural = "Pranayama Report System"
