import requests
import os
import json
import time
import re
import gspread
import zipfile
import io
import asyncio
from google.oauth2.service_account import Credentials
from http.server import HTTPServer, BaseHTTPRequestHandler
import logging
import base64
from datetime import datetime
from collections import defaultdict

# ==================== KONFIGURACJA LOGOWANIA ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    force=True
)

# ==================== KONFIGURACJA ====================
BOT_TOKEN = "8746910864:AAFiSK85KM_6OGsDHxEIGBm2xWkxIXWfMDc"
COHERE_API_KEY = "qRNhEDIPTpamhdhS0XofrAc1ZfpFg4gL8WIjci7B"
COHERE_MODEL = "command-a-vision-07-2025"
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/"

# ==================== GOOGLE SHEETS ====================
SHEET_ID = "1SHUyo_5sJYsQPiIIR9nCkAeJI2ZB5KQFx-1g0jXKaRw"
# !!! WAŻNE: Zmień na dokładną nazwę swojego arkusza (sprawdź na dole tabeli) !!!
SHEET_NAME = "Аркуш1"  # np. "Arkusz1", "Sheet1", "Лист1"

# ==================== SŁOWNIKI ====================
known_suppliers = {
    "carrefour": "Carrefour",
    "m mart": "M MART SUPERMARKET",
    "mmart": "M MART SUPERMARKET",
    "al aswaq": "ALASWAQ ALWATANIA LLC",
    "alaswaq": "ALASWAQ ALWATANIA LLC",
    "aswaq": "ASWAQ DOLPHIN",
    "al khaldiya": "AL KHALDIYA",
    "khaldiya": "AL KHALDIYA",
    "almaya": "almaya",
    "day to day": "Day To Day",
    "lulu": "Lulu Center LLC",
    "spinneys": "Spinneys",
    "viva": "VIVA Premier Investment LLC",
    "uva": "UVA Premier Investment LLC",
    "uiua": "Uiua Premiere Investment LLC",
    "al safeer": "Al Safeer Int. LLC",
    "al manal": "AL MANAL HYPER MARKET LLC",
    "al hoot": "AL HOOT HYPERMARKET LLC",
    "hoot": "AL HOOT HYPERMARKET LLC",
    "gulf hyper": "GULF HYPER MARKET LLC",
    "al bayader": "AL BAYADER INTERNATIONAL",
    "al jazeera": "AL JAZEERA DISCOUNTS MARKETS",
    "hany": "HANY SUPERMARKET LLC OPC",
    "royal emirates": "ROYAL EMIRATES SUPERMARKET",
    "chef": "Chef Middle East LLC",
    "sfg": "SFG General Trading Co. L.L.C",
    "waynik": "SFG General Trading Co. L.L.C",
    "royal caviar": "ROYAL CAVIAR CANNING AND PRESERVATION OF SEAFOOD",
    "caviar": "ROYAL CAVIAR CANNING AND PRESERVATION OF SEAFOOD",
    "hubit": "HUBIT GENERAL TRADING LLC",
    "italfood": "A & J GENERAL TRADING",
    "a & j": "A & J GENERAL TRADING",
    "eat well": "Eat Well Live Well",
    "demchenko": "DEMCHENKO FOODSTUFF TRADING CO. L.L.C",
    "hotpack": "Hotpack Packaging L.L.C",
    "falconpack": "Falconpack Investory LLC",
    "falcon": "Falconpack Investory LLC",
    "fallonpack": "FALLONPACK INDUSTRY",
    "adnoc": "ADNOC",
    "enoc": "ENOC",
    "emarat": "Emarat",
    "brothers gas": "Brothers Gas",
    "eppco": "EPPCO",
    "al ansari": "AL ANSARI EXCHANGE",
    "ansari": "AL ANSARI EXCHANGE",
    "foodics": "FOODICS",
    "drc": "DRC Trading L.L.C",
    "value bag": "Value Bag General Trading LLC",
    "sudhi": "SUDHI MOTOR CYCLE REPAIRING",
    "al ershad": "AL ERSHAD MOTOR CYCLES & BICYCLES REPAIRING",
    "al mumtaz": "AL MUMTAZ METAL TURING",
    "fahen": "FAHEN MOTOR CYCLE",
    "harf": "HARF TYPING AND DOCUMEN",
    "ruads": "Ruads Media by Little Pet Kingdom"
}

