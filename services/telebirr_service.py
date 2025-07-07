# services/telebirr_service.py

import asyncio
import re
from datetime import datetime
from playwright.async_api import Playwright, async_playwright, expect, Error
from bs4 import BeautifulSoup # Import BeautifulSoup
import sys # For WindowsProactorEventLoopPolicy

# --- ADD THESE LINES FOR WINDOWS ---
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
# -----------------------------------

from models import TransactionDetails, VerificationResult, VerifiedDataDetails # Ensure all models are imported

# This is the core extraction logic, adapted from the standalone script
async def _extract_telebirr_receipt_data_internal(transaction_id: str) -> dict:
    """
    Internal function to extract specific transaction data from a Telebirr public receipt page
    using Playwright to fetch HTML and BeautifulSoup for parsing.
    Returns a dictionary of extracted details.
    """
    base_url = "https://transactioninfo.ethiotelecom.et/receipt/"
    receipt_url = f"{base_url}{transaction_id}"
    
    print(f"Attempting to extract data from: {receipt_url}")

    # Initialize all target fields to None or default values
    sender_name = None
    receiver_name = None
    transaction_status = None
    payment_date_iso = None
    final_amount_float = 0.0

    async with async_playwright() as p:
        # Launch browser in headful mode for debugging.
        # CHANGE TO headless=True FOR PRODUCTION DEPLOYMENT AFTER DEBUGGING.
        browser = await p.chromium.launch(headless=False) 
        context = await browser.new_context()
        page = await context.new_page()

        try:
            # Increased timeout for page.goto and page.wait_for_selector
            await page.goto(receipt_url, wait_until="domcontentloaded", timeout=60000) # Increased to 60 seconds
            await page.wait_for_selector('td:has-text("የቴሌብር ክፍያ መረጃ/telebirr Transaction information")', timeout=30000) # Increased to 30 seconds
            print(f"Page loaded for {transaction_id}. Fetching HTML content...")

            html_content = await page.content()
            soup = BeautifulSoup(html_content, 'html.parser')
            print("HTML content parsed with BeautifulSoup. Starting focused data extraction...")

            # Helper function to find a <td> by its text and get the text of its next sibling <td>
            def get_value_by_label_bs4(soup_obj, label_text_regex):
                label_td = soup_obj.find('td', string=re.compile(label_text_regex, re.IGNORECASE | re.DOTALL))
                if label_td and label_td.find_next_sibling('td'):
                    return label_td.find_next_sibling('td').get_text(strip=True)
                return None

            # 1. Payer Name (Sender Name)
            sender_name = get_value_by_label_bs4(soup, r"የከፋይ ስም/Payer Name")
            
            # 2. Credited Party Name (Receiver Name)
            receiver_name = get_value_by_label_bs4(soup, r"የገንዘብ ተቀባይ ስም/Credited Party name")
            
            # 3. Transaction Status
            transaction_status = get_value_by_label_bs4(soup, r"የክፍያው ሁኔታ/transaction status")

            # Internal variables for invoice details, not directly added to final 'details' dict
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
                                payment_date_iso = dt_obj.isoformat() # ISO formatted date
                            except ValueError:
                                print(f"DEBUG: Could not parse invoice payment date/time: {raw_date_time_str}")
                                payment_date_iso = raw_date_time_str # Fallback to raw string if parsing fails
                        else:
                            print("DEBUG: Data row with transaction ID found but not enough cells for all details.")
                    else:
                        print(f"DEBUG: Could not find data row with transaction ID '{transaction_id}' within the invoice details table.")
                else:
                    print("DEBUG: Could not find the specific invoice details table.")
            except Exception as e:
                print(f"DEBUG: Error extracting date, invoice_no, or settled_amount from invoice details: {e}")

            # 5. Amount (Total Paid Amount) - Attempt to get from summary, fallback to settled_amount
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

            # Determine the final amount to use
            amount_to_parse = None
            if total_paid_amount_str_summary:
                amount_to_parse = total_paid_amount_str_summary
            elif settled_amount_str_internal: # Fallback to settled amount if total paid amount not found
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

            # Return the extracted details
            return {
                "sender_name": sender_name,
                "receiver_name": receiver_name,
                "status": transaction_status,
                "date": payment_date_iso,
                "amount": final_amount_float
            }

        finally:
            await browser.close()
            print(f"Browser closed for {transaction_id}.")
            
class PaymentService:
    async def verify_payment(self, transaction_details: TransactionDetails) -> VerificationResult:
        raise NotImplementedError

class TelebirrService(PaymentService):
    def __init__(self):
        self.receipt_base_url = "https://transactioninfo.ethiotelecom.et/receipt/"
        print("TelebirrService initialized for scraping. Base Receipt URL:", self.receipt_base_url)
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        print("!!! WARNING: Scraping this receipt page is NOT an official API. !!!")
        print("!!! It is prone to breaking if Ethio Telecom changes its website. !!!")
        print("!!! Official Telebirr APIs are the recommended secure solution. !!!")
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")

    async def verify_payment(self, transaction_details: TransactionDetails) -> VerificationResult:
        print(f"Attempting to verify Telebirr transaction via Playwright scraping: {transaction_details.transaction_id}")

        result = VerificationResult(
            transaction_id=transaction_details.transaction_id,
            status="Pending", # Set initial status to Pending
            message="Verification process started, awaiting scrape results.",
            verified_data=None,
            debug_info=None
        )

        try:
            # Call the internal extraction function
            extracted_details_dict = await _extract_telebirr_receipt_data_internal(transaction_details.transaction_id)
            
            # Create VerifiedDataDetails instance from the extracted dictionary
            verified_details = VerifiedDataDetails(
                sender_name=extracted_details_dict.get('sender_name'),
                receiver_name=extracted_details_dict.get('receiver_name'),
                status=extracted_details_dict.get('status'),
                date=extracted_details_dict.get('date'),
                amount=extracted_details_dict.get('amount')
            )
            
            result.verified_data = verified_details
            result.status = verified_details.status if verified_details.status else "Unknown"
            
            if result.status and "Completed" in result.status:
                result.message = f"Transaction verification successful. Status: {result.status}."
            elif result.status:
                result.message = f"Transaction verification found, but status is: {result.status}."
            else:
                result.message = "Transaction page found, but status could not be determined."
            
            print(f"Verification completed for {transaction_details.transaction_id}. Status: {result.status}")

        except Error as e:
            result.status = "Playwright Error"
            result.message = f"A Playwright error occurred during verification: {e}"
            result.debug_info = str(e)
            print(f"Playwright Error for {transaction_details.transaction_id}: {result.message}")
        except Exception as e:
            result.status = "Failed"
            result.message = f"An unexpected error occurred during verification: {e}"
            result.debug_info = str(e)
            print(f"General Error for {transaction_details.transaction_id}: {result.message}")
            
        return result

