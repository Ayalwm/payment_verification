# services/telebirr_service.py

import asyncio
import re
import base64
import io
from datetime import datetime
from playwright.async_api import Playwright, async_playwright, expect, Error, TimeoutError
from bs4 import BeautifulSoup 
from PIL import Image 
import sys 

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


from models import TransactionDetails, VerificationResult, VerifiedDataDetails # Ensure all models are imported


async def _extract_telebirr_receipt_data_internal(transaction_id: str) -> dict:
    """
    Internal function to extract specific transaction data from a Telebirr public receipt page
    using Playwright to fetch HTML and BeautifulSoup for parsing.
    Returns a dictionary of extracted details.
    """
    base_url = "https://transactioninfo.ethiotelecom.et/receipt/"
    receipt_url = f"{base_url}{transaction_id}"
    
    print(f"Attempting to extract data from: {receipt_url}")

    sender_name = None
    sender_bank_name = None 
    receiver_name = None 
    receiver_bank_name = None 
    transaction_status = None
    payment_date_iso = None
    final_amount_float = 0.0

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True) 
        context = await browser.new_context()
        page = await context.new_page()

        try:
            await page.goto(receipt_url, wait_until="domcontentloaded", timeout=60000) 

            not_found_selector = 'div:has-text("This request is not correct")'
            
            try:
                if await page.locator(not_found_selector).count() > 0:
                    print(f"DEBUG: Detected 'This request is not correct' message for ID: {transaction_id}")
                    return {
                        "sender_name": None,
                        "sender_bank_name": None, 
                        "receiver_name": None,
                        "receiver_bank_name": None, 
                        "status": "Invalid Transaction ID",
                        "date": None,
                        "amount": 0.0
                    }
            except TimeoutError:
                print(f"DEBUG: Timeout while checking for 'not found' selector. Proceeding to main content check.")
            except Exception as e:
                print(f"DEBUG: Error checking for 'not found' selector: {e}. Proceeding to main content check.")


            await page.wait_for_selector('td:has-text("የቴሌብር ክፍያ መረጃ/telebirr Transaction information")', timeout=30000)
            print(f"Page loaded for {transaction_id}. Fetching HTML content...")

            html_content = await page.content()
            soup = BeautifulSoup(html_content, 'html.parser')
            print("HTML content parsed with BeautifulSoup. Starting focused data extraction...")

            def get_value_by_label_bs4(soup_obj, label_text_regex):
                label_td = soup_obj.find('td', string=re.compile(label_text_regex, re.IGNORECASE | re.DOTALL))
                if label_td and label_td.find_next_sibling('td'):
                    return label_td.find_next_sibling('td').get_text(strip=True)
                return None

            raw_payer_name = get_value_by_label_bs4(soup, r"የከፋይ ስም/Payer Name")
            raw_payer_account_type = get_value_by_label_bs4(soup, r"የከፋይ አካውንት አይነት/Payer account type")
            raw_credited_party_name = get_value_by_label_bs4(soup, r"የገንዘብ ተቀባይ ስም/Credited Party name")
            transaction_status = get_value_by_label_bs4(soup, r"የክፍያው ሁኔታ/transaction status")
            payment_reason = get_value_by_label_bs4(soup, r"የክፍያ ምክንያት/Payment Reason")

            if raw_payer_account_type and "Organization" in raw_payer_account_type:
                sender_bank_name = raw_payer_name
                sender_name = None 
                try:
                    payer_bank_account_label_td = soup.find('td', string=re.compile(r"የከፋይ የባንክ አካውንት ቁጥር/Payer bank account number", re.IGNORECASE | re.DOTALL))
                    if payer_bank_account_label_td:
                        payer_bank_account_value_td = payer_bank_account_label_td.find_next_sibling('td')
                        if payer_bank_account_value_td:
                            payer_reference_label = payer_bank_account_value_td.find('label', id=re.compile(r'payer_reference_number|reference_number', re.IGNORECASE))
                            if payer_reference_label:
                                full_account_info = payer_reference_label.get_text(strip=True)
                                parts = full_account_info.split(' ', 1) 
                                if len(parts) > 1:
                                    sender_name = parts[1].strip() 
                                    print(f"DEBUG: Extracted sender bank account holder name from reference: {sender_name}")
                except Exception as e:
                    print(f"DEBUG: Error extracting sender bank account holder name from reference: {e}")
            else:
                sender_name = raw_payer_name
                sender_bank_name = None
                print(f"DEBUG: Sender is Individual. Sender Name: '{sender_name}'")

            receiver_bank_account_label_td = soup.find('td', string=re.compile(r"የባንክ አካውንት ቁጥር/Bank account number", re.IGNORECASE | re.DOTALL))

            if receiver_bank_account_label_td:
                receiver_bank_name = raw_credited_party_name
                receiver_name = None 

                try:
                    bank_account_value_td = receiver_bank_account_label_td.find_next_sibling('td')
                    if bank_account_value_td:
                        paid_reference_label = bank_account_value_td.find('label', id="paid_reference_number")
                        if paid_reference_label:
                            full_account_info = paid_reference_label.get_text(strip=True)
                            parts = full_account_info.split(' ', 1) 
                            if len(parts) > 1:
                                receiver_name = parts[1].strip() 
                                print(f"DEBUG: Extracted receiver bank account holder name: {receiver_name}")
                            else:
                                print(f"DEBUG: Could not parse receiver name from '{full_account_info}'. No space found or only one part.")
                        else:
                            print("DEBUG: Could not find <label id='paid_reference_number'> within bank account value td.")
                    else:
                        print("DEBUG: Could not find sibling <td> for bank account number label.")
                except Exception as e:
                    print(f"DEBUG: Error extracting receiver bank account holder name: {e}")
            else:
                receiver_name = raw_credited_party_name
                receiver_bank_name = None
                print(f"DEBUG: Receiver is not a bank account. Receiver Name: '{receiver_name}'")


            invoice_no_internal = None 
            settled_amount_str_internal = None 

            try:
                invoice_details_header_cell = soup.find('td', class_='receipttableTd3', string=re.compile(r"የክፍያ ዝርዝር/ Invoice details", re.IGNORECASE | re.DOTALL))
                
                invoice_data_table = None
                if invoice_details_header_cell:
                    invoice_data_table = invoice_details_header_cell.find_parent('table')

                if invoice_data_table:
                    data_row_with_transaction_id = None
                    for row in invoice_data_table.find_all('tr'):
                        if row.find('td', class_='receipttableTd2', string=re.compile(re.escape(transaction_id), re.IGNORECASE)):
                            data_row_with_transaction_id = row
                            break
                    
                    if data_row_with_transaction_id:
                        all_tds_in_data_row = data_row_with_transaction_id.find_all('td')
                        
                        if len(all_tds_in_data_row) >= 3:
                            invoice_no_internal = all_tds_in_data_row[0].get_text(strip=True)
                            raw_date_time_str = all_tds_in_data_row[1].get_text(strip=True)
                            settled_amount_str_internal = all_tds_in_data_row[2].get_text(strip=True)

                            try:
                                dt_obj = datetime.strptime(raw_date_time_str, '%d-%m-%Y %H:%M:%S')
                                payment_date_iso = dt_obj.isoformat() 
                            except ValueError:
                                print(f"DEBUG: Could not parse invoice payment date/time: {raw_date_time_str}")
                                payment_date_iso = raw_date_time_str 
                        else:
                            print("DEBUG: Data row with transaction ID found but not enough cells for all details.")
                    else:
                        print(f"DEBUG: Could not find data row with transaction ID '{transaction_id}' within the invoice details table.")
                else:
                    print("DEBUG: Could not find the specific invoice details table.")
            except Exception as e:
                print(f"DEBUG: Error extracting date, invoice_no, or settled_amount from invoice details: {e}")

            total_paid_amount_str_summary = None
            try:
                total_amount_in_word_label_td = soup.find('td', string=re.compile(r"የገንዘቡ ልክ በፊደል/Total Amount in word", re.IGNORECASE | re.DOTALL))
                summary_table = None
                if total_amount_in_word_label_td:
                    summary_table = total_amount_in_word_label_td.find_parent('table')

                if summary_table:
                    total_paid_amount_label_td = summary_table.find('td', class_='receipttableTd1', string=re.compile(r"ጠቅላላ የተከፈለ/Total Paid Amount", re.IGNORECASE | re.DOTALL))
                    if total_paid_amount_label_td:
                        amount_cell = total_paid_amount_label_td.find_next_sibling('td', class_=re.compile(r'receipttableTd\d+', re.IGNORECASE))
                        if amount_cell:
                            total_paid_amount_str_summary = amount_cell.get_text(strip=True)
                        else:
                            print("DEBUG: Could not find amount cell next to 'Total Paid Amount' label.")
                    else:
                        print("DEBUG: Could not find 'Total Paid Amount' label within its table.")
                else:
                    print("DEBUG: Could not find the summary table containing 'Total Amount in word'.")
            except Exception as e:
                print(f"DEBUG: Error extracting total paid amount from summary: {e}")

            amount_to_parse = None
            if total_paid_amount_str_summary:
                amount_to_parse = total_paid_amount_str_summary
            elif settled_amount_str_internal: 
                amount_to_parse = settled_amount_str_internal
                print(f"DEBUG: Using settled amount '{settled_amount_str_internal}' as fallback for total amount.")
            
            if amount_to_parse:
                try:
                    cleaned_amount_str = re.sub(r'[^\d.]', '', amount_to_parse)
                    final_amount_float = float(cleaned_amount_str)
                except ValueError:
                    print(f"DEBUG: Could not convert amount '{amount_to_parse}' to float.")
            else:
                print("DEBUG: No amount string found to parse.")

            return {
                "sender_name": sender_name,
                "sender_bank_name": sender_bank_name, 
                "receiver_name": receiver_name,
                "receiver_bank_name": receiver_bank_name, 
                "status": transaction_status,
                "date": payment_date_iso,
                "amount": final_amount_float
            }

        except TimeoutError as e:
            return {
                "sender_name": None,
                "sender_bank_name": None, 
                "receiver_name": None,
                "receiver_bank_name": None, 
                "status": "Network/Load Timeout", 
                "date": None,
                "amount": 0.0,
                "debug_info": str(e)
            }
        except Error as e:
            return {
                "sender_name": None,
                "sender_bank_name": None, 
                "receiver_name": None,
                "receiver_bank_name": None, 
                "status": "Playwright Error",
                "date": None,
                "amount": 0.0,
                "debug_info": str(e)
            }
        except Exception as e:
            return {
                "sender_name": None,
                "sender_bank_name": None, 
                "receiver_name": None,
                "receiver_bank_name": None, 
                "status": "Failed",
                "date": None,
                "amount": 0.0,
                "debug_info": str(e)
            }
        finally:
            await browser.close()
            
