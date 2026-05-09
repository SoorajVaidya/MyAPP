from django.contrib import admin
from .models import PatientsModel

class PatientsAdmin(admin.ModelAdmin):
    # Specify fields to display in the admin panel list view
    list_display = ('get_user_id', 'first_name', 'last_name', 'phone_number', 'gender', 'dob', 'email', 'country', 'state', 'city')

    # Enable filtering by various fields
    list_filter = ('gender', 'country', 'state', 'city')

    # Enable search by user-related fields and patient fields
    search_fields = ('user_profile__id', 'first_name', 'last_name', 'phone_number', 'email')

    # Specify the ordering of records in the admin panel
    ordering = ('first_name',)

    # Custom method to display a clickable link for the related UserProfile ID
    def get_user_id(self, obj):
        if obj.user_profile:
            return f"User #{obj.user_profile.id}"  # Formats as "User #ID"
        return "N/A"

    get_user_id.short_description = 'User ID'  # Sets the column name in the admin list view
    get_user_id.admin_order_field = 'user_profile__id'  # Allows sorting by UserProfile ID

    # Organize fields into fieldsets for better detail view
    fieldsets = (
        ("Personal Information", {
            'fields': ('first_name', 'last_name', 'gender', 'dob', 'phone_number', 'email')
        }),
        ("Location Details", {
            'fields': ('country', 'state', 'city')
        }),
        ("User Profile Association", {
            'fields': ('user_profile',),
            'classes': ('collapse',),  # Optional: Collapsible section
        }),
    )

    # Add related inline models here (if applicable)
    inlines = []  # Example: PatientInline(admin.TabularInline)

# Register the PatientsModel with the customized admin view
admin.site.register(PatientsModel, PatientsAdmin)
