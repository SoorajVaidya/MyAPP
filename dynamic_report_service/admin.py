from django.contrib import admin

from .forms import (
    AcupressureProtocolBankForm,
    AcupressureReportSystemForm,
    AuricularProtocolBankForm,
    AuricularReportSystemForm,
    MudraReportSystemForm,
    MudraProtocolBankForm,
    PranayamaProtocolBankForm,
    PranayamaReportSystemForm,
    SeedtherapyProtocolBankForm,
    SeedtherapyReportSystemForm,
    SingleSeedProtocolBankForm,
    SingleSeedReportSystemForm,
    YogaProtocolBankForm,
    YogaReportSystemForm,
    ColourProtocolBankForm,
    ColourReportSystemForm,
)
from .models import (
    Acupressure,
    AcupressureProtocolBank,
    AcupressureReportSystem,
    AuricularProtocolBank,
    AuricularReportSystem,
    MudraProtocolBank,
    MudraReportSystem,
    Auricular,
    Mudra,
    Pranayama,
    PranayamaProtocolBank,
    PranayamaReportSystem,
    Seedtherapy,
    SeedtherapyProtocolBank,
    SeedtherapyReportSystem,
    SingleSeed,
    SingleSeedProtocolBank,
    SingleSeedReportSystem,
    Yoga,
    YogaProtocolBank,
    YogaReportSystem,
    Colour,
    ColourProtocolBank,
    ColourReportSystem,
)


class BaseAdmin(admin.ModelAdmin):
    list_display = ("id", "treatment_note_preview", "base_image_1")
    search_fields = ("treatment_note",)
    list_filter = ("treatment_note",)
    readonly_fields = ("id",)

    def treatment_note_preview(self, obj):
        """Displays a preview of the treatment note (first 50 characters)."""
        return obj.treatment_note[:50] if obj.treatment_note else "No note"

    treatment_note_preview.short_description = "Treatment Note Preview"


class BaseProtocolBankAdmin(admin.ModelAdmin):
    list_display = (
        "protocol_number",
        "protocol",
        "protocol_notes",
        "base_image_1",
        "base_image_2",
        "reference_image_1",
        "reference_image_2",
        "reference_image_3",
        "reference_image_4",
        "reference_image_5",
        "created_by",
        "updated_by",
        "created_at",
        "updated_at",
    )
    readonly_fields = ("created_at", "updated_at", "created_by", "updated_by")
    exclude = ("created_by", "updated_by")  # These fields are set programmatically

    def save_model(self, request, obj, form, change):
        """Customize the save behavior for setting created_by and updated_by."""
        if not change:  # If creating a new object
            obj.created_by = request.user
        obj.updated_by = request.user  # Always update the updated_by field
        obj.full_clean()  # Ensure validation is triggered
        super().save_model(request, obj, form, change)

    def get_form(self, request, obj=None, **kwargs):
        """Customize the form to dynamically manage read-only fields."""
        form = super().get_form(request, obj, **kwargs)
        if not request.user.is_superuser:
            # Example: Disable fields for non-superusers
            if "disable_treatment_notes" in form.base_fields:
                form.base_fields["disable_treatment_notes"].disabled = True
        return form


class BaseReportSystemAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "report",
        "get_protocols_display",
        "created_by",
        "updated_by",
        "created_at",
        "updated_at",
    )
    readonly_fields = ("created_at", "updated_at", "created_by", "updated_by")
    exclude = ("created_by", "updated_by")

    def get_protocols_display(self, obj):
        if obj.protocols:
            protocol_ids = [
                int(id_) for id_ in obj.protocols.split(",") if id_.isdigit()
            ]
            protocols = self.protocol_model.objects.filter(id__in=protocol_ids)
            return ", ".join(
                [f"{self.protocol_label} {protocol.id}" for protocol in protocols]
            )
        return "None"

    get_protocols_display.short_description = "Protocols"

    def save_model(self, request, obj, form, change):
        if not change:  # If creating a new object
            obj.created_by = request.user
        obj.updated_by = request.user  # Always update the updated_by field
        super().save_model(request, obj, form, change)


@admin.register(Auricular)
class AuricularAdmin(BaseAdmin):
    pass


@admin.register(AuricularProtocolBank)
class AuricularProtocolBankAdmin(BaseProtocolBankAdmin):
    form = AuricularProtocolBankForm  # Attach the custom form if required