supplier_categories = {
    "carrefour": "ingredients",
    "m mart": "ingredients",
    "al aswaq": "ingredients",
    "aswaq": "ingredients",
    "al khaldiya": "ingredients",
    "almaya": "ingredients",
    "day to day": "ingredients",
    "lulu": "ingredients",
    "spinneys": "ingredients",
    "viva": "ingredients",
    "uva": "ingredients",
    "uiua": "ingredients",
    "al safeer": "ingredients",
    "al manal": "ingredients",
    "al hoot": "ingredients",
    "gulf hyper": "ingredients",
    "al bayader": "ingredients",
    "al jazeera": "ingredients",
    "hany": "ingredients",
    "royal emirates": "ingredients",
    "chef": "ingredients",
    "sfg": "ingredients",
    "waynik": "ingredients",
    "royal caviar": "ingredients",
    "caviar": "ingredients",
    "hubit": "ingredients",
    "italfood": "ingredients",
    "a & j": "ingredients",
    "eat well": "ingredients",
    "demchenko": "ingredients",
    "hotpack": "packaging",
    "falconpack": "packaging",
    "falcon": "packaging",
    "fallonpack": "packaging",
    "adnoc": "fuel",
    "enoc": "fuel",
    "emarat": "fuel",
    "brothers gas": "gas",
    "eppco": "fuel",
    "al ansari": "salary",
    "ansari": "salary",
    "sudhi": "maintenance",
    "al ershad": "maintenance",
    "al mumtaz": "maintenance",
    "fahen": "maintenance",
    "foodics": "others",
    "drc": "others",
    "value bag": "others",
    "harf": "others",
    "ruads": "others"
}

# ==================== STAN UŻYTKOWNIKÓW ====================
user_states = {}
user_photos = defaultdict(list)
user_analysis_results = defaultdict(list)

# ==================== FUNKCJE POMOCNICZE ====================
def send_message(chat_id, text):
    url = API_URL + "sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    try:
        r = requests.post(url, json=payload, timeout=10)
        logging.info(f"send_message status: {r.status_code}")
    except Exception as e:
        logging.error(f"send_message error: {e}")

def format_date(raw_date):
    if not raw_date or raw_date == "UNKNOWN" or raw_date == "":
        return "UNKNOWN"
    raw_date = re.sub(r'[^\d/]', '', raw_date)
    match = re.search(r'(\d{1,2})/?(\d{1,2})', raw_date)
    if match:
        day = match.group(1).zfill(2)
        month = match.group(2).zfill(2)
        if 1 <= int(day) <= 31 and 1 <= int(month) <= 12:
            return f"{day}/{month}"
    return "UNKNOWN"

def normalize_payment(payment_text):
    if not payment_text or payment_text == "UNKNOWN":
        return "UNKNOWN"
    payment_lower = payment_text.lower()
    card_keywords = ['card', 'credit', 'debit', 'visa', 'mastercard', 'karta', 'carta', 'carte']
    if any(kw in payment_lower for kw in card_keywords):
        return "card"
    cash_keywords = ['cash', 'gotówka', 'gotowka', 'kontant', 'gotowizna']
    if any(kw in payment_lower for kw in cash_keywords):
        return "cash"
    return "UNKNOWN"

def clean_amount(raw_amount):
    if not raw_amount or raw_amount == "UNKNOWN":
        return "UNKNOWN"
    cleaned = re.sub(r'[^\d.,]', '', raw_amount)
    cleaned = cleaned.replace('.', ',')
    if cleaned.count(',') > 1:
        cleaned = cleaned.replace(',', '')
        if len(cleaned) > 2:
            cleaned = cleaned[:-2] + ',' + cleaned[-2:]
    return cleaned

def find_supplier(text):
    text_lower = text.lower()
    for key, value in known_suppliers.items():
        if key in text_lower:
            return value
    return "UNKNOWN"

