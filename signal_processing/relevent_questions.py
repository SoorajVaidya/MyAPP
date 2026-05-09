from report_service.views import GetQuestionsAPI
from rest_framework.test import APIRequestFactory

def get_relevant_questions(five_elements):
    """
    Determines relevant questions based on the input dictionary `five_elements` and fetches questions from the API.

    Args:
        five_elements (dict): A dictionary containing 'primary', 'secondary',
                             'tertiary', and 'quaternary' keys.

    Returns:
        dict: The API response containing the relevant questions.
    """
    # Define the conditions and their corresponding question numbers

    
    conditions_to_question_numbers = {
        ("humid", "heat", "wind", "dry"): [1, 3],
        ("cold", "heat", "humid", "dry"): [2, 4],
        ("cold", "humid", "dry", "wind", "heat"): [1, 4],
        ("humid", "cold", "dry", "wind", "heat"): [1, 2],
        ("cold", "humid", "dry", "heat", "wind"): [3, 2],
        ("cold", "dry", "humid", "wind", "heat"): [3, 4],

    }

    # Extract the values from five_elements in order
    input_conditions = (
        five_elements.get("primary", "").split("_")[0].lower(),
        five_elements.get("secondary", "").split("_")[0].lower(),
        five_elements.get("tertiary", "").split("_")[0].lower(),
        five_elements.get("quaternary", "").split("_")[0].lower(),
        five_elements.get("quinary", "").split("_")[0].lower(),
    )

    # Get the question numbers for the input conditions
    question_numbers = conditions_to_question_numbers.get(input_conditions, [])

    if not question_numbers:
        return {"error": "No matching questions found for the given conditions."}

    # Call the API to fetch the questions
    try:
        factory = APIRequestFactory()
        get_questions_request = factory.get('/get-questions/', data={"question_numbers": ",".join(map(str, question_numbers))})

        get_questions_response = GetQuestionsAPI.as_view()(get_questions_request)

        if get_questions_response.status_code == 200:
            return get_questions_response.data
        else:
            return {"error": f"API error: {get_questions_response.status_code}", "details": get_questions_response.data}

    except Exception as e:
        return {"error": "Failed to fetch questions from API.", "details": str(e)}