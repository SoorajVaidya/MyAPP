import os
import random

from django.conf import settings
from django.http import Http404

from dynamic_report_service.models import (
    Acupressure,
    AcupressureProtocolBank,
    AcupressureReportSystem,
    AuricularReportSystem,
    AuricularProtocolBank,
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
    YogaProtocolBank,
    YogaReportSystem,
    Yoga,
    Colour,
    ColourProtocolBank,
    ColourReportSystem,
)
from dynamic_report_service.utils import color_therapy, highlight_points, multi_seed_image_generation, process_image_and_annotations
from oohy_product import settings
from report_service.models import DiagnosisReportHistory


def generate_auricular_report(request_data):
    """
    Generate an Auricular report based on the provided request data.

    Args:
        request_data (dict): The data from the request, must include 'pattern_id'.

    Returns:
        dict: A response dictionary containing status_code, message, and data/errors.
    """
    # Retrieve pattern_id directly from request data
    pattern_id = request_data.get("pattern_id")
    patient_id = request_data.get("patient_id")
    
    if not pattern_id or not patient_id:
        return {
            "status": "error",
            "errors": {"detail": "pattern_id and patient_id are required."},
            "status_code": 400,
        }

    try:
        # Fetch the AuricularReportSystem object using pattern_id
        auricular_report_system = AuricularReportSystem.objects.get(
            report_id=pattern_id
        )
    except AuricularReportSystem.DoesNotExist:
        return {
            "status": "error",
            "errors": {
                "detail": f"AuricularReportSystem with report_id {pattern_id} not found."
            },
            "status_code": 404,
        }

    # Retrieve protocols
    protocols = auricular_report_system.protocols
    if not protocols:
        return {
            "status": "error",
            "errors": {
                "detail": "No protocols associated with this AuricularReportSystem."
            },
            "status_code": 404,
        }

    # Fetch the AuricularProtocolBank object using the first protocol (assuming comma-separated values)
    protocol_ids = [p.strip() for p in protocols.split(",")]
    
    # Determine how many previous reports have a protocol assigned for this patient and pattern
    previous_count = DiagnosisReportHistory.objects.filter(
        patient_id=patient_id,
        report_pattern_type=pattern_id,
        auricular_treatment__isnull=False
    ).count()
    
    # Use round-robin logic to select the next protocol
    index = previous_count % len(protocol_ids)
    selected_protocol = protocol_ids[index]
    
    # print(70, protocol_ids)
    try:
        auricular_protocol = AuricularProtocolBank.objects.get(protocol_number=selected_protocol)
        
    except AuricularProtocolBank.DoesNotExist:
        return {
            "status": "error",
            "errors": {
                "detail": f"AuricularProtocolBank with id {selected_protocol} not found."
            },
            "status_code": 404,
        }

    # Retrieve the protocol value
    protocol_value = auricular_protocol.protocol
    # print(85, protocol_value)
    if not protocol_value:
        return {
            "status": "error",
            "errors": {"detail": "No protocol value found in AuricularProtocolBank."},
            "status_code": 404,
        }

    auricular = Auricular.objects.first()
    if not auricular:
        raise Http404("Auricular object does not exist.")

    # Check if the image exists and fetch its URL
    if auricular.base_image_1:
        image_url = (
            auricular.base_image_1.url
        )  # Assuming no need for absolute URI in function
    else:
        return {
            "status": "error",
            "errors": {"detail": "Base image not found for Auricular."},
            "status_code": 404,
        }

    annotation_file = os.path.join(
        settings.BASE_DIR, "image_processing/auricular_coordinates.txt"
    )

    # Call the helper function
    image_base64, highlighted_points = process_image_and_annotations(
        image_url, annotation_file, protocol_value
    )

    if isinstance(image_base64, dict):
        return image_base64  # Return early in case of error

    # Fetch Treatment note from auricular
    treatment_note = auricular.treatment_note

    # Fetch protocol_notes from AuricularProtocolBank
    auricular_treatment_note = auricular_protocol.protocol_notes or ""

    # Fetch disable_treatment_notes from AuricularProtocolBank
    disable_treatment_note = auricular_protocol.disable_treatment_notes

    # If it is disabled, only auricular_treatment_note will be displayed. Else both treatment_note & auricular_treatment_note will be displayed
    if disable_treatment_note:
        final_note = auricular_treatment_note
    else:
        final_note = f"{treatment_note}, {auricular_treatment_note}"

    # Return the image data as a base64-encoded JSON response
    content_data = [
        {"type": "image", "title": "Auricular Report", "value": image_base64},
        {"type": "text", "title": "Auricular Notes", "value": final_note},
    ]
    return {
        "status": "success",
        "data": [
            {
                "section_name": "Treatment Report",
                "section_metadata": {"protocol": auricular_protocol.protocol_number},
                "content": content_data,
            }
        ],
        "message": "Auricular report generated successfully with image.",
        "status_code": 200,
    }


