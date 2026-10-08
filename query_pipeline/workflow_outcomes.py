"""Non-error task outcomes that request more information from the user."""
from dataclasses import dataclass


@dataclass(frozen=True)
class IdentifierRequired:
    message: str = "Enter a valid Case ID or Employee ID or SR Number"
