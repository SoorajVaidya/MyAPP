from django.contrib import admin
from .models import MinimumBalance, Wallet, WalletPaymentsDetails, WalletTransactionDetails, Service

# Register Wallet and Wallet-related models
admin.site.register(Wallet)
admin.site.register(WalletPaymentsDetails)
admin.site.register(WalletTransactionDetails)

@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ('service_id', 'name', 'price', 'number_of_pages', 'description', 'image_url', 'updated_at',)  # Added 'number_of_pages'
    list_editable = ('price', 'number_of_pages', 'image_url')  # Made 'number_of_pages' editable in the list view
    search_fields = ('name',)
    ordering = ('name',)
    list_filter = ('updated_at',)
    readonly_fields = ('created_at', 'updated_at')

    def get_readonly_fields(self, request, obj=None):
        """
        Ensure the name of 'Minimum Balance' service cannot be changed.
        """
        if obj and obj.name == 'Minimum Balance':
            return self.readonly_fields + ('name',)
        return self.readonly_fields

    def has_delete_permission(self, request, obj=None):
        """
        Prevent deletion of the 'Minimum Balance' service.
        """
        if obj and obj.name == 'Minimum Balance':
            return False
        return super().has_delete_permission(request, obj)

    def save_model(self, request, obj, form, change):
        """
        Set the updated_by field to the current user when saving changes.
        """
        if change:
            obj.updated_by = request.user
        super().save_model(request, obj, form, change)
        
        
class MinimumBalanceAdmin(admin.ModelAdmin):
    list_display = ('id', 'minimum_balance', 'created_at', 'updated_at', 'created_by', 'updated_by')
    readonly_fields = ('created_at', 'updated_at', 'created_by', 'updated_by')

    def has_add_permission(self, request):
        # Prevent adding a new record if one already exists
        if self.model.objects.count() >= 1:
            return False
        return super().has_add_permission(request)

    def save_model(self, request, obj, form, change):
        # For new objects, set created_by to the current authenticated user
        if not change:
            obj.created_by = request.user
        # Always update updated_by to the current user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)

admin.site.register(MinimumBalance, MinimumBalanceAdmin)