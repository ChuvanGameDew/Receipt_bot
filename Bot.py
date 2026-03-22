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
from difflib import SequenceMatcher
import traceback

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
SHEET_NAME = "Аркуш1"

# ==================== KONFIGURACJA AUTORYZACJI ====================
DATA_FILE = "bot_data.json"

USER_PASSWORDS = {
    "user1234": {"used": False, "max_photos": 5, "used_by": None},
    "user5678": {"used": False, "max_photos": 5, "used_by": None},
    "user9012": {"used": False, "max_photos": 5, "used_by": None}
}

ADMIN_PASSWORDS = {
    "admin08": {"used": False, "used_by": None},
    "admin09": {"used": False, "used_by": None},
    "admin10": {"used": False, "used_by": None},
    "admin11": {"used": False, "used_by": None},
    "admin12": {"used": False, "used_by": None}
}

authorized_users = {}

# ==================== BAZA DUPLIKATÓW ====================
receipts_database = {}

def load_receipts_database():
    global receipts_database
    if os.path.exists("receipts_db.json"):
        try:
            with open("receipts_db.json", 'r', encoding='utf-8') as f:
                receipts_database = json.load(f)
                logging.info(f"✅ Wczytano {len(receipts_database)} unikalnych fingerprintów z bazy")
        except Exception as e:
            logging.error(f"❌ Błąd wczytywania bazy: {e}")
            receipts_database = {}

def save_receipts_database():
    try:
        with open("receipts_db.json", 'w', encoding='utf-8') as f:
            json.dump(receipts_database, f, indent=2, ensure_ascii=False)
        logging.info(f"✅ Zapisano {len(receipts_database)} fingerprintów do bazy")
    except Exception as e:
        logging.error(f"❌ Błąd zapisu bazy: {e}")

def calculate_fingerprint(receipt_data):
    supplier = receipt_data.get('supplier', '')
    amount = receipt_data.get('amount', '')
    date = receipt_data.get('date', '')
    return f"{supplier}|{amount}|{date}"

def find_duplicate_group(receipt_data, similarity_threshold=0.85):
    new_fingerprint = calculate_fingerprint(receipt_data)
    
    if new_fingerprint in receipts_database:
        return new_fingerprint, receipts_database[new_fingerprint]
    
    for fp, items in receipts_database.items():
        for item in items:
            original_data = item['full_data']
            similarity = SequenceMatcher(None, 
                f"{original_data.get('supplier', '')}{original_data.get('amount', '')}{original_data.get('date', '')}",
                f"{receipt_data.get('supplier', '')}{receipt_data.get('amount', '')}{receipt_data.get('date', '')}"
            ).ratio()
            
            if similarity >= similarity_threshold:
                return fp, items
    
    return None, None

def get_next_filename_in_group(existing_filenames):
    if not existing_filenames:
        return None
    
    base_names = set()
    for name in existing_filenames:
        if '.' in name:
            base = name.split('.')[0]
        else:
            base = name
        base_names.add(base)
    
    if len(base_names) == 1:
        base_name = list(base_names)[0]
        max_suffix = 0
        for name in existing_filenames:
            if '.' in name:
                try:
                    suffix = int(name.split('.')[1])
                    max_suffix = max(max_suffix, suffix)
                except:
                    pass
        return f"{base_name}.{max_suffix + 1}"
    return None

def add_to_receipts_database(filename, receipt_data, group_fingerprint=None):
    if group_fingerprint:
        fingerprint = group_fingerprint
    else:
        fingerprint = calculate_fingerprint(receipt_data)
    
    if fingerprint not in receipts_database:
        receipts_database[fingerprint] = []
    
    existing_filenames = [item['filename'] for item in receipts_database[fingerprint]]
    
    if filename not in existing_filenames:
        receipts_database[fingerprint].append({
            'filename': filename,
            'timestamp': datetime.now().isoformat(),
            'full_data': receipt_data
        })
        logging.info(f"✅ Dodano {filename} do grupy {fingerprint}")
    
    save_receipts_database()
    return fingerprint