def generate_mudra_report(request_data):
    """
    Generate a Mudra report based on the provided request data.

    Args:
        request_data (dict): The data from the request, must include 'pattern_id' and 'patient_id'.

    Returns:
        dict: A response dictionary containing status_code, message, and data/errors.
    """
    # Retrieve pattern_id and patient_id directly from request data
    pattern_id = request_data.get("pattern_id")
    patient_id = request_data.get("patient_id")
    
    if not pattern_id or not patient_id:
        return {
            "status": "error",
            "errors": {"detail": "pattern_id and patient_id are required."},
            "status_code": 400,
        }

    try:
        # Fetch the MudraReportSystem object using pattern_id
        mudra_report_system = MudraReportSystem.objects.get(report_id=pattern_id)
    except MudraReportSystem.DoesNotExist:
        return {
            "status": "error",
            "errors": {
                "pattern_id": f"MudraReportSystem with report_id {pattern_id} not found."
            },
            "status_code": 404,
        }

    # Retrieve protocols
    protocols = mudra_report_system.protocols
    if not protocols:
        return {
            "status": "error",
            "errors": {
                "protocols": "No protocols associated with this MudraReportSystem."
            },
            "status_code": 404,
        }

    # Split comma-separated protocol IDs
    protocol_ids = [p.strip() for p in protocols.split(",")]

    # Determine how many previous reports have a protocol assigned for this patient and pattern
    previous_count = DiagnosisReportHistory.objects.filter(
        patient_id=patient_id,
        report_pattern_type=pattern_id,
        mudra_treatment__isnull=False
    ).count()

    # Prepare list for content data and metadata
    content_data = []
    selected_protocol_numbers = []

    # Fetch common treatment note from the Mudra object
    mudra = Mudra.objects.first()
    if not mudra:
        raise Http404("Mudra object does not exist.")
    treatment_note = mudra.treatment_note

    # Loop to pick 3 protocols using round-robin logic
    for i in range(3):
        index = (previous_count + i) % len(protocol_ids)
        selected_protocol = protocol_ids[index]
        selected_protocol_numbers.append(selected_protocol)

        # Fetch the MudraProtocolBank object for the selected protocol
        try:
            mudra_protocol = MudraProtocolBank.objects.get(protocol_number=selected_protocol)
        except MudraProtocolBank.DoesNotExist:
            return {
                "status": "error",
                "errors": {
                    "protocol_id": f"MudraProtocolBank with id {selected_protocol} not found."
                },
                "status_code": 404,
            }

        # Retrieve protocol value
        protocol_value = mudra_protocol.protocol
        if not protocol_value:
            return {
                "status": "error",
                "errors": {
                    "protocol_value": "No protocol value found in MudraProtocolBank."
                },
                "status_code": 404,
            }

        # Retrieve base image URL from mudra_protocol
        if mudra_protocol.base_image_1:
            image_url = mudra_protocol.base_image_1.url  # Assuming no need for absolute URI
        else:
            return {
                "status": "error",
                "errors": {"detail": "Base image not found for Mudra."},
                "status_code": 404,
            }

        # Fetch protocol notes from MudraProtocolBank
        mudra_treatment_note = mudra_protocol.protocol_notes or ""

        # Fetch disable_treatment_notes flag from MudraProtocolBank
        disable_treatment_note = mudra_protocol.disable_treatment_notes

        # If treatment notes are disabled, only mudra_treatment_note will be displayed.
        # Otherwise, combine the common treatment_note with mudra_treatment_note.
        if disable_treatment_note:
            final_note = mudra_treatment_note
        else:
            final_note = f"{treatment_note}, {mudra_treatment_note}"

        # Append an image entry with a title indicating its order and a corresponding text note
        content_data.append({
            "type": "image",
            "title": f"Mudra Report {i + 1}",
            "value": image_url
        })
        content_data.append({
            "type": "text",
            "title": "Mudra Notes",
            "value": final_note
        })

    # Combine and return the responses
    return {
        "status": "success",
        "data": [
            {
                "section_name": "Treatment Report",
                "section_metadata": {"protocols": selected_protocol_numbers},
                "content": content_data,
            }
        ],
        "message": "Mudra report generated successfully.",
        "status_code": 200,
    }

