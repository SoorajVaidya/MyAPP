from django.contrib import admin
from django import forms
from django.urls import path, reverse
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.contrib import admin
from django.utils.safestring import mark_safe
from django.contrib import admin
# from .models import QuestionsSet, QuestionLink, QuestionModel
from .models import Patterns, QuestionBank, DiagnosticResource
from django.contrib import admin


from django.contrib import admin
from .models import SymptomsQuestions



class CreatedUpdatedByAdmin(admin.ModelAdmin):
    """
    Base admin class to automatically set created_by and updated_by fields.
    """
    exclude = ('created_by', 'updated_by')  # Hide these fields in the admin form

    def save_model(self, request, obj, form, change):
        # Automatically set created_by on creation
        if not obj.pk:  # Object is being created
            obj.created_by = request.user
        # Automatically set updated_by on every save
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)

class PatternsAdmin(admin.ModelAdmin):
    list_display = (
        'pattern_number', 'pattern_name', 'primary', 'secondary', 
        'tertiary', 'quaternary', 'yin_yang', 'created_at', 'updated_at', 
        'created_by', 'updated_by'
    )
    search_fields = ('pattern_name', 'primary', 'secondary', 'tertiary', 'quaternary')
    list_filter = ('pattern_number', 'yin_yang', 'created_by', 'updated_by')
    readonly_fields = ('created_by', 'updated_by', 'created_at', 'updated_at')

    def save_model(self, request, obj, form, change):
        # For new objects, set created_by to the current authenticated user
        if not change:
            obj.created_by = request.user
        # Always update updated_by to the current user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)

admin.site.register(Patterns, PatternsAdmin)




@admin.register(QuestionBank)
class QuestionBankAdmin(admin.ModelAdmin):
    list_display = ('question_number', 'question')
    search_fields = ('question',)
    list_filter = ('question_number',)
    ordering = ('question_number',)




class DiagnosticResourceAdmin(admin.ModelAdmin):
    list_display = ['pattern_name', 'pattern_number']

admin.site.register(DiagnosticResource, DiagnosticResourceAdmin)




@admin.register(SymptomsQuestions)
class SymptomsQuestionsAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'yin_yang', 'question', 'disable', 'created_by', 'created_at')
    list_filter = ('name', 'yin_yang', 'disable')
    search_fields = ('question', 'name')
    # Remove created_by and updated_by from the form so that they don't show a dropdown.
    exclude = ('created_by', 'updated_by',)

    def save_model(self, request, obj, form, change):
        if not change:
            # When creating a new record, set the created_by field
            obj.created_by = request.user
        # Always set the updated_by field on save
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)