from .models import DiagnosticResource, Patterns
from .serliaizers import DiagnosticResourceSerializer
from datetime import date, datetime


def generate_treatment_report(
    parameters,
    user_name=None,
    patient_name=None,
    patient_age=None,
    patient_number=None,
    language="English",
    user_number=None,
) -> dict:
    """
    Generate a treatment report by fetching data from the DiagnosticResource model based on predefined patterns.

    :param parameters: Dictionary containing query parameters.
    :param user_name: Optional username for the report metadata.
    :param patient_name: Optional patient name for the report metadata.
    :param patient_age: Optional patient age for the report metadata.
    :return: A dictionary with the generated report data.
    """
    # Set default values if the optional parameters are not provided
    if user_name is None:
        user_name = "Unknown User"
    if patient_name is None:
        patient_name = "Unknown Patient"
    if patient_age is None:
        patient_age = "Unknown Age"
    if patient_number is None:
        patient_number = "Unknown Number"
    if user_number is None:
        user_number = "Unknown Number"

    if not language:
        language = "English"

    primary = parameters.get("primary", "").split("_")[0].lower()
    secondary = parameters.get("secondary", "").split("_")[0].lower()
    tertiary = parameters.get("tertiary", "").split("_")[0].lower()
    quaternary = parameters.get("quaternary", "").split("_")[0].lower()
    quinary = parameters.get("quinary", "").split("_")[0].lower()

    # Initialize the report_type
    report_type = None

    try:
        # Instead of hardcoding multiple if conditions, query the Patterns model
        pattern_instance = Patterns.objects.filter(
            primary__iexact=primary,
            secondary__iexact=secondary,
            tertiary__iexact=tertiary,
        ).first()

        if pattern_instance:
            # Use the pattern_number from the matching Patterns record as the report_type
            report_type = pattern_instance.pattern_name
        else:
            return {
                "status": "failure",
                "message": "No matching pattern found for the provided primary, secondary, and tertiary values.",
                "data": {},
            }

        # report_type = "Wind-Dry-Humid"
        # print(54, report_type)

        pattern = DiagnosticResource.objects.filter(
            pattern_name__icontains=report_type, language__iexact=language
        ).first()

        if pattern:
            response_data = DiagnosticResourceSerializer(pattern).data
            pdf_image_fields = [
                field for field in response_data.keys() if "_pdf_" in field
            ]

            # Validate response: Check for binary data
            for key, value in response_data.items():
                if isinstance(value, bytes):
                    response_data[key] = None  # Replace with None or handle as needed

            # Transform the response to the required format
            content = []
            for field_name, field_value in response_data.items():
                # Keep only text fields and PDF images
                if field_name == "heart_rate":
                    # Include heart_rate even if it's empty. You can choose a default value if it's None.
                    hr_value = (
                        field_value if field_value is not None else "Not provided"
                    )
                    content.append(
                        {"type": "text", "title": field_name, "value": hr_value}
                    )
                    continue
                if field_name in pdf_image_fields:
                    field_type = "image"
                elif field_name not in pdf_image_fields and isinstance(
                    field_value, (str, int, dict, list)
                ):
                    field_type = "text"
                else:
                    continue  # Skip non-PDF images

                # Ensure PDF image URLs start with `https://`
                if (
                    field_type == "image"
                    and isinstance(field_value, str)
                    and not field_value.startswith("http")
                ):
                    field_value = f"https://{field_value}"

                content.append(
                    {"type": field_type, "title": field_name, "value": field_value}
                )

            current_datetime = datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )  # Format: YYYY-MM-DD HH:MM:SS

            transformed_response = [
                {
                    "section_name": "Diagnosis Report",
                    "section_metadata": {
                        "patient_name": patient_name,
                        "patient_age": patient_age,
                        "user_name": user_name,
                        "user_number": user_number,
                        "patient_number": patient_number,
                        "current_datetime": current_datetime,
                        "id": response_data.get("id"),
                        "pattern_name": response_data.get("pattern_name"),
                        "pattern_number": response_data.get("pattern_number"),
                    },
                    "content": content,
                }
            ]

            return {
                "status": "success",
                "message": f"Data available for {report_type}.",
                "data": transformed_response,
            }

        # If no matching pattern is found in the database
        return {
            "status": "failure",
            "message": f"No data available for {report_type}.",
            "data": {},
        }
    except Exception as e:
        # Handle unexpected errors
        return {
            "status": "failure",
            "message": f"An error occurred: {str(e)}",
            "data": {},
        }
