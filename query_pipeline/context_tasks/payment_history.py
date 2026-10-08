"""Post-processing for payment_history."""
from http_task.task import call_http_api
from workflow_outcomes import IdentifierRequired
from .common import response_payload


def process_payment_history(state):
    response = call_http_api(state)
    if isinstance(response, IdentifierRequired):
        return response
    result = response_payload(response)
    # Add payment_history-specific field mapping / formatting here.
    # If the API returns a typed UI reply, its type/details/report are preserved.
    return result
