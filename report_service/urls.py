from django.urls import path, include
from rest_framework.routers import DefaultRouter


from .views import GenerateDiagnosisReport, GetQuestionsByReportHistoryAPIView, ReportHistory, CreateDiagnosisHistory, CreateTreatmentHistory, \
    PatientHistoryListView, AddCommentAPIView, AddSuggestionAPIView, PatientHistorySingleReportView, ReportPageMetadata, \
    GetQuestionsAPI, ScrollableDiagnosisReportView

urlpatterns = [
    path('report-history/', ReportHistory.as_view(), name='report_history_list'),


    path('patient-history-list-view/', PatientHistoryListView.as_view(), name='treatment-history-datetime'),
    path('patient-history-single-report-view/<int:report_history_id>/', PatientHistorySingleReportView.as_view(),
         name='diagnosis-report-detail'),
    path('report-page-metdata/', ReportPageMetadata.as_view(),
         name='get-services-by-report'),

    path('get-questions/', GetQuestionsAPI.as_view(), name='get_questions'),
    path('add-comment/', AddCommentAPIView.as_view(), name='add-comment'),
    path('add-suggestion/', AddSuggestionAPIView.as_view(), name='add-suggestion'),

    # Not directly used in frontend, but internally used in backend
    path('create-diagnosis-history/', CreateDiagnosisHistory.as_view(), name='diagnosis-report-history-create'),
    path('create-treatment-history/', CreateTreatmentHistory.as_view(), name='treatment-report-history-create'),
    path('generate-diagnosis-report/', GenerateDiagnosisReport.as_view(), name='diagnoize_report'),

    path('diagnosis-report-scrollable/', ScrollableDiagnosisReportView.as_view(), name='diagnosis_report_scrollable'),

    path('assessment/report/', GetQuestionsByReportHistoryAPIView.as_view(), name='assessment_by_report'),


]