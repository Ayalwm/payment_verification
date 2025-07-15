# main.py (Your FastAPI application entry point)

import re
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from models import TransactionDetails, VerificationResult, ImageVerificationRequest, BoATransactionDetails, CBETransactionDetails, VerifiedDataDetails 
from services.telebirr_service import TelebirrService
from services.boa_service import BOAService 
from services.cbe_service import CBEService 
from utils.image_processor import extract_text_id_from_image_gemini, extract_qr_code_data 
import base64
from typing import Optional 

from starlette.middleware.cors import CORSMiddleware
from dotenv import load_dotenv 
import os 

load_dotenv()

app = FastAPI(
    title="Transaction Verifier",
    description="API to verify Telebirr transactions by ID or from image, Bank of Abyssinia transactions, and CBE transactions from PDF links."
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    error_details = []
    for error in exc.errors():
        field = ".".join(map(str, error["loc"])) if error["loc"] else "unknown"
        error_details.append({
            "field": field,
            "message": error["msg"],
            "type": error["type"]
        })
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": error_details,
            "message": "Validation Error: The provided data does not match the expected format.",
            "debug_info": "Check 'detail' for specific field errors."
        },
    )

telebirr_service = TelebirrService()
boa_service = BOAService() 
cbe_service = CBEService() 

@app.post("/verify_telebirr_payment", response_model=VerificationResult) 
async def verify_telebirr_payment_by_id(transaction_details: TransactionDetails):
    result = await telebirr_service.verify_payment(transaction_details)
    return result

@app.post("/verify_telebirr_payment_from_image", response_model=VerificationResult) 
async def verify_telebirr_payment_from_image(image_file: UploadFile = File(...)):
    
    transaction_id = None
    image_base64 = None

    try:
        image_bytes = await image_file.read()
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')

    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail={
                "transaction_id": "N/A",
                "status": "Failed",
                "message": f"Could not read or process uploaded image file: {e}",
                "debug_info": str(e)
            }
        )

    extracted_details = await extract_text_id_from_image_gemini(image_base64) 
    
    transaction_id = extracted_details.get("transaction_id") if extracted_details and isinstance(extracted_details, dict) else None

    if not transaction_id:
        raise HTTPException(
            status_code=400, 
            detail={
                "transaction_id": "N/A",
                "status": "Failed",
                "message": "No Telebirr transaction ID found or could not extract from image using Gemini OCR.",
                "debug_info": "Ensure the image contains visible Telebirr transaction ID text."
            }
        )
    
    transaction_details = TransactionDetails(transaction_id=transaction_id)
    result = await telebirr_service.verify_payment(transaction_details)
    return result

@app.post("/verify_boa_payment", response_model=VerificationResult)
async def verify_boa_payment(boa_details: BoATransactionDetails):
    
    if len(boa_details.sender_account) < 5:
        raise HTTPException(
            status_code=400,
            detail={
                "transaction_id": boa_details.transaction_id,
                "status": "Failed",
                "message": "Sender account number must have at least 5 digits to extract the last five.",
                "debug_info": "Invalid sender_account length."
            }
        )
        
    sender_account_last_5_digits = boa_details.sender_account[-5:]

    extracted_data_dict = await boa_service.verify_payment(
        transaction_id=boa_details.transaction_id, 
        sender_account_last_5_digits=sender_account_last_5_digits
    )

    verified_details = VerifiedDataDetails(
        sender_name=extracted_data_dict.get('sender_name'),
        sender_bank_name=extracted_data_dict.get('sender_bank_name'), 
        receiver_name=extracted_data_dict.get('receiver_name'),
        receiver_bank_name=extracted_data_dict.get('receiver_bank_name'), 
        status=extracted_data_dict.get('status'),
        date=extracted_data_dict.get('date'),
        amount=extracted_data_dict.get('amount')
    )
    
    result = VerificationResult(
        transaction_id=extracted_data_dict.get('transaction_id', boa_details.transaction_id), 
        status=extracted_data_dict.get('status', 'Failed'),
        message="Bank of Abyssinia verification completed." if extracted_data_dict.get('status') not in ["Network/Load Timeout", "Playwright Error", "Failed", "Invalid Transaction ID"] else "Bank of Abyssinia verification failed.",
        verified_data=verified_details,
        debug_info=extracted_data_dict.get('debug_info')
    )
    
    return result

