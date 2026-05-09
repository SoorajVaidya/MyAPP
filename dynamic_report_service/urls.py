from django.urls import path

from dynamic_report_service.all_reports import BulkPDFReportsView, BulkPatternReportPDFView
from dynamic_report_service.report_pdf import DownloadReportPDFView, MergedPDFDownloadView, MergedPDFView

from .views import PurchaseTreatmentReport, GenerateTreatmentReport, ReportPDFView, ReportPDFViewTimer, UnpurchaseTreatmentReport, \
    ReportPDFViewBuffer

urlpatterns = [



    path('download-diagnosis-report/', ReportPDFView.as_view(), name='download_diagnosis_report'),
    path('download-diagnosis-report-buffer/', ReportPDFViewBuffer.as_view(), name='download_diagnosis_report'),

    path('purchase-treatment-report/', PurchaseTreatmentReport.as_view(), name='purchase-treatment-report'),

    path('generate-treatment-report/', GenerateTreatmentReport.as_view(), name='deduct-service'),

    path('unpurchase-treatment-report/', UnpurchaseTreatmentReport.as_view(), name='unpurchase-treatment-report'),
    
    path('download-diagnosis-report-timer/', ReportPDFViewTimer.as_view(), name='download_diagnosis_report'),
    
    path('download-all-reports/', BulkPatternReportPDFView.as_view(), name='download_diagnosis_report'),
    
    path('bulk-treatment-reports/', BulkPDFReportsView.as_view(), name='download_diagnosis_report'),
    
    path('merge-pdf-report/', MergedPDFView.as_view(), name='merge-pdf-report'),
    path('merge-pdf-download-report/', MergedPDFDownloadView.as_view(), name='merge-pdf-download-report'),
    
    path('download-merge-pdf-report/', DownloadReportPDFView.as_view(), name='download-merge-pdf-report'),

]