def generate_yoga_report(request_data):
    """
    Generate a Yoga report based on the provided request data.

    Args:
        request_data (dict): The data from the request, must include 'pattern_id' and 'patient_id'.

    Returns:
        dict: A response dictionary containing status_code, message, and data/errors.
    """
    # Retrieve pattern_id and patient_id directly from request data
    pattern_id = request_data.get("pattern_id")
    patient_id = request_data.get("patient_id")
    
    if not pattern_id or not patient_id:
        return {
            "status": "error",
            "errors": {"detail": "pattern_id and patient_id are required."},
            "status_code": 400,
        }

    try:
        # Fetch the YogaReportSystem object using pattern_id
        yoga_report_system = YogaReportSystem.objects.get(report_id=pattern_id)
    except YogaReportSystem.DoesNotExist:
        return {
            "status": "error",
            "errors": {
                "pattern_id": f"YogaReportSystem with report_id {pattern_id} not found."
            },
            "status_code": 404,
        }

    # Retrieve protocols
    protocols = yoga_report_system.protocols
    if not protocols:
        return {
            "status": "error",
            "errors": {
                "protocols": "No protocols associated with this YogaReportSystem."
            },
            "status_code": 404,
        }

    # Split comma-separated protocol IDs
    protocol_ids = [p.strip() for p in protocols.split(",")]

    # Determine how many previous reports have a protocol assigned for this patient and pattern
    previous_count = DiagnosisReportHistory.objects.filter(
        patient_id=patient_id,
        report_pattern_type=pattern_id,
        yoga_treatment__isnull=False
    ).count()

    # Prepare list for content data and metadata
    content_data = []
    selected_protocol_numbers = []

    # Fetch common treatment note from the Yoga object
    yoga = Yoga.objects.first()
    if not yoga:
        raise Http404("Yoga object does not exist.")
    treatment_note = yoga.treatment_note

    # Loop to pick 3 protocols using round-robin logic
    for i in range(3):
        index = (previous_count + i) % len(protocol_ids)
        selected_protocol = protocol_ids[index]
        selected_protocol_numbers.append(selected_protocol)

        # Fetch the YogaProtocolBank object for the selected protocol
        try:
            yoga_protocol = YogaProtocolBank.objects.get(protocol_number=selected_protocol)
        except YogaProtocolBank.DoesNotExist:
            return {
                "status": "error",
                "errors": {
                    "protocol_id": f"YogaProtocolBank with id {selected_protocol} not found."
                },
                "status_code": 404,
            }

        # Retrieve protocol value
        protocol_value = yoga_protocol.protocol
        if not protocol_value:
            return {
                "status": "error",
                "errors": {
                    "protocol_value": "No protocol value found in YogaProtocolBank."
                },
                "status_code": 404,
            }

        # Retrieve base image URL from yoga_protocol
        if yoga_protocol.base_image_1:
            image_url = yoga_protocol.base_image_1.url  # Assuming no need for absolute URI
        else:
            return {
                "status": "error",
                "errors": {"detail": "Base image not found for Yoga."},
                "status_code": 404,
            }

        # Fetch protocol notes from YogaProtocolBank
        yoga_treatment_note = yoga_protocol.protocol_notes or ""

        # Fetch disable_treatment_notes flag from YogaProtocolBank
        disable_treatment_note = yoga_protocol.disable_treatment_notes

        # If treatment notes are disabled, only yoga_treatment_note will be displayed.
        # Otherwise, combine the common treatment_note with yoga_treatment_note.
        if disable_treatment_note:
            final_note = yoga_treatment_note
        else:
            final_note = f"{treatment_note}, {yoga_treatment_note}"

        # Append an image entry with a title indicating its order and a corresponding text note
        content_data.append({
            "type": "image",
            "title": f"Yoga Report {i + 1}",
            "value": image_url
        })
        content_data.append({
            "type": "text",
            "title": "Yoga Notes",
            "value": final_note
        })

    # Combine and return the responses
    return {
        "status": "success",
        "data": [
            {
                "section_name": "Treatment Report",
                "section_metadata": {"protocols": selected_protocol_numbers},
                "content": content_data,
            }
        ],
        "message": "Yoga report generated successfully.",
        "status_code": 200,
    }


