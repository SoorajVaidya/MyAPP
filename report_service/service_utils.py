from pulse_payments.models import Service
from .models import (
    DiagnosisReportHistory
)
from django.shortcuts import get_object_or_404
from global_utils.service_treatments_map import SERVICE_TREATMENT_MAP
from .serliaizers import (
ReportPageMetdataSerializer)



def get_purchase_service_lists(report_history_id):
    diagnosis_report = get_object_or_404(
        DiagnosisReportHistory, report_history_id=report_history_id
    )
    purchased_service_ids = []

    # Dynamically check treatment fields and append service IDs
    for service_id, treatment_field in SERVICE_TREATMENT_MAP.items():
        if getattr(diagnosis_report, treatment_field, False):
            purchased_service_ids.append(int(service_id))

    return purchased_service_ids

def get_services_for_history(report_history_id):
    services = Service.objects.all().order_by('name')
    purchased_service_ids = get_purchase_service_lists(report_history_id)
    # Serialize services and mark those with matching IDs as purchased
    services_with_purchased_status = []

    for service in services:
        if service.name == "Diagnosis Report":
            continue
        # Check if the service ID is in the purchased_service_ids list and set purchased accordingly
        purchased_status = (
            "Y" if service.service_id in purchased_service_ids else "N"
        )
        service_data = ReportPageMetdataSerializer(service).data
        service_data["purchased"] = purchased_status
        services_with_purchased_status.append(service_data)

    # Fetch all the services
    services = Service.objects.all()

    # Serialize services and mark those with matching IDs as purchased
    services_with_purchased_status = []

    for service in services:
        if service.name == "Diagnosis Report":
            continue
        # Check if the service ID is in the purchased_service_ids list and set purchased accordingly
        purchased_status = (
            "Y" if service.service_id in purchased_service_ids else "N"
        )
        service_data = ReportPageMetdataSerializer(service).data
        service_data["purchased"] = purchased_status
        services_with_purchased_status.append(service_data)

    return services_with_purchased_status