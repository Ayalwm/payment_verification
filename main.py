# main.py

import asyncio
import sys
from fastapi import FastAPI, HTTPException
from models import TransactionDetails, VerificationResult
from services.telebirr_service import TelebirrService

# --- ADD THESE LINES FOR WINDOWS ---
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
# -----------------------------------

app = FastAPI(
    title="Telebirr Verification API",
    description="API for verifying Telebirr transactions by scraping the official receipt page.",
    version="1.0.0"
)

# Initialize your service
telebirr_service = TelebirrService()

@app.post("/verify_payment", response_model=VerificationResult, summary="Verify Telebirr Payment")
async def verify_payment_endpoint(transaction_details: TransactionDetails):
    """
    Verifies a Telebirr payment by its transaction ID.

    **Input:**
    - `transaction_id`: The unique ID of the Telebirr transaction.

    **Output:**
    Returns a `VerificationResult` object containing:
    - `transaction_id`: The ID of the transaction that was verified.
    - `status`: The overall status of the verification ("Completed", "Failed", "Pending", etc.).
    - `message`: A human-readable message about the verification outcome.
    - `verified_data`: An object containing all the scraped details (payer, receiver, amount, date, etc.), if successful.
    - `debug_info`: Additional technical details for debugging in case of an error.
    """
    print(f"Received verification request for transaction ID: {transaction_details.transaction_id}")
    try:
        verification_result = await telebirr_service.verify_payment(transaction_details)
        return verification_result
    except Exception as e:
        print(f"Error during verification for {transaction_details.transaction_id}: {e}")
        # Return a structured error response matching VerificationResult
        error_result = VerificationResult(
            transaction_id=transaction_details.transaction_id,
            status="Failed",
            message=f"An internal server error occurred during verification: {e}",
            verified_data=None,
            debug_info=str(e)
        )
        raise HTTPException(status_code=500, detail=error_result.dict())

# Optional: Root endpoint for basic health check
@app.get("/")
async def root():
    return {"message": "Telebirr Verification API is running!"}