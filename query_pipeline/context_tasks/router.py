"""Select exactly one processor using the resolved business context."""
from workflow_errors import TaskExecutionError, task_boundary


def context_dispatcher(processors):
    handlers = {context: task_boundary(fn.__name__, fn) for context, fn in processors.items()}

    def process_context(state):
        handler = handlers.get(state.get("context"))
        if handler is None:
            raise TaskExecutionError(task="process_context", code="CONTEXT_PROCESSOR_NOT_FOUND",
                                     message="No processor is configured for this context.", status_code=500)
        return handler(state)

    return process_context
