import json

import numpy as np
import pandas as pd

from pulse_analysis_algo.Testing_function import pulse_predict


def decision_making(signal_data):
    """
    Temporary function to extract pulse features.
    Replace with real pulse extraction logic.
    """
    # return {
    #     "primary": "humid",
    #     "secondary": "heat",
    #     "tertiary": "wind",
    #     "quaternary": "dry"
    # }

    # print(16, type(signal_data))

    if isinstance(signal_data, str):
        try:
            # Attempt to parse JSON string
            signal_data = json.loads(signal_data)
            if isinstance(signal_data, dict):
                signal_data = list(signal_data.values())  # Convert dict to list
        except json.JSONDecodeError:
            # If not JSON, try parsing as comma-separated numbers
            try:
                signal_data = [float(x) for x in signal_data.split(",")]
            except ValueError:
                raise ValueError(
                    "String input is not valid JSON or a comma-separated list of numbers."
                )

        # Convert to NumPy array if needed
    if isinstance(signal_data, (list, tuple, pd.Series)):
        pulse_array = np.array(signal_data)  # Convert to NumPy array
    elif isinstance(signal_data, np.ndarray):
        pulse_array = signal_data  # Already in the correct format
    elif isinstance(signal_data, pd.DataFrame):
        pulse_array = signal_data.values  # Convert DataFrame to NumPy array
    else:
        raise ValueError(
            f"Invalid input type: {type(signal_data)}. Expected a list, tuple, pandas Series, or numpy array."
        )

        # Call pulse_predict function
    pulse_result = pulse_predict(pulse_array)

    if isinstance(pulse_result, pd.DataFrame):
        first_row = pulse_result.iloc[0]
    else:
        return False

        # Extract primary, secondary, tertiary, quaternary
    decision_dict = {
        "primary": first_row["Primary"],
        "secondary": first_row["Secondary"],
        "tertiary": first_row["Tertiary"],
        "quaternary": first_row["Quaternary"],
        "quinary": first_row["Quinary"],
    }
    
    # Extract additional fields and correct Heart_yin by removing the '%' sign if present
    heart_yin_value = first_row.get("Heart_yin")
    if isinstance(heart_yin_value, str) and heart_yin_value.endswith("%"):
        try:
            heart_yin_value = float(heart_yin_value.rstrip("%"))
        except ValueError:
            pass  # In case conversion fails, leave the value as is

    # Extract all additional fields without the percentage signs
    extra_fields = {
        "heart_rate": first_row.get("Heart_rate"),
        "heart_yin": heart_yin_value,
        "carbohydrate": first_row.get("Carbohydrate"),
        "protein": first_row.get("Protein"),
        "fat": first_row.get("Fat"),
        "wind_yin": first_row.get("Wind_Yin"),
        "wind_yang": first_row.get("Wind_Yang"),
        "heat_yin": first_row.get("Heat_Yin"),
        "heat_yang": first_row.get("Heat_Yang"),
        "humid_yin": first_row.get("Humid_Yin"),
        "humid_yang": first_row.get("Humid_Yang"),
        "dry_yin": first_row.get("Dry_Yin"),
        "dry_yang": first_row.get("Dry_Yang"),
        "cold_yin": first_row.get("Cold_Yin"),
        "cold_yang": first_row.get("Cold_Yang"),
        "vata": first_row.get("VATA"),
        "pitta": first_row.get("PITTA"),
        "kapha": first_row.get("KAPHA"),
    }

    # Merge both dictionaries
    decision_dict.update(extra_fields)
    
    # print(100, decision_dict)

    # print(61, decision_dict)
    return decision_dict


def decision_making1(signal_data):
    decision = {
        "primary": "Wind_61.51%",
        "secondary": "Heat_42.57%",
        "tertiary": "Cold_7.5%",
        "quaternary": "Humid_5.57%",
        "quinary": "Dry_-5.11%",
        "heart_rate": 333.33,
        "heart_yin": 8.47,
        "carbohydrate": "Medium",
        "protein": "Medium",
        "fat": "Medium",
        "wind_yin": "Very Low",
        "wind_yang": "Normal",
        "heat_yin": "Low",
        "heat_yang": "Normal",
        "humid_yin": "Low",
        "humid_yang": "Normal",
        "dry_yin": "Normal",
        "dry_yang": "High",
        "cold_yin": "Very Low",
        "cold_yang": "Normal",
        "vata": "High",
        "pitta": "Normal",
        "kapha": "Low",
    }

    return decision
