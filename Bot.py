import requests
import os
import json
import time
import gspread
from google.oauth2.service_account import Credentials
from http.server import HTTPServer, BaseHTTPRequestHandler
import logging
import base64
from datetime import datetime

# ==================== KONFIGURACJA ====================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

BOT_TOKEN = "8746910864:AAFiSK85KM_6OGsDHxEIGBm2xWkxIXWfMDc"
COHERE_API_KEY = "qRNhEDIPTpamhdhS0XofrAc1ZfpFg4gL8WIjci7B"  # klucz z twojego Unity!
COHERE_MODEL = "command-a-vision-07-2025"  # model z twojego Unity [citation:4][citation:8]
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/"

# ==================== GOOGLE SHEETS ====================
SHEET_ID = "1SHUyo_5sJYsQPiIIR9nCkAeJI2ZB5KQFx-1g0jXKaRw"
SHEET_NAME = "Аркуш1"  # twoja nazwa arkusza

# ==================== SŁOWNIKI KLASYFIKACJI ====================
known_suppliers = { ... }  # zostawiasz swoje słowniki!
supplier_categories = { ... }  # zostawiasz!

# ==================== FUNKCJE POMOCNICZE ====================
def send_message(chat_id, text):
    url = API_URL + "sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    requests.post(url, json=payload, timeout=10)

def classify_receipt(supplier, amount_str, products=""):
    # twoja istniejąca funkcja klasyfikacji – zostaje bez zmian!
    ...

def clean_value(value):
    if value == "UNKNOWN" or not value:
        return ""
    return str(value).strip()

def save_to_sheet(data):
    """Zapis do Google Sheets – bez zmian"""
    try:
        # ... twój istniejący kod zapisu ...
        return True
    except Exception as e:
        logging.error(f"Błąd zapisu: {e}")
        return False

# ==================== GŁÓWNA LOGIKA Z COHERE AI ====================
def handle_update(update):
    logging.info("=== NOWA WIADOMOŚĆ ===")
    
    if 'message' in update and 'text' in update['message']:
        if update['message']['text'] == '/start':
            send_message(update['message']['chat']['id'], "👋 Wyślij zdjęcie paragonu")
            return
    
    if 'message' not in update or 'photo' not in update['message']:
        return

    chat_id = update['message']['chat']['id']
    send_message(chat_id, "🔍 Analizuję paragon...")

    try:
        # 1. Pobierz zdjęcie z Telegrama
        file_id = update['message']['photo'][-1]['file_id']
        file_info = requests.get(API_URL + f"getFile?file_id={file_id}", timeout=10).json()
        file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info['result']['file_path']}"
        
        img_data = requests.get(file_url, timeout=30).content
        with open("receipt.jpg", "wb") as f:
            f.write(img_data)

        # 2. Koduj do base64 (dokładnie jak w Unity!)
        with open("receipt.jpg", "rb") as f:
            base64_image = base64.b64encode(f.read()).decode("utf-8")

        # 3. Wyślij do Cohere AI (Command A Vision)
        url = "https://api.cohere.ai/compatibility/v1/chat/completions"  # endpoint z twojego Unity
        
        # Prompt identyczny jak w Unity – AI samo wyciągnie dane!
        prompt = """Z tego paragonu podaj TYLKO: nazwę firmy, datę, kwotę całkowitą, metodę płatności, numer paragonu.
        Odpowiedz w formacie JSON:
        {
            "firma": "...",
            "data": "...",
            "kwota": "...",
            "platnosc": "...",
            "numer": "..."
        }
        Jeśli nie widzisz jakiegoś elementu, wpisz UNKNOWN."""
        
        payload = {
            "model": COHERE_MODEL,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                ]
            }],
            "response_format": {"type": "json_object"}  # wymuś JSON! [citation:4]
        }
        
        headers = {
            "Authorization": f"Bearer {COHERE_API_KEY}",
            "Content-Type": "application/json"
        }

        r = requests.post(url, json=payload, headers=headers, timeout=60)
        
        if r.status_code == 200:
            result = r.json()
            # Wyciągnij odpowiedź AI
            ai_response = json.loads(result['choices'][0]['message']['content'])
            
            # 4. Mapuj dane z AI na format tabeli
            supplier = ai_response.get('firma', 'UNKNOWN')
            date = ai_response.get('data', 'UNKNOWN')
            amount = ai_response.get('kwota', 'UNKNOWN')
            payment = ai_response.get('platnosc', 'UNKNOWN').lower()
            
            # Normalizuj płatność
            if 'card' in payment or 'karta' in payment:
                payment = 'card'
            elif 'cash' in payment or 'gotowka' in payment:
                payment = 'cash'
            else:
                payment = 'UNKNOWN'
            
            # Numer paragonu – z AI lub nazwy pliku
            bill_number = ai_response.get('numer', 'UNKNOWN')
            if bill_number == 'UNKNOWN':
                bill_number = os.path.splitext(os.path.basename(file_info['result']['file_path']))[0]
            
            # 5. Klasyfikacja (używając twoich słowników!)
            expense_item, category = classify_receipt(supplier, amount, "")
            
            # 6. Przygotuj dane do zapisu
            receipt_data = {
                'supplier': supplier,
                'date': date,
                'amount': amount,
                'payment': payment,
                'bill_number': bill_number,
                'expense_item': expense_item,
                'category': category
            }
            
            # 7. Zapisz do Google Sheets
            saved = save_to_sheet(receipt_data)
            
            # 8. Odpowiedź dla użytkownika
            response = f"✅ Paragon rozpoznany!\n\n"
            response += f"🏪 Dostawca: {supplier}\n"
            response += f"📅 Data: {date}\n"
            response += f"💰 Kwota: {amount}\n"
            response += f"💳 Płatność: {payment}\n"
            response += f"🧾 Nr paragonu: {bill_number}\n"
            response += f"📦 Expense: {expense_item}\n"
            response += f"📁 Kategoria: {category}\n\n"
            response += "📊 Zapisano do Google Sheets!" if saved else "⚠️ Nie udało się zapisać"
            
            send_message(chat_id, response)
            
        else:
            send_message(chat_id, f"⚠️ Błąd Cohere AI: {r.status_code}")

    except Exception as e:
        logging.exception(f"Błąd: {e}")
        send_message(chat_id, f"⚠️ Błąd: {str(e)[:100]}")
    finally:
        if os.path.exists("receipt.jpg"):
            os.remove("receipt.jpg")

# ==================== SERWER HTTP ====================
class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_len = int(self.headers.get('Content-Length', 0))
        post_body = self.rfile.read(content_len)
        try:
            update = json.loads(post_body)
            handle_update(update)
        except Exception as e:
            logging.exception(f"Błąd w POST: {e}")
        finally:
            self.send_response(200)
            self.end_headers()

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running")

def main():
    port = int(os.environ.get('PORT', 10000))
    server = HTTPServer(("0.0.0.0", port), Handler)
    logging.info(f"🚀 Bot z Cohere AI wystartował na porcie {port}")
    server.serve_forever()

if __name__ == "__main__":
    main()