@app.post("/verify_boa_payment_from_image", response_model=VerificationResult)
async def verify_boa_payment_from_image(
    image_file: UploadFile = File(...),
    sender_account_input: Optional[str] = Form(None)
):
    
    image_base64 = None
    try:
        image_bytes = await image_file.read()
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail={
                "transaction_id": "N/A", "status": "Failed",
                "message": f"Could not read or process uploaded image file: {e}", "debug_info": str(e)
            }
        )

    transaction_id_for_service = None
    sender_account_for_service = sender_account_input

    extracted_details_from_gemini = await extract_text_id_from_image_gemini(image_base64)
    
    if extracted_details_from_gemini and isinstance(extracted_details_from_gemini, dict):
        transaction_id_for_service = extracted_details_from_gemini.get("transaction_id")
    else:
        pass

    if not transaction_id_for_service:
        raise HTTPException(
            status_code=400,
            detail={
                "transaction_id": "N/A", "status": "Failed",
                "message": "No BOA transaction ID found or could not extract from image using Gemini OCR.",
                "debug_info": "Ensure the image contains visible BOA transaction ID text."
            }
        )
    
    sender_account_last_5_digits = sender_account_for_service[-5:] if sender_account_for_service and len(sender_account_for_service) >= 5 else None

    if not sender_account_last_5_digits:
        return VerificationResult(
            transaction_id=transaction_id_for_service,
            status="Account_Number_Required",
            message=f"Bank of Abyssinia transaction ID ({transaction_id_for_service}) extracted. Please provide the sender's full account number to complete verification.",
            verified_data=VerifiedDataDetails(
                sender_account_number=None,
                receiver_account_number=None,
                transaction_id=transaction_id_for_service
            ),
            debug_info="Missing sender account for BOA verification."
        )

    extracted_data_dict = await boa_service.verify_payment(
        transaction_id=transaction_id_for_service, 
        sender_account_last_5_digits=sender_account_last_5_digits
    )

    final_verified_data = VerifiedDataDetails(
        sender_name=extracted_data_dict.get('sender_name'),
        sender_bank_name=extracted_data_dict.get('sender_bank_name'), 
        receiver_name=extracted_data_dict.get('receiver_name'),
        receiver_bank_name=extracted_data_dict.get('receiver_bank_name'), 
        status=extracted_data_dict.get('status'),
        date=extracted_data_dict.get('date'),
        amount=extracted_data_dict.get('amount'),
        sender_account_number=sender_account_for_service, 
        receiver_account_number=None
    )
    
    result = VerificationResult(
        transaction_id=extracted_data_dict.get('transaction_id', transaction_id_for_service), 
        status=extracted_data_dict.get('status', 'Failed'),
        message="Bank of Abyssinia image verification completed." if extracted_data_dict.get('status') not in ["Network/Load Timeout", "Playwright Error", "Failed", "Invalid Transaction ID"] else "Bank of Abyssinia image verification failed.",
        verified_data=final_verified_data,
        debug_info=extracted_data_dict.get('debug_info')
    )
    
    return result

