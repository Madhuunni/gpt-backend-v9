"""Normalize the HTTP transport envelope before business-specific processing."""
from copy import deepcopy

def response_payload(response):
    data = deepcopy(response["data"])
    # Preserve existing typed UI replies; retain lists/scalars as JSON data.
    return data if isinstance(data, dict) else {"data": data}
