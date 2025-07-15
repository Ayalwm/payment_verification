import base64
import re
import json
import httpx
from typing import Optional, Dict, Any
import os
import asyncio

import cv2
import numpy as np

async def extract_text_id_from_image_gemini(image_base64: str) -> Optional[Dict[str, Any]]:
    max_retries = 3
    initial_delay = 1

    for attempt in range(max_retries):
        try:
            prompt = """
            Analyze this bank transaction receipt image.
            Your task is to extract only the **Transaction ID**. Look for labels like "Invoice No.", "Reference No.", "Transaction Ref", "Receipt No.", "VAT Receipt No.". This is typically an alphanumeric string, often 10-15 characters long. If it's part of a URL, extract only the ID part.

            Output the Transaction ID clearly labeled.
            If the Transaction ID is not found, state "Transaction ID: Not Found".

            Example Output:
            Transaction ID: FT25188TN19J
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

            apiKey = os.environ.get("GEMINI_API_KEY", "") 
            if not apiKey:
                return None

            apiUrl = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={apiKey}"
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    apiUrl, 
                    json=payload,
                    headers={'Content-Type': 'application/json'},
                    timeout=90.0
                )
                response.raise_for_status()
                result = response.json()

            extracted_id = None

            if result and result.get('candidates') and len(result['candidates']) > 0 and \
               result['candidates'][0].get('content') and result['candidates'][0].get('content').get('parts') and \
               len(result['candidates'][0]['content']['parts']) > 0:
                
                raw_gemini_text = result['candidates'][0]['content']['parts'][0]['text']
                
                id_match = re.search(r'Transaction ID:\s*([A-Z0-9]+)', raw_gemini_text, re.IGNORECASE)
                if id_match:
                    extracted_id = id_match.group(1).strip()
                else:
                    pass

                final_extracted_details = {
                    "transaction_id": extracted_id.upper() if extracted_id else None,
                }
                
                return final_extracted_details
            else:
                return None

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 503 and attempt < max_retries - 1:
                delay = initial_delay * (2 ** attempt)
                await asyncio.sleep(delay)
                continue
            return None
        except Exception as e:
            return None
    
    return None

def extract_qr_code_data(image_bytes: bytes) -> Optional[str]:
    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img is None:
            return None

        qr_detector = cv2.QRCodeDetector()

        decoded_data, _, _ = qr_detector.detectAndDecode(img)

        if decoded_data:
            return decoded_data
        else:
            return None
    except Exception as e:
        return None

