# custom_responses.py\oohy_prduct
from rest_framework.response import Response


class StandardResponse(Response):
    def __init__(self, data=None, success=True, message=None, status_code=None, status='success',
                 template_name=None, headers=None, exception=False, content_type=None):
        standardized_data = {
            'status': status,
            'data': data,
            'message': message,
        }
        super().__init__(standardized_data, status=status_code, template_name=template_name,
                         headers=headers, exception=exception, content_type=content_type)


class ErrorResponse(Response):
    NON_FIELD_ERRORS = 'non_field_errors'
    FIELD_ERRORS = 'field_errors'

    def __init__(self, errors=None, status_code=None, success=False,
                 template_name=None, headers=None, exception=False, content_type=None):
        standardized_data = {
            'status': 'error',
            'errors': errors or {}
        }
        super().__init__(standardized_data, status=status_code, template_name=template_name,
                         headers=headers, exception=exception, content_type=content_type)