def classify_receipt(supplier, amount_str, products=""):
    supplier_lower = supplier.lower()
    if 'ansari' in supplier_lower:
        return "salary", "salary"
    if 'brothers gas' in supplier_lower:
        return "gas", "utilities"
    if any(x in supplier_lower for x in ['adnoc', 'enoc', 'emarat', 'eppco']):
        try:
            amount = float(amount_str.replace(',', '.'))
            expense = "bike fuel" if amount < 40 else "car fuel"
            return expense, "others"
        except:
            return "car fuel", "others"
    if any(x in supplier_lower for x in ['hotpack', 'falconpack', 'falcon', 'pack']):
        return "packaging", "packaging"
    if any(x in supplier_lower for x in ['sudhi', 'al ershad', 'al mumtaz', 'fahen']):
        if 'oil' in products.lower():
            return "bike oil", "others"
        return "maintenance", "maintenance"
    for key, category in supplier_categories.items():
        if key in supplier_lower:
            if category == "ingredients":
                return "ingredients", "ingredients"
            elif category == "fuel":
                try:
                    amount = float(amount_str.replace(',', '.'))
                    expense = "bike fuel" if amount < 40 else "car fuel"
                    return expense, "others"
                except:
                    return "car fuel", "others"
            else:
                return category, category
    return "ingredients", "ingredients"

def get_receipt_fingerprint(receipt_data):
    return f"{receipt_data.get('supplier', '')}|{receipt_data.get('amount', '')}|{receipt_data.get('payment', '')}|{receipt_data.get('date', '')}"

# ==================== FUNKCJE GOOGLE SHEETS ====================
def get_google_sheet():
    logging.info("=== PRÓBA POŁĄCZENIA Z GOOGLE SHEETS ===")
    possible_paths = [
        '/etc/secrets/google-credentials.json',
        'google-credentials.json',
        os.path.join(os.getcwd(), 'google-credentials.json')
    ]
    creds_path = None
    for path in possible_paths:
        if os.path.exists(path):
            creds_path = path
            logging.info(f"✅ Znaleziono plik credentials: {path}")
            logging.info(f"   Rozmiar pliku: {os.path.getsize(path)} bajtów")
            break
    if not creds_path:
        logging.error("❌ NIE ZNALEZIONO pliku credentials!")
        return None
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_file(creds_path, scopes=scope)
        logging.info("✅ Credentials wczytane pomyślnie")
        client = gspread.authorize(creds)
        logging.info("✅ Autoryzacja gspread OK")
        sheet = client.open_by_key(SHEET_ID)
        logging.info(f"✅ Tabela otwarta, tytuł: {sheet.title}")
        worksheet = sheet.worksheet(SHEET_NAME)
        logging.info(f"✅ Arkusz otwarty, nazwa: {SHEET_NAME}")
        return worksheet
    except Exception as e:
        logging.error(f"❌ BŁĄD połączenia: {str(e)}")
        logging.error(f"   Typ błędu: {type(e).__name__}")
        return None

def clean_value(value):
    if value == "UNKNOWN" or not value:
        return ""
    return str(value).strip()

def save_to_sheet(data):
    logging.info("=== PRÓBA ZAPISU DO GOOGLE SHEETS ===")
    try:
        sheet = get_google_sheet()
        if not sheet:
            logging.error("❌ Nie można uzyskać dostępu do arkusza")
            return False
        row = [
            '',                                      # Kolumna A - pusta
            clean_value(data.get('date', '')),       # Kolumna B - data
            clean_value(data.get('supplier', '')),   # Kolumna C - dostawca
            clean_value(data.get('bill_number', '')),# Kolumna D - numer paragonu
            clean_value(data.get('payment', '')),    # Kolumna E - płatność
            clean_value(data.get('expense_item', '')), # Kolumna F - expense item
            clean_value(data.get('category', '')),   # Kolumna G - kategoria
            '',                                      # Kolumna H - pusta
            clean_value(data.get('amount', ''))      # Kolumna I - kwota
        ]
        logging.info(f"   Próba zapisu wiersza: {row}")
        sheet.append_row(row)
        logging.info(f"✅ Zapisano do Google Sheets")
        return True
    except Exception as e:
        logging.error(f"❌ Błąd zapisu: {str(e)}")
        return False