def generate_colour_report(request_data):
    """
    Generate a Colour report based on the provided request data.

    Args:
        request_data (dict): The data from the request, must include 'pattern_id'.

    Returns:
        dict: A response dictionary containing status_code, message, and data/errors.
    """
    # Retrieve pattern_id directly from request data
    pattern_id = request_data.get("pattern_id")
    patient_id = request_data.get("patient_id")
    
    if not pattern_id or not patient_id:
        return {
            "status": "error",
            "errors": {"detail": "pattern_id and patient_id are required."},
            "status_code": 400,
        }

    try:
        # Fetch the ColourReportSystem object using pattern_id
        colour_report_system = ColourReportSystem.objects.get(report_id=pattern_id)
    except ColourReportSystem.DoesNotExist:
        return {
            "status": "error",
            "errors": {
                "detail": f"ColourReportSystem with report_id {pattern_id} not found."
            },
            "status_code": 404,
        }

    # Retrieve protocols
    protocols = colour_report_system.protocols
    # print(399, protocols)
    if not protocols:
        return {
            "status": "error",
            "errors": {
                "detail": "No protocols associated with this ColourReportSystem."
            },
            "status_code": 404,
        }

    # Fetch the ColourProtocolBank object using the first protocol (assuming comma-separated values)
    protocol_ids = [p.strip() for p in protocols.split(",")]
    
    # Determine how many previous reports have a protocol assigned for this patient and pattern
    previous_count = DiagnosisReportHistory.objects.filter(
        patient_id=patient_id,
        report_pattern_type=pattern_id,
        auricular_treatment__isnull=False
    ).count()
    
    # Use round-robin logic to select the next protocol
    index = previous_count % len(protocol_ids)
    selected_protocol = protocol_ids[index]

    try:
        colour_protocol = ColourProtocolBank.objects.get(protocol_number=selected_protocol)
    except ColourProtocolBank.DoesNotExist:
        return {
            "status": "error",
            "errors": {
                "detail": f"ColourProtocolBank with id {selected_protocol} not found."
            },
            "status_code": 404,
        }

    # Retrieve the protocol value
    protocol_value = colour_protocol.protocol
    # print(420, protocol_value)
    if not protocol_value:
        return {
            "status": "error",
            "errors": {"detail": "No protocol value found in ColourProtocolBank."},
            "status_code": 404,
        }

    colour = Colour.objects.first()
    if not colour:
        raise Http404("Colour object does not exist.")

    # Check if the image exists and fetch its URL
    if colour.base_image_1:
        image_url = (
            colour.base_image_1.url
        )  # Assuming no need for absolute URI in function
    else:
        return {
            "status": "error",
            "errors": {"detail": "Base image not found for Colour."},
            "status_code": 404,
        }

    image_url = os.path.join(settings.BASE_DIR, "image_processing", "colour")
    # Call the helper function
    image_path = r"D:\Projects\Colour\Left-Ring1.jpg"
    annotation_file = r"D:\Projects\Colour\colour_coordinates1.txt"

    # protocol_values = [
    #     ColourProtocolBank.objects.get(id=protocol_id).protocol
    #     for protocol_id in protocol_ids
    # ]
    
    if colour.base_image_1:
        image_url = (
            colour.base_image_1.url
        )  # Assuming no need for absolute URI in function
    else:
        return {
            "status": "error",
            "errors": {"detail": "Base image not found for Auricular."},
            "status_code": 404,
        }
    # print(458, image_path)
    # print(459, image_url)

    annotation_file = os.path.join(
        settings.BASE_DIR, "image_processing/colour_coordinates.txt"
    )

    # image_base = highlight_points(image_url, annotation_file, protocol_values)
    protocol_value = [item.strip() for item in protocol_value.split(',')]
    image_base = color_therapy(image_url, protocol_value)

    if isinstance(image_base, dict):
        return image_base  # Return early in case of error

    # Fetch Treatment note from colour
    treatment_note = colour.treatment_note

    # Fetch protocol_notes from ColourProtocolBank
    colour_treatment_note = colour_protocol.protocol_notes or ""
    

    # Fetch disable_treatment_notes from ColourProtocolBank
    disable_treatment_note = colour_protocol.disable_treatment_notes

    # If it is disabled, only colour_treatment_note will be displayed. Else both treatment_note & colour_treatment_note will be displayed
    if disable_treatment_note:
        final_note = colour_treatment_note
    else:
        final_note = f"{treatment_note}, {colour_treatment_note}"

    # Return the image data as a base64-encoded JSON response
    content_data = [
        {"type": "image", "title": "Colour Report", "value": image_base},
        {"type": "text", "title": "Colour Notes", "value": final_note},
    ]
    return {
        "status": "success",
        "data": [
            {
                "section_name": "Treatment Report",
                "section_metadata": {"protocol": colour_protocol.protocol_number},
                "content": content_data,
            }
        ],
        "message": "Colour report generated successfully with image.",
        "status_code": 200,
    }
    
    
    
    
