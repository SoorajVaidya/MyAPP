from django.contrib import admin
from .models import FactorySenorList, RegisterSensor

# Register both models in the admin panel
@admin.register(FactorySenorList)
class FactorySenorListAdmin(admin.ModelAdmin):
    exclude = ('created_by',)  # Exclude 'created_by' from the admin form

    def save_model(self, request, obj, form, change):
        """
        Automatically set 'created_by' to the logged-in user during creation.
        """
        if not obj.pk:  # If the object is being created
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(RegisterSensor)
class RegisterSensorAdmin(admin.ModelAdmin):
    # Specify the fields to display in the admin list view, including user ID
    list_display = ('unique_id', 'user', 'user_id', 'created_at', 'updated_at')

    # Add search functionality for relevant fields
    search_fields = ('unique_id', 'user__username', 'user__email')

    # Add filtering options for fields
    list_filter = ('created_at', 'updated_at', 'is_active', 'is_admin')

    # Helper method to display the user ID
    def user_id(self, obj):
        return obj.user.id
    user_id.short_description = "User ID"


