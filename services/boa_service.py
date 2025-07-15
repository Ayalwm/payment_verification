# services/boa_service.py

import asyncio
import re
from datetime import datetime
from playwright.async_api import async_playwright, Error, TimeoutError
from bs4 import BeautifulSoup 
import sys 

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from models import VerificationResult, VerifiedDataDetails

class BOAService:
    def __init__(self):
        self.base_url = "https://cs.bankofabyssinia.com/slip/"

    async def verify_payment(self, transaction_id: str, sender_account_last_5_digits: str) -> dict:
        full_trx_param = f"{transaction_id}{sender_account_last_5_digits}"
        receipt_url = f"{self.base_url}?trx={full_trx_param}"
        
        sender_name = None
        sender_bank_name = "Bank of Abyssinia"
        receiver_name = None 
        receiver_bank_name = None 
        transaction_status = "Completed"
        payment_date_iso = None
        final_amount_float = 0.0
        extracted_transaction_id = transaction_id

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()

            try:
                await page.goto(receipt_url, wait_until="domcontentloaded", timeout=60000) 
                await page.wait_for_selector('h1.text-center:has-text("Receipt")', timeout=30000)
                await page.wait_for_selector('table.my-5', timeout=30000)
                
                html_content = await page.content()
                soup = BeautifulSoup(html_content, 'html.parser')

                def get_value_by_label_bs4(soup_obj, label_text):
                    label_td = soup_obj.find('td', string=lambda text: text and text.strip() == label_text)
                    if label_td and label_td.find_next_sibling('td'):
                        return label_td.find_next_sibling('td').get_text(strip=True)
                    return None
                
                main_table = soup.find('table', class_='my-5')

                if main_table:
                    sender_name = get_value_by_label_bs4(main_table, "Source Account Name")
                    receiver_name = get_value_by_label_bs4(main_table, "Receiver's Name")

                    amount_str = get_value_by_label_bs4(main_table, "Transferred amount")
                    if amount_str:
                        cleaned_amount_str = re.sub(r'[^\d.]', '', amount_str)
                        try:
                            final_amount_float = float(cleaned_amount_str)
                        except ValueError:
                            pass

                    date_str = get_value_by_label_bs4(main_table, "Transaction Date")
                    if date_str:
                        try:
                            day, month, year_short = date_str.split(' ')[0].split('/')
                            hour, minute = date_str.split(' ')[1].split(':')
                            full_year = f"20{year_short}"
                            
                            dt_obj = datetime(int(full_year), int(month), int(day), int(hour), int(minute))
                            payment_date_iso = dt_obj.isoformat()
                        except ValueError:
                            pass

                    extracted_transaction_id = get_value_by_label_bs4(main_table, "Transaction Reference")
                    if not extracted_transaction_id:
                        extracted_transaction_id = transaction_id

                else:
                    transaction_status = "Failed"

                return {
                    "sender_name": sender_name,
                    "sender_bank_name": sender_bank_name, 
                    "receiver_name": receiver_name,
                    "receiver_bank_name": receiver_bank_name, 
                    "status": transaction_status,
                    "date": payment_date_iso,
                    "amount": final_amount_float,
                    "transaction_id": extracted_transaction_id
                }

            except TimeoutError as e:
                return {
                    "sender_name": None, "sender_bank_name": "Bank of Abyssinia", 
                    "receiver_name": None, "receiver_bank_name": None, 
                    "status": "Network/Load Timeout", "date": None, "amount": 0.0,
                    "debug_info": str(e), "transaction_id": transaction_id
                }
            except Error as e:
                return {
                    "sender_name": None, "sender_bank_name": "Bank of Abyssinia", 
                    "receiver_name": None, "receiver_bank_name": None, 
                    "status": "Playwright Error", "date": None, "amount": 0.0,
                    "debug_info": str(e), "transaction_id": transaction_id
                }
            except Exception as e:
                return {
                    "sender_name": None, "sender_bank_name": "Bank of Abyssinia", 
                    "receiver_name": None, "receiver_bank_name": None, 
                    "status": "Failed", "date": None, "amount": 0.0,
                    "debug_info": str(e), "transaction_id": transaction_id
                }
            finally:
                await browser.close()
            