def generate_multi_seed_report(request_data):
    """
    Generate an Auricular report based on the provided request data.

    Args:
        request_data (dict): The data from the request, must include 'pattern_id'.

    Returns:
        dict: A response dictionary containing status_code, message, and data/errors.
    """
    # Retrieve pattern_id directly from request data
    pattern_id = request_data.get("pattern_id")
    patient_id = request_data.get("patient_id")
    
    if not pattern_id or not patient_id:
        return {
            "status": "error",
            "errors": {"detail": "pattern_id and patient_id are required."},
            "status_code": 400,
        }

    try:
        # Fetch the AuricularReportSystem object using pattern_id
        multi_seed_report_system = SeedtherapyReportSystem.objects.get(
            report_id=pattern_id
        )
    except SeedtherapyReportSystem.DoesNotExist:
        return {
            "status": "error",
            "errors": {
                "detail": f"SeedtherapyReportSystem with report_id {pattern_id} not found."
            },
            "status_code": 404,
        }

    # Retrieve protocols
    protocols = multi_seed_report_system.protocols
    if not protocols:
        return {
            "status": "error",
            "errors": {
                "detail": "No protocols associated with this SeedtherapyReportSystem."
            },
            "status_code": 404,
        }

    # Fetch the AuricularProtocolBank object using the first protocol (assuming comma-separated values)
    protocol_ids = [p.strip() for p in protocols.split(",")]
    
    # Determine how many previous reports have a protocol assigned for this patient and pattern
    previous_count = DiagnosisReportHistory.objects.filter(
        patient_id=patient_id,
        report_pattern_type=pattern_id,
        seed_treatment__isnull=False
    ).count()
    
    # Use round-robin logic to select the next protocol
    index = previous_count % len(protocol_ids)
    selected_protocol = protocol_ids[index]
    
    # print(70, protocol_ids)
    try:
        multi_seed_protocol = SeedtherapyProtocolBank.objects.get(protocol_number=selected_protocol)
        
    except SeedtherapyProtocolBank.DoesNotExist:
        return {
            "status": "error",
            "errors": {
                "detail": f"SeedtherapyProtocolBank with id {selected_protocol} not found."
            },
            "status_code": 404,
        }

    # Retrieve the protocol value
    protocol_value = multi_seed_protocol.protocol
    # print(85, protocol_value)
    if not protocol_value:
        return {
            "status": "error",
            "errors": {"detail": "No protocol value found in SeedtherapyProtocolBank."},
            "status_code": 404,
        }

    multi_seed = Seedtherapy.objects.first()
    if not multi_seed:
        raise Http404("Seed object does not exist.")

    # Check if the image exists and fetch its URL
    if multi_seed.base_image_1:
        image_url = (
            multi_seed.base_image_1.url
        )  # Assuming no need for absolute URI in function
    else:
        return {
            "status": "error",
            "errors": {"detail": "Base image not found for Seedtherapy."},
            "status_code": 404,
        }

    annotation_file = os.path.join(
        settings.BASE_DIR, "image_processing/multi_seed_coordinates.txt"
    )

    # Call the helper function
    image_base64, highlighted_points = multi_seed_image_generation(
        image_url, annotation_file, protocol_value
    )

    if isinstance(image_base64, dict):
        return image_base64  # Return early in case of error

    # Fetch Treatment note from auricular
    treatment_note = multi_seed.treatment_note

    # Fetch protocol_notes from AuricularProtocolBank
    seed_treatment_note = multi_seed_protocol.protocol_notes  or ""

    # Fetch disable_treatment_notes from AuricularProtocolBank
    disable_treatment_note = multi_seed_protocol.disable_treatment_notes

    # If it is disabled, only auricular_treatment_note will be displayed. Else both treatment_note & auricular_treatment_note will be displayed
    if disable_treatment_note:
        final_note = seed_treatment_note
    else:
        final_note = f"{treatment_note}, {seed_treatment_note}"

    # Return the image data as a base64-encoded JSON response
    content_data = [
        {"type": "image", "title": "Seed Therapy Report", "value": image_base64},
        {"type": "text", "title": "Seed Therapy Notes", "value": final_note},
    ]
    return {
        "status": "success",
        "data": [
            {
                "section_name": "Treatment Report",
                "section_metadata": {"protocol": multi_seed_protocol.protocol_number},
                "content": content_data,
            }
        ],
        "message": "Seed Therapy report generated successfully with image.",
        "status_code": 200,
    }




