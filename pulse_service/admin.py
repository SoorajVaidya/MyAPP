# from django.contrib import admin
# from .models import QuestionSet, Question, Option
#
# class OptionInline(admin.TabularInline):
#     """Allows adding options inline while editing a question"""
#     model = Option
#     extra = 2  # Show two empty option fields by default
#
# class QuestionAdmin(admin.ModelAdmin):
#     """Customize question admin panel"""
#     list_display = ["text", "set"]
#     search_fields = ["text"]
#     list_filter = ["set"]
#     inlines = [OptionInline]  # Add options directly within the question form
#
# class QuestionSetAdmin(admin.ModelAdmin):
#     """Customize question set admin panel"""
#     list_display = ["name"]
#     search_fields = ["name"]
#
# class OptionAdmin(admin.ModelAdmin):
#     """Customize option admin panel"""
#     list_display = ["text", "question", "next_question"]
#     search_fields = ["text"]
#     list_filter = ["question"]
#
# # Register models in Django admin
# admin.site.register(QuestionSet, QuestionSetAdmin)
# admin.site.register(Question, QuestionAdmin)
# admin.site.register(Option, OptionAdmin)