# ==================== ANALIZA ZDJĘCIA PRZEZ COHERE ====================
async def analyze_image_with_cohere(image_path, chat_id):
    try:
        with open(image_path, "rb") as f:
            base64_image = base64.b64encode(f.read()).decode("utf-8")

        url = "https://api.cohere.ai/compatibility/v1/chat/completions"
        prompt = """Z tego paragonu wyciągnij następujące informacje:
        1. Nazwa firmy/sklepu (np. Carrefour, ADNOC, AL KHALDIYA)
        2. Data w formacie DD/MM/YYYY
        3. Kwota całkowita do zapłaty
        4. Metoda płatności (card/cash)
        5. Numer paragonu/faktury

        Odpowiedz TYLKO w formacie JSON:
        {
            "firma": "nazwa firmy",
            "data": "DD/MM/YYYY",
            "kwota": "kwota",
            "platnosc": "card lub cash",
            "numer": "numer paragonu"
        }
        Jeśli nie znajdziesz jakiegoś elementu, wpisz "UNKNOWN"."""

        payload = {
            "model": COHERE_MODEL,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                ]
            }],
            "response_format": {"type": "json_object"}
        }

        headers = {"Authorization": f"Bearer {COHERE_API_KEY}", "Content-Type": "application/json"}
        r = requests.post(url, json=payload, headers=headers, timeout=60)

        if r.status_code == 200:
            result = r.json()
            ai_response = json.loads(result['choices'][0]['message']['content'])
            logging.info(f"✅ Odpowiedź Cohere: {ai_response}")

            supplier = ai_response.get('firma', 'UNKNOWN')
            date = format_date(ai_response.get('data', 'UNKNOWN'))
            amount = clean_amount(ai_response.get('kwota', 'UNKNOWN'))
            payment = normalize_payment(ai_response.get('platnosc', 'UNKNOWN'))
            bill_number = ai_response.get('numer', 'UNKNOWN')
            if bill_number == "UNKNOWN" or not bill_number:
                bill_number = os.path.splitext(os.path.basename(image_path))[0]

            expense_item, category = classify_receipt(supplier, amount, "")

            return {
                'supplier': supplier,
                'date': date,
                'amount': amount,
                'payment': payment,
                'bill_number': bill_number,
                'expense_item': expense_item,
                'category': category
            }
        else:
            logging.error(f"Błąd Cohere: {r.status_code}")
            return None
    except Exception as e:
        logging.exception(f"Błąd analizy obrazu: {e}")
        return None

# ==================== GŁÓWNA LOGIKA BOTA ====================
def handle_start(chat_id):
    welcome_text = """
🤖 <b>Receipt Scanner Bot v5.2</b>

📸 <b>Co potrafię:</b>
• Rozpoznaję tekst z paragonów
• Klasyfikuję dostawców
• Rozróżniam metody płatności
• Zapisuję dane do Google Sheets
• Tryb archiwizacji /chuvan

📋 <b>Jak używać:</b>
1. Wyślij mi zdjęcie paragonu
2. AI przeanalizuje obraz
3. Otrzymasz podsumowanie
4. Dane trafią do tabeli
"""
    send_message(chat_id, welcome_text)