def generate_acupressure_report(request_data):
    """
    Generate a Yoga report based on the provided request data.

    Args:
        request_data (dict): The data from the request, must include 'pattern_id'.

    Returns:
        dict: A response dictionary containing status_code, message, and data/errors.
    """
    # Retrieve pattern_id directly from request data
    pattern_id = request_data.get("pattern_id")
    patient_id = request_data.get("patient_id")
    
    if not pattern_id or not patient_id:
        return {
            "status": "error",
            "errors": {"detail": "pattern_id and patient_id are required."},
            "status_code": 400,
        }

    try:
        # Fetch the YogaReportSystem object using pattern_id
        acupressure_report_system = AcupressureReportSystem.objects.get(report_id=pattern_id)
    except AcupressureReportSystem.DoesNotExist:
        return {
            "status": "error",
            "errors": {
                "pattern_id": f"AcupressureReportSystem with report_id {pattern_id} not found."
            },
            "status_code": 404,
        }

    # Retrieve protocols
    protocols = acupressure_report_system.protocols
    if not protocols:
        return {
            "status": "error",
            "errors": {
                "protocols": "No protocols associated with this AcupressureReportSystem."
            },
            "status_code": 404,
        }

    # Fetch the YogaProtocolBank object using the first protocol (assuming comma-separated values)
    protocol_ids = [p.strip() for p in protocols.split(",")]
    
    # Determine how many previous reports have a protocol assigned for this patient and pattern
    previous_count = DiagnosisReportHistory.objects.filter(
        patient_id=patient_id,
        report_pattern_type=pattern_id,
        acupressure_treatment__isnull=False
    ).count()
    
    # Use round-robin logic to select the next protocol
    index = previous_count % len(protocol_ids)
    selected_protocol = protocol_ids[index]

    try:
        acupressure_protocol = AcupressureProtocolBank.objects.get(protocol_number=selected_protocol)
    except AcupressureProtocolBank.DoesNotExist:
        return {
            "status": "error",
            "errors": {
                "protocol_id": f"AcupressureProtocolBank with id {selected_protocol} not found."
            },
            "status_code": 404,
        }

    # Retrieve the protocol value
    protocol_value = acupressure_protocol.protocol

    if not protocol_value:
        return {
            "status": "error",
            "errors": {
                "protocol_value": "No protocol value found in AcupressureProtocolBank."
            },
            "status_code": 404,
        }

    if acupressure_protocol.base_image_1:
        image_url = (
            acupressure_protocol.base_image_1.url
        )  # Assuming no need for absolute URI in function

    else:
        return {
            "status": "error",
            "errors": {"detail": "Base image not found for Acupressure."},
            "status_code": 404,
        }

    # Fetch treatment note from yoga
    acupressure = Acupressure.objects.first()
    if not acupressure:
        raise Http404("Acupressure object does not exist.")

    treatment_note = acupressure.treatment_note

    # Fetch protocol_notes from YogaProtocolBank
    acupressure_treatment_note = acupressure_protocol.protocol_notes or ""

    # Fetch disable_treatment_notes from YogaProtocolBank
    disable_treatment_note = acupressure_protocol.disable_treatment_notes

    # If it is disabled, only yoga_treatment_note will be displayed. Else both treatment_note & yoga_treatment_note will be displayed
    if disable_treatment_note:
        final_note = acupressure_treatment_note
    else:
        final_note = f"{treatment_note}, {acupressure_treatment_note}"

    # Combine and return the responses
    content_data = [
        {"type": "image", "title": "Acupressure Report", "value": image_url},
        {"type": "text", "title": "Acupressure Notes", "value": final_note},
    ]

    return {
        "status": "success",
        "data": [
            {
                "section_name": "Treatment Report",
                "section_metadata": {"protocol": acupressure_protocol.protocol_number},
                "content": content_data,
            }
        ],
        "message": "Acupressure report generated successfully.",
        "status_code": 200,
    }
    
    