def update_sheet_group(fingerprint, items):
    if not items:
        return False
    
    sorted_items = sorted(items, key=lambda x: x['filename'])
    filenames_str = ','.join([item['filename'] for item in sorted_items])
    first_data = sorted_items[0]['full_data']
    
    data = {
        'date': first_data.get('date', ''),
        'supplier': first_data.get('supplier', ''),
        'bill_numbers': filenames_str,
        'payment': first_data.get('payment', ''),
        'expense_item': first_data.get('expense_item', ''),
        'category': first_data.get('category', ''),
        'amount': first_data.get('amount', '')
    }
    
    return save_group_to_sheet(data, fingerprint)

def save_group_to_sheet(data, fingerprint):
    logging.info(f"=== ZAPIS GRUPY DO GOOGLE SHEETS: {fingerprint} ===")
    try:
        sheet = get_google_sheet()
        if not sheet:
            logging.error("❌ Nie można uzyskać dostępu do arkusza")
            return False
        
        all_records = sheet.get_all_records()
        
        headers = sheet.row_values(1)
        if 'fingerprint' not in headers:
            sheet.update_cell(1, 10, 'fingerprint')
        
        existing_row = None
        existing_row_num = None
        
        for idx, record in enumerate(all_records, start=2):
            if record.get('fingerprint') == fingerprint:
                existing_row = record
                existing_row_num = idx
                break
        
        row = [
            '',
            clean_value(data.get('date', '')),
            clean_value(data.get('supplier', '')),
            clean_value(data.get('bill_numbers', '')),
            clean_value(data.get('payment', '')),
            clean_value(data.get('expense_item', '')),
            clean_value(data.get('category', '')),
            '',
            clean_value(data.get('amount', '')),
            fingerprint
        ]
        
        if existing_row_num:
            for col, value in enumerate(row, start=1):
                sheet.update_cell(existing_row_num, col, value)
            logging.info(f"✅ Zaktualizowano grupę w wierszu {existing_row_num}: {data['bill_numbers']}")
        else:
            sheet.append_row(row)
            logging.info(f"✅ Dodano nową grupę: {data['bill_numbers']}")
        
        return True
    except Exception as e:
        logging.error(f"❌ Błąd zapisu grupy: {str(e)}")
        logging.error(traceback.format_exc())
        return False

# ==================== FUNKCJE DO ZAPISU/ODCZYTU DANYCH ====================
def load_data():
    global authorized_users, USER_PASSWORDS, ADMIN_PASSWORDS
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                authorized_users = data.get('authorized_users', {})
                authorized_users = {int(k): v for k, v in authorized_users.items()}
                USER_PASSWORDS = data.get('user_passwords', USER_PASSWORDS)
                ADMIN_PASSWORDS = data.get('admin_passwords', ADMIN_PASSWORDS)
                logging.info(f"✅ Wczytano dane z pliku {DATA_FILE}")
        except Exception as e:
            logging.error(f"❌ Błąd wczytywania danych: {e}")
    else:
        logging.info("📁 Brak pliku z danymi, używam domyślnych ustawień")

def save_data():
    try:
        data = {
            'authorized_users': authorized_users,
            'user_passwords': USER_PASSWORDS,
            'admin_passwords': ADMIN_PASSWORDS
        }
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logging.info(f"✅ Zapisano dane do pliku {DATA_FILE}")
    except Exception as e:
        logging.error(f"❌ Błąd zapisu danych: {e}")

load_data()
load_receipts_database()

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

def send_document(chat_id, file_data, filename):
    """Wysyła dokument z lepszą obsługą błędów"""
    url = API_URL + "sendDocument"
    try:
        files = {
            'document': (filename, file_data, 'application/zip')
        }
        data = {'chat_id': chat_id}
        
        logging.info(f"Wysyłam dokument: {filename}, rozmiar: {len(file_data)} bajtów")
        r = requests.post(url, data=data, files=files, timeout=60)
        
        logging.info(f"Status wysyłania dokumentu: {r.status_code}")
        if r.status_code == 200:
            logging.info("✅ Dokument wysłany pomyślnie")
            return True
        else:
            logging.error(f"❌ Błąd wysyłania dokumentu: {r.text}")
            send_message(chat_id, f"❌ Błąd wysyłania ZIP: {r.status_code}")
            return False
    except Exception as e:
        logging.error(f"❌ Wyjątek przy wysyłaniu dokumentu: {e}")
        send_message(chat_id, f"❌ Błąd wysyłania ZIP: {str(e)}")
        return False

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