@app.post("/verify_cbe_payment_from_image", response_model=VerificationResult)
async def verify_cbe_payment_from_image(
    image_file: UploadFile = File(...),
    account_number_input: Optional[str] = Form(None)
):
    
    image_base64 = None
    image_bytes = None 
    try:
        image_bytes = await image_file.read()
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail={
                "transaction_id": "N/A", "status": "Failed",
                "message": f"Could not read or process uploaded image file: {e}", "debug_info": str(e)
            }
        )

    transaction_id_for_service = None
    account_number_for_service = account_number_input
    
    qr_data = extract_qr_code_data(image_bytes)
    if qr_data:
        cbe_qr_match = re.search(r'id=([A-Z0-9]+)(\d{8})', qr_data, re.IGNORECASE)
        if cbe_qr_match:
            transaction_id_for_service = cbe_qr_match.group(1)
            account_number_for_service = account_number_for_service or cbe_qr_match.group(2) 
        else:
            pass
    
    if not transaction_id_for_service:
        extracted_details_from_gemini = await extract_text_id_from_image_gemini(image_base64)
        if extracted_details_from_gemini and isinstance(extracted_details_from_gemini, dict):
            transaction_id_for_service = extracted_details_from_gemini.get("transaction_id")
        else:
            pass

    if not transaction_id_for_service:
        raise HTTPException(
            status_code=400,
            detail={
                "transaction_id": "N/A", "status": "Failed",
                "message": "No CBE transaction ID found or could not extract from image using QR or Gemini OCR.",
                "debug_info": "Ensure the image contains visible CBE transaction ID or a scannable QR code."
            }
        )
    
    if not account_number_for_service:
        return VerificationResult(
            transaction_id=transaction_id_for_service,
            status="Account_Number_Required",
            message=f"Commercial Bank of Ethiopia transaction ID ({transaction_id_for_service}) extracted. Sender account number could not be provided. Please provide it manually.",
            verified_data=VerifiedDataDetails(
                sender_account_number=None,
                receiver_account_number=None,
                transaction_id=transaction_id_for_service
            ),
            debug_info="Missing sender account for CBE verification."
        )

    extracted_data_dict = await cbe_service.verify_payment(
        transaction_id=transaction_id_for_service,
        account_number=account_number_for_service
    )

    final_verified_data = VerifiedDataDetails(
        sender_name=extracted_data_dict.get('sender_name'),
        sender_bank_name=extracted_data_dict.get('sender_bank_name'),
        receiver_name=extracted_data_dict.get('receiver_name'),
        receiver_bank_name=extracted_data_dict.get('receiver_bank_name'),
        status=extracted_data_dict.get('status'),
        date=extracted_data_dict.get('date'),
        amount=extracted_data_dict.get('amount'),
        sender_account_number=account_number_for_service, 
        receiver_account_number=None
    )

    result = VerificationResult(
        transaction_id=extracted_data_dict.get('transaction_id', transaction_id_for_service),
        status=extracted_data_dict.get('status', 'Failed'),
        message="CBE image verification completed." if extracted_data_dict.get('status') not in ["PDF_FETCH_FAILED", "INVALID_INPUT_OR_PDF_FORMAT", "PDF_PARSE_FAILED"] else "CBE image verification failed.",
        verified_data=final_verified_data,
        debug_info=extracted_data_dict.get('debug_info')
    )

    return result


@app.post("/verify_cbe_payment", response_model=VerificationResult)
async def verify_cbe_payment(cbe_details: CBETransactionDetails):
    extracted_data_dict = await cbe_service.verify_payment(
        transaction_id=cbe_details.transaction_id,
        account_number=cbe_details.account_number
    )

    verified_details = VerifiedDataDetails(
        sender_name=extracted_data_dict.get('sender_name'),
        sender_bank_name=extracted_data_dict.get('sender_bank_name'),
        receiver_name=extracted_data_dict.get('receiver_name'),
        receiver_bank_name=extracted_data_dict.get('receiver_bank_name'),
        status=extracted_data_dict.get('status'),
        date=extracted_data_dict.get('date'),
        amount=extracted_data_dict.get('amount')
    )

    result = VerificationResult(
        transaction_id=extracted_data_dict.get('transaction_id', cbe_details.transaction_id),
        status=extracted_data_dict.get('status', 'Failed'),
        message="CBE PDF parsing completed." if extracted_data_dict.get('status') not in ["PDF_FETCH_FAILED", "INVALID_INPUT_OR_PDF_FORMAT", "PDF_PARSE_FAILED"] else "CBE PDF parsing failed.",
        verified_data=verified_details,
        debug_info=extracted_data_dict.get('debug_info')
    )

    return result


@app.get("/")
async def root():
    return {"message": "Transaction Verification API. Use /docs for API documentation."}