def generate_single_seed_report(organ_name, yin_yang):
    
    #print(913, organ_name)
    """
    Generate a Single Seed report using direct parameters.
    
    Args:
        organ_name (str): The organ name (e.g., "GB").
        yin_yang (str): The yin/yang value (e.g., "yang").
        
    Returns:
        dict: A response dictionary containing:
            - status (str): "success" or "error".
            - data (list): Report data when successful.
            - errors (dict): Error details if any.
            - message (str): A human-readable message.
            - status_code (int): HTTP status code.
    """
    try:
        # Validate required parameters.
        if not organ_name or not yin_yang:
            return {
                "status": "error",
                "errors": {"detail": "organ_name and yin_yang are required."},
                "status_code": 400,
            }
        
        # Retrieve all matching SingleSeedProtocolBank records.
        protocols = list(
            SingleSeedProtocolBank.objects.filter(
                organ=organ_name, yin_yang=yin_yang
            )
        )
        
        if not protocols:
            return {
                "status": "error",
                "errors": {"detail": f"No SingleSeedProtocolBank found with organ '{organ_name}' and yin_yang '{yin_yang}'."},
                "status_code": 404,
            }
        
        # Select a random protocol from the list.
        single_seed_protocol = random.choice(protocols)
        
        protocol_value = single_seed_protocol.protocol
        if not protocol_value:
            return {
                "status": "error",
                "errors": {"protocol_value": "No protocol value found in SingleSeedProtocolBank."},
                "status_code": 404,
            }
            
            
        
        if single_seed_protocol.base_image_1:
            image_url = single_seed_protocol.base_image_1.url
        else:
            return {
                "status": "error",
                "errors": {"detail": "Base image not found for Single Seed."},
                "status_code": 404,
            }
        
        # Fetch the treatment note from the SingleSeed model (without filtering by patient_id)
        single_seed = SingleSeed.objects.first()
        if not single_seed:
            return {
                "status": "error",
                "errors": {"detail": "SingleSeed object not found."},
                "status_code": 404,
            }
        treatment_note = single_seed.treatment_note
        
        protocol_notes = single_seed_protocol.protocol_notes or ""
        disable_treatment_note = single_seed_protocol.disable_treatment_notes
        
        if disable_treatment_note:
            final_note = protocol_notes
        else:
            final_note = f"{treatment_note}, {protocol_notes}" if protocol_notes else treatment_note
        
        content_data = [
            {"type": "image", "title": "Single Seed Report", "value": image_url},
            {"type": "text", "title": "Single Seed Notes", "value": final_note},
        ]
        
        return {
            "status": "success",
            "data": [
                {
                    "section_name": "Treatment Report",
                    "section_metadata": {"protocol": single_seed_protocol.organ},
                    "content": content_data,
                }
            ],
            "message": "Single Seed report generated successfully.",
            "status_code": 200,
        }
    except Exception as e:
        return {
            "status": "error",
            "errors": {"detail": str(e)},
            "status_code": 500,
        }



