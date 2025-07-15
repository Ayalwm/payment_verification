# services/cbe_service.py

import httpx
import re
from datetime import datetime
from typing import Optional, Dict, Any
import fitz
import base64
import os

from models import VerificationResult, VerifiedDataDetails

class CBEService:
    def __init__(self):
        self.base_url = "https://apps.cbe.com.et:100/"
        self.gemini_api_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key="
        self.gemini_api_key = os.environ.get("GEMINI_API_KEY", "") 

    async def _extract_from_image_with_gemini(self, image_base64: str) -> Optional[Dict[str, Any]]:
        prompt = """
        Analyze this image, which is a page from a Commercial Bank of Ethiopia (CBE) transaction receipt PDF.
        Extract the following transaction details. Provide each detail on a new line, labeled clearly.
        
        Fields to extract:
        - Transaction ID (VAT Receipt No or Reference No.):
        - Payer Name:
        - Receiver Name (Credited Party name):
        - Transferred Amount:
        - Payment Date & Time:
        - Transaction Status:

        Example output format:
        Transaction ID: FT25188TN19J
        Payer Name: EHITEMUSIE NEBIYU MENGISTIE
        Receiver Name: ABDULSHEKUR SULTAN AHIMED
        Transferred Amount: 100.00 ETB
        Payment Date & Time: 06/07/2025, 10:08:00 AM
        Transaction Status: Completed
        """

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": prompt},
                        {
                            "inlineData": {
                                "mimeType": "image/png",
                                "data": image_base64
                            }
                        }
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.1
            }
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.gemini_api_url}{self.gemini_api_key}",
                    json=payload,
                    headers={'Content-Type': 'application/json'},
                    timeout=90.0
                )
                response.raise_for_status()
                result = response.json()

            extracted_details = {
                "transaction_id": None,
                "sender_name": None,
                "receiver_name": None,
                "amount": None,
                "date": None,
                "status": None
            }

            if result and result.get('candidates') and len(result['candidates']) > 0 and \
               result['candidates'][0].get('content') and result['candidates'][0]['content'].get('parts') and \
               len(result['candidates'][0]['content']['parts']) > 0:
                
                raw_gemini_text = result['candidates'][0]['content']['parts'][0]['text']
                
                id_match = re.search(r'Transaction ID.*?:?\s*([A-Z0-9]{10,})', raw_gemini_text, re.IGNORECASE)
                if id_match:
                    extracted_details["transaction_id"] = id_match.group(1).strip()
                
                sender_match = re.search(r'Payer Name.*?:?\s*(.+)', raw_gemini_text, re.IGNORECASE)
                if sender_match:
                    extracted_details["sender_name"] = sender_match.group(1).strip()
                
                receiver_match = re.search(r'Receiver Name.*?:?\s*(.+)', raw_gemini_text, re.IGNORECASE)
                if receiver_match:
                    extracted_details["receiver_name"] = receiver_match.group(1).strip()
                
                amount_match = re.search(r'Transferred Amount.*?:?\s*([\d\.,]+)\s*(?:ETB|Birr)?', raw_gemini_text, re.IGNORECASE)
                if amount_match:
                    try:
                        extracted_details["amount"] = float(amount_match.group(1).replace(',', ''))
                    except ValueError:
                        pass
                
                date_match = re.search(r'Payment Date & Time.*?:?\s*(.+)', raw_gemini_text, re.IGNORECASE)
                if date_match:
                    raw_date_str = date_match.group(1).strip()
                    try:
                        dt_obj = None
                        if re.match(r'\d{1,2}/\d{1,2}/\d{4},\s*\d{1,2}:\d{2}:\d{2}\s*(?:AM|PM)', raw_date_str):
                            dt_obj = datetime.strptime(raw_date_str, '%m/%d/%Y, %I:%M:%S %p')
                        elif re.match(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}', raw_date_str):
                            dt_obj = datetime.fromisoformat(raw_date_str)
                        elif re.match(r'\d{2}-\d{2}-\d{4}\s*\d{2}:\d{2}:\d{2}', raw_date_str):
                            dt_obj = datetime.strptime(raw_date_str, '%d-%m-%Y %H:%M:%S')
                        
                        if dt_obj:
                            extracted_details["date"] = dt_obj.isoformat()
                        else:
                            extracted_details["date"] = raw_date_str
                    except ValueError:
                        extracted_details["date"] = raw_date_str

                status_match = re.search(r'Transaction Status.*?:?\s*(Completed|Failed|Pending|Successful)', raw_gemini_text, re.IGNORECASE)
                if status_match:
                    extracted_details["status"] = status_match.group(1).strip()
                
                return extracted_details
            else:
                return None

        except httpx.HTTPStatusError as e:
            return None
        except Exception as e:
            return None


    async def verify_payment(self, transaction_id: str, account_number: str) -> dict:
        extracted_data = {
            "transaction_id": transaction_id,
            "sender_name": None,
            "sender_bank_name": "Commercial Bank of Ethiopia",
            "receiver_name": None,
            "receiver_bank_name": None,
            "status": "UNKNOWN",
            "date": None,
            "amount": 0.0,
            "debug_info": ""
        }

        try:
            if len(account_number) < 8:
                raise ValueError("Account number must have at least 8 digits to construct the PDF link.")
            
            last_8_digits_of_account = account_number[-8:]
            pdf_url = f"{self.base_url}?id={transaction_id}{last_8_digits_of_account}"
            
            async with httpx.AsyncClient(verify=False) as client:
                response = await client.get(
                    pdf_url, 
                    follow_redirects=True, 
                    timeout=120.0
                )
                response.raise_for_status()

                if 'application/pdf' not in response.headers.get('Content-Type', ''):
                    raise ValueError(f"Expected PDF, but received content type: {response.headers.get('Content-Type')}")

                pdf_bytes = response.content

            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            all_extracted_details = {}

            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                img_bytes = pix.pil_tobytes(format="PNG")
                image_base64 = base64.b64encode(img_bytes).decode('utf-8')
                
                page_data = await self._extract_from_image_with_gemini(image_base64)
                
                if page_data:
                    for key, value in page_data.items():
                        if value is not None and all_extracted_details.get(key) is None:
                            all_extracted_details[key] = value
                    
                    if 'date' in all_extracted_details and all_extracted_details['date']:
                        try:
                            dt_obj = None
                            if re.match(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}', all_extracted_details['date']):
                                dt_obj = datetime.fromisoformat(all_extracted_details['date'])
                            elif re.match(r'\d{1,2}/\d{1,2}/\d{4}, \d{1,2}:\d{2}:\d{2} (?:AM|PM)', all_extracted_details['date']):
                                dt_obj = datetime.strptime(all_extracted_details['date'], '%m/%d/%Y, %I:%M:%S %p')
                            elif re.match(r'\d{2}-\d{2}-\d{4} \d{2}:\d{2}:\d{2}', all_extracted_details['date']):
                                dt_obj = datetime.strptime(all_extracted_details['date'], '%d-%m-%Y %H:%M:%S')
                            
                            if dt_obj:
                                all_extracted_details['date'] = dt_obj.isoformat()
                            else:
                                all_extracted_details['date'] = all_extracted_details['date']
                        except ValueError:
                            all_extracted_details['date'] = all_extracted_details['date']
            
            doc.close()

            extracted_data["transaction_id"] = all_extracted_details.get("transaction_id", transaction_id)
            extracted_data["sender_name"] = all_extracted_details.get("sender_name")
            extracted_data["receiver_name"] = all_extracted_details.get("receiver_name")
            extracted_data["amount"] = all_extracted_details.get("amount", 0.0)
            extracted_data["date"] = all_extracted_details.get("date")
            extracted_data["status"] = all_extracted_details.get("status", "UNKNOWN")

            if extracted_data["status"] == "Completed":
                extracted_data["message"] = "CBE PDF parsed successfully using Gemini."
            elif all_extracted_details: 
                extracted_data["status"] = "Partial Data Extracted"
                extracted_data["message"] = "CBE PDF parsed, partial data extracted from Gemini."
            else:
                extracted_data["status"] = "PDF_PARSE_FAILED"
                current_debug_info = extracted_data.get("debug_info", "")
                extracted_data["debug_info"] = current_debug_info + " No data extracted from Gemini."

        except httpx.HTTPStatusError as e:
            extracted_data["status"] = "PDF_FETCH_FAILED"
            extracted_data["debug_info"] = f"HTTP error fetching PDF: {e.response.status_code} - {e.response.text}"
        except ValueError as e:
            extracted_data["status"] = "INVALID_INPUT_OR_PDF_FORMAT"
            extracted_data["debug_info"] = f"Error in input or PDF content type: {e}"
        except Exception as e:
            extracted_data["status"] = "PDF_PARSE_FAILED"
            current_debug_info = extracted_data.get("debug_info", "")
            extracted_data["debug_info"] = f"{current_debug_info} General error parsing PDF: {e}"
            
        return extracted_data