def check_authorization(user_id, message_text, chat_id):
    global USER_PASSWORDS, ADMIN_PASSWORDS, authorized_users
    
    if user_id in authorized_users:
        user_info = authorized_users[user_id]
        if user_info['type'] == 'user' and user_info['photos_used'] >= user_info['max_photos']:
            send_message(chat_id, "❌ Limit zdjęć dla tego konta został wyczerpany. Hasło wygasło.")
            return False
        return True
    
    if message_text and message_text.startswith('/'):
        send_message(chat_id, "🔒 Ten bot jest chroniony hasłem. Podaj hasło dostępu.")
        return False
    
    if message_text and message_text in USER_PASSWORDS:
        if USER_PASSWORDS[message_text]['used']:
            send_message(chat_id, "❌ To hasło zostało już wykorzystane przez innego użytkownika.")
            return False
        
        authorized_users[user_id] = {
            'type': 'user',
            'max_photos': USER_PASSWORDS[message_text]['max_photos'],
            'photos_used': 0,
            'used_password': message_text
        }
        USER_PASSWORDS[message_text]['used'] = True
        USER_PASSWORDS[message_text]['used_by'] = user_id
        save_data()
        send_message(chat_id, f"✅ Hasło poprawne! Możesz wysłać maksymalnie {USER_PASSWORDS[message_text]['max_photos']} zdjęć.")
        return True
    
    if message_text and message_text in ADMIN_PASSWORDS:
        if ADMIN_PASSWORDS[message_text]['used']:
            send_message(chat_id, "❌ To hasło administratorskie zostało już wykorzystane przez innego użytkownika.")
            return False
        
        authorized_users[user_id] = {
            'type': 'admin',
            'photos_used': 0,
            'used_password': message_text
        }
        ADMIN_PASSWORDS[message_text]['used'] = True
        ADMIN_PASSWORDS[message_text]['used_by'] = user_id
        save_data()
        send_message(chat_id, "✅ Hasło administratorskie! Nie masz limitu zdjęć.")
        return True
    
    send_message(chat_id, "🔒 Nieprawidłowe hasło. Podaj poprawne hasło dostępu.")
    return False

def increment_photo_count(user_id, chat_id):
    if user_id in authorized_users:
        user_info = authorized_users[user_id]
        if user_info['type'] == 'user':
            user_info['photos_used'] += 1
            remaining = user_info['max_photos'] - user_info['photos_used']
            logging.info(f"Użytkownik {user_id} wykorzystał {user_info['photos_used']}/{user_info['max_photos']} zdjęć")
            save_data()
            
            if remaining <= 0:
                send_message(chat_id, f"⚠️ To było ostatnie zdjęcie z Twojego limitu. Dostęp wygasł.")
            elif remaining <= 2:
                send_message(chat_id, f"⚠️ Pozostało Ci tylko {remaining} zdjęć.")
        return True
    return False

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
            break
    if not creds_path:
        logging.error("❌ NIE ZNALEZIONO pliku credentials!")
        return None
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_file(creds_path, scopes=scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SHEET_ID)
        worksheet = sheet.worksheet(SHEET_NAME)
        logging.info(f"✅ Arkusz otwarty, nazwa: {SHEET_NAME}")
        return worksheet
    except Exception as e:
        logging.error(f"❌ BŁĄD połączenia: {str(e)}")
        return None

def clean_value(value):
    if value == "UNKNOWN" or not value:
        return ""
    return str(value).strip()

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

            supplier = find_supplier(ai_response.get('firma', 'UNKNOWN'))
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