def generate_pranayama_report(request_data):
    """
    Generate a Pranayama report based on the provided request data.

    Args:
        request_data (dict): The data from the request, must include 'pattern_id' and 'patient_id'.

    Returns:
        dict: A response dictionary containing status_code, message, and data/errors.
    """
    # Retrieve pattern_id and patient_id directly from request data
    pattern_id = request_data.get("pattern_id")
    patient_id = request_data.get("patient_id")
    
    if not pattern_id or not patient_id:
        return {
            "status": "error",
            "errors": {"detail": "pattern_id and patient_id are required."},
            "status_code": 400,
        }

    try:
        # Fetch the PranayamaReportSystem object using pattern_id
        pranayama_report_system = PranayamaReportSystem.objects.get(report_id=pattern_id)
    except PranayamaReportSystem.DoesNotExist:
        return {
            "status": "error",
            "errors": {
                "pattern_id": f"PranayamaReportSystem with report_id {pattern_id} not found."
            },
            "status_code": 404,
        }

    # Retrieve protocols
    protocols = pranayama_report_system.protocols
    if not protocols:
        return {
            "status": "error",
            "errors": {
                "protocols": "No protocols associated with this PranayamaReportSystem."
            },
            "status_code": 404,
        }

    # Split comma-separated protocol IDs
    protocol_ids = [p.strip() for p in protocols.split(",")]

    # Determine how many previous reports have a protocol assigned for this patient and pattern
    previous_count = DiagnosisReportHistory.objects.filter(
        patient_id=patient_id,
        report_pattern_type=pattern_id,
        pranayama_treatment__isnull=False
    ).count()

    # Prepare list for content data and metadata
    content_data = []
    selected_protocol_numbers = []

    # Fetch common treatment note from the Pranayama object
    pranayama = Pranayama.objects.first()
    if not pranayama:
        raise Http404("Pranayama object does not exist.")
    treatment_note = pranayama.treatment_note

    # Loop to pick 3 protocols using round-robin logic
    for i in range(3):
        index = (previous_count + i) % len(protocol_ids)
        selected_protocol = protocol_ids[index]
        selected_protocol_numbers.append(selected_protocol)

        # Fetch the PranayamaProtocolBank object for the selected protocol
        try:
            pranayama_protocol = PranayamaProtocolBank.objects.get(protocol_number=selected_protocol)
        except PranayamaProtocolBank.DoesNotExist:
            return {
                "status": "error",
                "errors": {
                    "protocol_id": f"PranayamaProtocolBank with id {selected_protocol} not found."
                },
                "status_code": 404,
            }

        # Retrieve protocol value
        protocol_value = pranayama_protocol.protocol
        if not protocol_value:
            return {
                "status": "error",
                "errors": {
                    "protocol_value": "No protocol value found in PranayamaProtocolBank."
                },
                "status_code": 404,
            }

        # Retrieve base image URL from pranayama_protocol
        if pranayama_protocol.base_image_1:
            image_url = pranayama_protocol.base_image_1.url  # Assuming no need for absolute URI
        else:
            return {
                "status": "error",
                "errors": {"detail": "Base image not found for Pranayama."},
                "status_code": 404,
            }

        # Fetch protocol notes from PranayamaProtocolBank
        pranayama_treatment_note = pranayama_protocol.protocol_notes or ""

        # Fetch disable_treatment_notes flag from PranayamaProtocolBank
        disable_treatment_note = pranayama_protocol.disable_treatment_notes

        # If treatment notes are disabled, only pranayama_treatment_note will be displayed.
        # Otherwise, combine the common treatment_note with pranayama_treatment_note.
        if disable_treatment_note:
            final_note = pranayama_treatment_note
        else:
            final_note = f"{treatment_note}, {pranayama_treatment_note}"

        # Append an image entry with a title indicating its order and a corresponding text note
        content_data.append({
            "type": "image",
            "title": f"Pranayama Report {i + 1}",
            "value": image_url
        })
        content_data.append({
            "type": "text",
            "title": "Pranayama Notes",
            "value": final_note
        })

    # Combine and return the responses
    return {
        "status": "success",
        "data": [
            {
                "section_name": "Treatment Report",
                "section_metadata": {"protocols": selected_protocol_numbers},
                "content": content_data,
            }
        ],
        "message": "Pranayama report generated successfully.",
        "status_code": 200,
    }
