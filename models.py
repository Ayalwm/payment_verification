# models/models.py

from pydantic import BaseModel
from typing import Optional

# Model for the detailed scraped data, now focused on the requested fields
class VerifiedDataDetails(BaseModel):
    sender_name: Optional[str] = None
    receiver_name: Optional[str] = None
    status: Optional[str] = None # This will be the transaction status directly from details
    date: Optional[str] = None # ISO formatted datetime string
    amount: float = 0.0

# Main response model
class VerificationResult(BaseModel):
    transaction_id: str
    status: str # "Completed", "Failed", "Pending", etc. (Overall verification status)
    message: str # A descriptive message about the verification outcome
    verified_data: Optional[VerifiedDataDetails] = None # Contains the focused scraped details
    debug_info: Optional[str] = None # For capturing detailed error messages or debug info

# Input model for the API endpoint
class TransactionDetails(BaseModel):
    transaction_id: str # Only the transaction ID is required as input