def handle_start(chat_id):
    welcome_text = """
🤖 <b>Receipt Scanner Bot v8.0 - Grupowanie duplikatów!</b>

📸 <b>Co potrafię:</b>
• Rozpoznaję tekst z paragonów
• Klasyfikuję dostawców
• GRUPUJĘ DUPLIKATY w jednym wierszu (b211,b211.1,b211.2)
• Automatycznie nadaję nazwy z suffixami
• Zapisuję dane do Google Sheets
• Tryb archiwizacji /chuvan
• System haseł jednorazowych

📋 <b>Jak używać:</b>
1. Wyślij mi zdjęcie paragonu
2. AI przeanalizuje obraz
3. Duplikaty są grupowane w jednym wierszu
4. Dane trafiają do tabeli
"""
    send_message(chat_id, welcome_text)

def handle_update(update):
    logging.info("=== NOWA WIADOMOŚĆ ===")

    if 'message' in update:
        chat_id = update['message']['chat']['id']
        user_id = update['message']['from']['id']
        message_text = update['message'].get('text', '')
        
        if not check_authorization(user_id, message_text, chat_id):
            return
        
        if 'photo' in update['message']:
            if user_id in authorized_users:
                user_info = authorized_users[user_id]
                if user_info['type'] == 'user' and user_info['photos_used'] >= user_info['max_photos']:
                    send_message(chat_id, "❌ Osiągnąłeś maksymalną liczbę zdjęć. Hasło wygasło.")
                    return
        
        if message_text == '/start':
            handle_start(chat_id)
            return

        elif message_text == '/chuvan':
            user_states[user_id] = 'ARCHIVE_COLLECT'
            user_photos[user_id] = []
            user_analysis_results[user_id] = []
            send_message(chat_id, "🗂️ Tryb archiwizacji aktywowany. Wysyłaj zdjęcia – najpierw je przeanalizuję.\nGdy skończysz wysyłać, napisz /archiwum.")
            return

        elif message_text == '/archiwum':
            if user_states.get(user_id) == 'ARCHIVE_COLLECT':
                if not user_photos[user_id]:
                    send_message(chat_id, "❌ Nie wysłałeś żadnych zdjęć do archiwizacji.")
                    return

                user_states[user_id] = 'ARCHIVE_DECISION'
                send_message(chat_id, "Czy chcesz zapisać te zdjęcia w archiwum ZIP?\n/tak – zapisz wszystko (podam nazwy)\n/nie – nie zapisuj, tylko dane trafią do tabeli")
            else:
                send_message(chat_id, "❌ Najpierw wpisz /chuvan, żeby rozpocząć tryb archiwizacji.")
            return

        elif message_text == '/tak':
            if user_states.get(user_id) == 'ARCHIVE_DECISION':
                user_states[user_id] = 'ARCHIVE_ASK_NAME'
                send_message(chat_id, "Podaj nazwę początkową (np. b235):")
            else:
                send_message(chat_id, "❌ Nie ma oczekującej archiwizacji.")
            return

        elif message_text == '/nie':
            if user_states.get(user_id) == 'ARCHIVE_DECISION':
                send_message(chat_id, f"⏳ Zapisuję {len(user_analysis_results[user_id])} zdjęć do tabeli...")
                
                for data in user_analysis_results[user_id]:
                    group_fp, group_items = find_duplicate_group(data)
                    
                    if group_fp:
                        filename = data.get('bill_number', f"receipt_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
                        add_to_receipts_database(filename, data, group_fp)
                        update_sheet_group(group_fp, receipts_database[group_fp])
                        send_message(chat_id, f"⚠️ Dodano duplikat do grupy: {filename}")
                    else:
                        filename = data.get('bill_number', f"receipt_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
                        group_fp = add_to_receipts_database(filename, data)
                        update_sheet_group(group_fp, receipts_database[group_fp])
                
                send_message(chat_id, f"✅ Zapisano {len(user_analysis_results[user_id])} wierszy w tabeli!")
                
                del user_states[user_id]
                del user_photos[user_id]
                del user_analysis_results[user_id]
            else:
                send_message(chat_id, "❌ Nie ma oczekującej archiwizacji.")
            return

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
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            receipt_data = loop.run_until_complete(analyze_image_with_cohere(filename, chat_id))
            loop.close()

            if receipt_data:
                user_analysis_results[user_id].append(receipt_data)
                user_photos[user_id].append((filename, img_data))
                send_message(chat_id, f"✅ Otrzymałem ({current_count})")
                increment_photo_count(user_id, chat_id)
            else:
                send_message(chat_id, "⚠️ Nie udało się przeanalizować zdjęcia")
                os.remove(filename)
            return

    if 'message' in update and 'text' in update['message']:
        text = update['message']['text']
        chat_id = update['message']['chat']['id']
        user_id = update['message']['from']['id']

        if user_states.get(user_id) == 'ARCHIVE_ASK_NAME':
            base_name = text.strip()
            
            send_message(chat_id, f"⏳ Tworzę archiwum ZIP dla {len(user_photos[user_id])} zdjęć...")
            
            # Wyślij informację, że proces się rozpoczął
            send_message(chat_id, "📦 Tworzenie pliku ZIP...")

            match = re.search(r'(\d+)$', base_name)
            if match:
                start_num = int(match.group(1))
                prefix = base_name[:match.start()]
                
                zip_buffer = io.BytesIO()
                file_count = 0
                
                try:
                    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                        for idx, (filename, img_data) in enumerate(user_photos[user_id]):
                            current_number = start_num + idx
                            base_filename = f"{prefix}{current_number}"
                            
                            data = user_analysis_results[user_id][idx]
                            group_fp, group_items = find_duplicate_group(data)
                            
                            if group_fp:
                                existing_filenames = [item['filename'] for item in group_items]
                                final_name = get_next_filename_in_group(existing_filenames)
                                if not final_name:
                                    final_name = f"{base_filename}.1"
                                
                                add_to_receipts_database(final_name, data, group_fp)
                                update_sheet_group(group_fp, receipts_database[group_fp])
                                send_message(chat_id, f"⚠️ <b>WYKRYTO DUPLIKAT!</b>\nGrupa: {', '.join(existing_filenames)}\nDodano: {final_name}")
                            else:
                                final_name = base_filename
                                group_fp = add_to_receipts_database(final_name, data)
                                update_sheet_group(group_fp, receipts_database[group_fp])
                            
                            arcname = f"{final_name}.jpg"
                            zip_file.writestr(arcname, img_data)
                            file_count += 1
                            
                            # Aktualizuj dane
                            user_analysis_results[user_id][idx]['bill_number'] = final_name
                    
                    send_message(chat_id, f"✅ Utworzono ZIP z {file_count} plikami")
                    
                    # Przygotuj dane do wysyłki
                    zip_buffer.seek(0)
                    zip_data = zip_buffer.getvalue()
                    
                    send_message(chat_id, f"📤 Wysyłam archiwum ZIP ({len(zip_data) // 1024} KB)...")
                    
                    # Wyślij ZIP
                    success = send_document(chat_id, zip_data, "archiwum.zip")
                    
                    if success:
                        send_message(chat_id, "✅ Archiwum ZIP wysłane pomyślnie!")
                    else:
                        send_message(chat_id, "❌ Nie udało się wysłać archiwum ZIP")
                        return
                    
                except Exception as e:
                    logging.error(f"Błąd tworzenia ZIP: {e}")
                    logging.error(traceback.format_exc())
                    send_message(chat_id, f"❌ Błąd tworzenia archiwum: {str(e)}")
                    return

                send_message(chat_id, f"📸 Wysyłam {len(user_analysis_results[user_id])} przeanalizowanych zdjęć:")
                
                for idx, (filename, img_data) in enumerate(user_photos[user_id]):
                    try:
                        with open(filename, 'rb') as f:
                            files = {'photo': (f'zdjecie_{idx+1}.jpg', f, 'image/jpeg')}
                            response = requests.post(API_URL + 'sendPhoto', data={'chat_id': chat_id}, files=files, timeout=30)
                            if response.status_code != 200:
                                logging.error(f"Błąd wysyłania zdjęcia {idx}: {response.text}")
                    except Exception as e:
                        logging.error(f"Błąd wysyłania zdjęcia {idx}: {e}")
                    
                    data = user_analysis_results[user_id][idx]
                    response_text = f"✅ Paragon rozpoznany!\n\n"
                    response_text += f"🏪 Dostawca: {data['supplier']}\n"
                    response_text += f"📅 Data: {data['date']}\n"
                    response_text += f"💰 Kwota: {data['amount']}\n"
                    response_text += f"💳 Płatność: {data['payment']}\n"
                    response_text += f"🧾 Nr paragonu: {data['bill_number']}\n"
                    response_text += f"📦 Expense: {data['expense_item']}\n"
                    response_text += f"📁 Kategoria: {data['category']}\n\n"
                    
                    send_message(chat_id, response_text)

                send_message(chat_id, f"✅ Zakończono! Wszystkie dane zostały zgrupowane w tabeli.")

                del user_states[user_id]
                
                for filename, _ in user_photos[user_id]:
                    if os.path.exists(filename):
                        os.remove(filename)
                
                del user_photos[user_id]
                del user_analysis_results[user_id]
            else:
                send_message(chat_id, "❌ Nazwa musi zawierać cyfry na końcu (np. b235)")
            return

    # Normalna obsługa pojedynczego zdjęcia
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
                group_fp, group_items = find_duplicate_group(receipt_data)
                
                if group_fp:
                    existing_filenames = [item['filename'] for item in group_items]
                    final_name = get_next_filename_in_group(existing_filenames)
                    if not final_name:
                        final_name = f"{receipt_data.get('bill_number', 'receipt')}.1"
                    
                    add_to_receipts_database(final_name, receipt_data, group_fp)
                    update_sheet_group(group_fp, receipts_database[group_fp])
                    
                    response = f"⚠️ <b>WYKRYTO DUPLIKAT!</b>\n\n"
                    response += f"📁 Grupa: {', '.join(existing_filenames)}\n"
                    response += f"➕ Dodano: {final_name}\n\n"
                    response += f"🏪 Dostawca: {receipt_data['supplier']}\n"
                    response += f"📅 Data: {receipt_data['date']}\n"
                    response += f"💰 Kwota: {receipt_data['amount']}\n"
                    response += f"💳 Płatność: {receipt_data['payment']}\n"
                    response += f"📦 Expense: {receipt_data['expense_item']}\n"
                    response += f"📁 Kategoria: {receipt_data['category']}\n\n"
                    response += "📊 Zaktualizowano grupę w Google Sheets!"
                    
                    send_message(chat_id, response)
                else:
                    final_name = receipt_data.get('bill_number', f"receipt_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
                    group_fp = add_to_receipts_database(final_name, receipt_data)
                    update_sheet_group(group_fp, receipts_database[group_fp])
                    
                    increment_photo_count(user_id, chat_id)
                    
                    response = f"✅ Nowy paragon!\n\n"
                    response += f"🏪 Dostawca: {receipt_data['supplier']}\n"
                    response += f"📅 Data: {receipt_data['date']}\n"
                    response += f"💰 Kwota: {receipt_data['amount']}\n"
                    response += f"💳 Płatność: {receipt_data['payment']}\n"
                    response += f"🧾 Nr paragonu: {final_name}\n"
                    response += f"📦 Expense: {receipt_data['expense_item']}\n"
                    response += f"📁 Kategoria: {receipt_data['category']}\n\n"
                    response += "📊 Zapisano do Google Sheets!"

                    send_message(chat_id, response)
            else:
                send_message(chat_id, "😕 Nie udało się rozpoznać paragonu")

            os.remove(filename)
            return

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
    logging.info(f"🚀 Bot z grupowaniem duplikatów wystartował na porcie {port}")
    logging.info(f"📊 Google Sheets ID: {SHEET_ID}")
    server.serve_forever()

if __name__ == "__main__":
    main()
