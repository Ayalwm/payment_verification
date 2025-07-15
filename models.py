# models/models.py

from pydantic import BaseModel
from typing import Optional

# Model for the detailed scraped/parsed data
class VerifiedDataDetails(BaseModel):
    sender_name: Optional[str] = None
    sender_bank_name: Optional[str] = None 
    receiver_name: Optional[str] = None
    receiver_bank_name: Optional[str] = None 
    status: Optional[str] = None 
    date: Optional[str] = None 
    amount: float = 0.0

# Main response model
class VerificationResult(BaseModel):
    transaction_id: str
    status: str 
    message: str 
    verified_data: Optional[VerifiedDataDetails] = None 
    debug_info: Optional[str] = None 

# Input model for the API endpoint (transaction ID directly)
class TransactionDetails(BaseModel):
    transaction_id: str 

# Input model for image-based verification (OCR only)
class ImageVerificationRequest(BaseModel):
    image_base64: str # Base64 encoded string of the image (e.g., JPEG, PNG)

# NEW: Input model for Bank of Abyssinia (BoA) transaction verification
class BoATransactionDetails(BaseModel):
    transaction_id: str
    sender_account: str # Full sender account number
class CBETransactionDetails(BaseModel):
    transaction_id: str # The transaction ID part (e.g., FT25189TY6KT)
    account_number: str # The full account number (e.g., 1234567890123)