@admin.register(AuricularReportSystem)
class AuricularReportSystemAdmin(BaseReportSystemAdmin):
    form = AuricularReportSystemForm
    protocol_model = MudraProtocolBank
    protocol_label = "Auricular Protocol"


@admin.register(Mudra)
class MudraAdmin(BaseAdmin):
    pass


@admin.register(MudraProtocolBank)
class MudraProtocolBankAdmin(BaseProtocolBankAdmin):
    form = MudraProtocolBankForm


@admin.register(MudraReportSystem)
class MudraReportSystemAdmin(BaseReportSystemAdmin):
    form = MudraReportSystemForm
    protocol_model = MudraProtocolBank
    protocol_label = "Mudra Protocol"


@admin.register(Yoga)
class YogaAdmin(BaseAdmin):
    pass


@admin.register(YogaProtocolBank)
class YogaProtocolBankAdmin(BaseProtocolBankAdmin):
    form = YogaProtocolBankForm


@admin.register(YogaReportSystem)
class YogaReportSystemAdmin(BaseReportSystemAdmin):
    form = YogaReportSystemForm
    protocol_model = YogaProtocolBank
    protocol_label = "Yoga Protocol"


@admin.register(Colour)
class ColourAdmin(BaseAdmin):
    pass


@admin.register(ColourProtocolBank)
class ColourProtocolBankAdmin(BaseProtocolBankAdmin):
    form = ColourProtocolBankForm


@admin.register(ColourReportSystem)
class ColouReportSystemAdmin(BaseReportSystemAdmin):
    form = ColourReportSystemForm
    protocol_model = ColourProtocolBank
    protocol_label = "Colour Protocol"


@admin.register(SingleSeed)
class SingleSeedAdmin(BaseAdmin):
    pass


@admin.register(SingleSeedProtocolBank)
class SingleSeedProtocolBankAdmin(BaseProtocolBankAdmin):
    form = SingleSeedProtocolBankForm
    list_display = (
        "protocol",  # existing protocol text field if needed
        "protocol_notes",
        "organ",  # new field
        "yin_yang",  # new field
        "base_image_1",
        "base_image_2",
        "reference_image_1",
        "reference_image_2",
        "reference_image_3",
        "reference_image_4",
        "created_by",
        "updated_by",
        "created_at",
        "updated_at",
    )


@admin.register(SingleSeedReportSystem)
class SingleSeedReportSystemAdmin(BaseReportSystemAdmin):
    form = SingleSeedReportSystemForm
    protocol_model = SingleSeedProtocolBank
    protocol_label = "Single Seed Protocol"


@admin.register(Seedtherapy)
class SeedtherapyAdmin(BaseAdmin):
    pass


@admin.register(SeedtherapyProtocolBank)
class SeedtherapyProtocolBankAdmin(BaseProtocolBankAdmin):
    form = SeedtherapyProtocolBankForm


@admin.register(SeedtherapyReportSystem)
class SeedtherapyReportSystemAdmin(BaseReportSystemAdmin):
    form = SeedtherapyReportSystemForm
    protocol_model = SeedtherapyProtocolBank
    protocol_label = "Seed therapy Protocol"


@admin.register(Acupressure)
class AcupressureAdmin(BaseAdmin):
    pass


@admin.register(AcupressureProtocolBank)
class AcupressureProtocolBankAdmin(BaseProtocolBankAdmin):
    form = AcupressureProtocolBankForm


@admin.register(AcupressureReportSystem)
class AcupressureReportSystemAdmin(BaseReportSystemAdmin):
    form = AcupressureReportSystemForm
    protocol_model = AcupressureProtocolBank
    protocol_label = "Acupressure Protocol"


@admin.register(Pranayama)
class PranayamaAdmin(BaseAdmin):
    pass


@admin.register(PranayamaProtocolBank)
class PranayamaProtocolBankAdmin(BaseProtocolBankAdmin):
    form = PranayamaProtocolBankForm


@admin.register(PranayamaReportSystem)
class PranayamaReportSystemAdmin(BaseReportSystemAdmin):
    form = PranayamaReportSystemForm
    protocol_model = PranayamaProtocolBank
    protocol_label = "Pranayama Protocol"
