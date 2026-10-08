"""Register business processors here. Each processor owns its HTTP call and mapping."""
from context_tasks.case_details import process_case_details
from context_tasks.letter_generation import process_letter_generation
from context_tasks.installment_details import process_installment_details
from context_tasks.payment_history import process_payment_history
from context_tasks.router import context_dispatcher
from .graph import ExtraTask

CONTEXT_PROCESSORS = {
    "case_details": process_case_details,
    "letter_generation": process_letter_generation,
    "installment_details": process_installment_details,
    "payment_history": process_payment_history,
}

# Keep this result key for existing frontend and subsequent-task compatibility.
# The callable is the context dispatcher, not the HTTP helper.
EXTRA_TASKS: list[ExtraTask] = [
    ExtraTask("call_http_api", context_dispatcher(CONTEXT_PROCESSORS), require_identifiers=True),
]