def handle_update(update):
    logging.info("=== NOWA WIADOMOŚĆ ===")

    if 'message' in update and 'text' in update['message']:
        text = update['message']['text']
        chat_id = update['message']['chat']['id']
        user_id = update['message']['from']['id']

        if text == '/start':
            handle_start(chat_id)
            return

        elif text == '/chuvan':
            user_states[user_id] = 'ARCHIVE_COLLECT'
            user_photos[user_id] = []
            user_analysis_results[user_id] = []
            send_message(chat_id, "🗂️ Tryb archiwizacji aktywowany. Wysyłaj zdjęcia – najpierw je przeanalizuję.\nGdy skończysz wysyłać, napisz /archiwum.")
            return

        elif text == '/archiwum':
            if user_states.get(user_id) == 'ARCHIVE_COLLECT':
                if not user_photos[user_id]:
                    send_message(chat_id, "❌ Nie wysłałeś żadnych zdjęć do archiwizacji.")
                    return

                user_states[user_id] = 'ARCHIVE_DECISION'
                send_message(chat_id, "Czy chcesz zapisać te zdjęcia w archiwum ZIP?\n/tak – zapisz wszystko (podam nazwy)\n/nie – nie zapisuj, tylko dane trafią do tabeli")
            else:
                send_message(chat_id, "❌ Najpierw wpisz /chuvan, żeby rozpocząć tryb archiwizacji.")
            return

        elif text == '/tak':
            if user_states.get(user_id) == 'ARCHIVE_DECISION':
                user_states[user_id] = 'ARCHIVE_ASK_NAME'
                send_message(chat_id, "Podaj nazwę początkową (np. b235):")
            else:
                send_message(chat_id, "❌ Nie ma oczekującej archiwizacji.")
            return

        elif text == '/nie':
            if user_states.get(user_id) == 'ARCHIVE_DECISION':
                send_message(chat_id, f"⏳ Zapisuję {len(user_analysis_results[user_id])} zdjęć do tabeli...")
                
                for data in user_analysis_results[user_id]:
                    save_to_sheet(data)
                
                send_message(chat_id, f"✅ Zapisano {len(user_analysis_results[user_id])} wierszy w tabeli!")
                
                # Wyczyść stan
                del user_states[user_id]
                del user_photos[user_id]
                del user_analysis_results[user_id]
            else:
                send_message(chat_id, "❌ Nie ma oczekującej archiwizacji.")
            return

    # Obsługa zdjęć w trybie archiwizacji
    if 'message' in update and 'photo' in update['message']:
        chat_id = update['message']['chat']['id']
        user_id = update['message']['from']['id']

        if user_states.get(user_id) == 'ARCHIVE_COLLECT':
            file_id = update['message']['photo'][-1]['file_id']
            file_info = requests.get(API_URL + f"getFile?file_id={file_id}", timeout=10).json()
            file_path = file_info['result']['file_path']
            file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"

            img_data = requests.get(file_url, timeout=30).content
            filename = f"temp_{file_id}.jpg"
            with open(filename, "wb") as f:
                f.write(img_data)

            current_count = len(user_photos[user_id]) + 1
            send_message(chat_id, f"🔍 Analizuję zdjęcie {current_count}...")
            
            # Analiza zdjęcia
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            receipt_data = loop.run_until_complete(analyze_image_with_cohere(filename, chat_id))
            loop.close()

            if receipt_data:
                user_analysis_results[user_id].append(receipt_data)
                user_photos[user_id].append((filename, img_data))
                send_message(chat_id, f"✅ Otrzymałem ({current_count})")
            else:
                send_message(chat_id, "⚠️ Nie udało się przeanalizować zdjęcia")
                os.remove(filename)
            return

    # Obsługa odpowiedzi z nazwą początkową (ARCHIVE_ASK_NAME)
    if 'message' in update and 'text' in update['message']:
        text = update['message']['text']
        chat_id = update['message']['chat']['id']
        user_id = update['message']['from']['id']

        if user_states.get(user_id) == 'ARCHIVE_ASK_NAME':
            base_name = text.strip()
            
            send_message(chat_id, f"⏳ Tworzę archiwum ZIP dla {len(user_photos[user_id])} zdjęć...")

            # Wyodrębnij numer początkowy z nazwy (np. z "b235" weźmie 235)
            match = re.search(r'(\d+)$', base_name)
            if match:
                start_num = int(match.group(1))
                prefix = base_name[:match.start()]
                
                # Tworzenie archiwum ZIP
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                    for idx, (filename, img_data) in enumerate(user_photos[user_id]):
                        current_number = start_num + idx
                        arcname = f"{prefix}{current_number}.jpg"
                        zip_file.writestr(arcname, img_data)
                
                zip_buffer.seek(0)

                # Wyślij ZIP
                files = {'document': ('archiwum.zip', zip_buffer.getvalue())}
                requests.post(API_URL + 'sendDocument', data={'chat_id': chat_id}, files=files)

                # Wyślij każde zdjęcie po kolei z opisem
                send_message(chat_id, f"📸 Wysyłam {len(user_analysis_results[user_id])} przeanalizowanych zdjęć:")
                
                for idx, (filename, img_data) in enumerate(user_photos[user_id]):
                    # Wyślij zdjęcie
                    with open(filename, 'rb') as f:
                        files = {'photo': (f'zdjecie_{idx+1}.jpg', f, 'image/jpeg')}
                        requests.post(API_URL + 'sendPhoto', data={'chat_id': chat_id}, files=files)
                    
                    # Wyślij opis
                    data = user_analysis_results[user_id][idx]
                    current_number = start_num + idx
                    response = f"✅ Paragon rozpoznany!\n\n"
                    response += f"🏪 Dostawca: {data['supplier']}\n"
                    response += f"📅 Data: {data['date']}\n"
                    response += f"💰 Kwota: {data['amount']}\n"
                    response += f"💳 Płatność: {data['payment']}\n"
                    response += f"🧾 Nr paragonu: {prefix}{current_number}\n"
                    response += f"📦 Expense: {data['expense_item']}\n"
                    response += f"📁 Kategoria: {data['category']}\n\n"
                    
                    send_message(chat_id, response)

                # Zapisz wszystkie dane do tabeli z poprawnymi numerami
                send_message(chat_id, f"⏳ Zapisuję {len(user_analysis_results[user_id])} wierszy w Google Sheets...")

                saved_count = 0
                for idx, data in enumerate(user_analysis_results[user_id]):
                    current_number = start_num + idx
                    # Nadpisz numer paragonu tym, co jest w nazwie pliku
                    data['bill_number'] = f"{prefix}{current_number}"
                    if save_to_sheet(data):
                        saved_count += 1

                send_message(chat_id, f"✅ Zapisano {saved_count} z {len(user_analysis_results[user_id])} wierszy w tabeli!")

                # Wyczyść stan
                del user_states[user_id]
                
                # Usuń pliki tymczasowe
                for filename, _ in user_photos[user_id]:
                    if os.path.exists(filename):
                        os.remove(filename)
                
                del user_photos[user_id]
                del user_analysis_results[user_id]
            else:
                send_message(chat_id, "❌ Nazwa musi zawierać cyfry na końcu (np. b235)")
            return

    # Normalna obsługa pojedynczego zdjęcia (poza trybem archiwizacji)
    if 'message' in update and 'photo' in update['message']:
        chat_id = update['message']['chat']['id']
        user_id = update['message']['from']['id']

        if user_id not in user_states:
            file_id = update['message']['photo'][-1]['file_id']
            file_info = requests.get(API_URL + f"getFile?file_id={file_id}", timeout=10).json()
            file_path = file_info['result']['file_path']
            file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"

            img_data = requests.get(file_url, timeout=30).content
            filename = f"temp_{file_id}.jpg"
            with open(filename, "wb") as f:
                f.write(img_data)

            send_message(chat_id, "🔍 Analizuję paragon...")
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            receipt_data = loop.run_until_complete(analyze_image_with_cohere(filename, chat_id))
            loop.close()

            if receipt_data:
                saved = save_to_sheet(receipt_data)

                response = f"✅ Paragon rozpoznany!\n\n"
                response += f"🏪 Dostawca: {receipt_data['supplier']}\n"
                response += f"📅 Data: {receipt_data['date']}\n"
                response += f"💰 Kwota: {receipt_data['amount']}\n"
                response += f"💳 Płatność: {receipt_data['payment']}\n"
                response += f"🧾 Nr paragonu: {receipt_data['bill_number']}\n"
                response += f"📦 Expense: {receipt_data['expense_item']}\n"
                response += f"📁 Kategoria: {receipt_data['category']}\n\n"

                if saved:
                    response += "📊 Zapisano do Google Sheets!"
                else:
                    response += "⚠️ Nie udało się zapisać do Sheets"

                send_message(chat_id, response)
            else:
                send_message(chat_id, "😕 Nie udało się rozpoznać paragonu")

            os.remove(filename)
            return

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
    logging.info(f"🚀 Bot z Cohere AI i trybem archiwizacji wystartował na porcie {port}")
    logging.info(f"📊 Google Sheets ID: {SHEET_ID}")
    server.serve_forever()

if __name__ == "__main__":
    main()