class PaymentService:
    async def verify_payment(self, transaction_details: TransactionDetails) -> VerificationResult:
        raise NotImplementedError

class TelebirrService(PaymentService):
    def __init__(self):
        self.receipt_base_url = "https://transactioninfo.ethiotelecom.et/receipt/"
     
    async def verify_payment(self, transaction_details: TransactionDetails) -> VerificationResult:

        result = VerificationResult(
            transaction_id=transaction_details.transaction_id,
            status="Pending", 
            message="Verification process started, awaiting scrape results.",
            verified_data=None,
            debug_info=None
        )

        try:
            extracted_details_dict = await _extract_telebirr_receipt_data_internal(transaction_details.transaction_id)
            
            verified_details = VerifiedDataDetails(
                sender_name=extracted_details_dict.get('sender_name'),
                sender_bank_name=extracted_details_dict.get('sender_bank_name'), 
                receiver_name=extracted_details_dict.get('receiver_name'),
                receiver_bank_name=extracted_details_dict.get('receiver_bank_name'), 
                status=extracted_details_dict.get('status'),
                date=extracted_details_dict.get('date'),
                amount=extracted_details_dict.get('amount')
            )
            
            result.verified_data = verified_details
            
            if verified_details.status == "Invalid Transaction ID":
                result.status = "Invalid Transaction ID"
                result.message = "The provided transaction ID is invalid or not found."
            elif verified_details.status == "Network/Load Timeout":
                result.status = "Network/Load Timeout"
                result.message = "The receipt page could not be loaded due to a network issue or timeout."
                result.debug_info = extracted_details_dict.get('debug_info')
            elif verified_details.status and "Completed" in verified_details.status:
                result.status = "Completed"
                result.message = f"Transaction verification successful. Status: {verified_details.status}."
            elif verified_details.status:
                result.status = verified_details.status
                result.message = f"Transaction data extracted, but status is: {verified_details.status}."
            else:
                result.status = "Partial Data Extracted"
                result.message = "Transaction page found, but status could not be determined."
            

        except Exception as e:
            result.status = "Failed"
            result.message = f"An unexpected error occurred during verification: {e}"
            result.debug_info = str(e)
            
        return result

