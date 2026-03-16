import requests
import os
import json
import time
import re
import gspread
from google.oauth2.service_account import Credentials
from http.server import HTTPServer, BaseHTTPRequestHandler
import logging
import base64
from datetime import datetime

# ==================== KONFIGURACJA LOGOWANIA ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    force=True
)

# ==================== KONFIGURACJA ====================
BOT_TOKEN = "8746910864:AAFiSK85KM_6OGsDHxEIGBm2xWkxIXWfMDc"
PADDLE_TOKEN = "e4ade03b3e21505f809528f4f3c74eb31097c93a"
PADDLE_URL = "https://i8w753gcm0e7e7y0.aistudio-app.com/layout-parsing"
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/"

# ==================== GOOGLE SHEETS ====================
SHEET_ID = "1SHUyo_5sJYsQPiIIR9nCkAeJI2ZB5KQFx-1g0jXKaRw"
SHEET_NAME = "Аркуш1"  # !!! ZMIEŃ NA SWOJĄ NAZWĘ ARKUSZA (sprawdź na dole tabeli) !!!

# ==================== SŁOWNIKI (z Twojego kodu Unity) ====================
known_suppliers = {
    # Supermarkety i sklepy spożywcze
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
    
    # Dostawcy dla restauracji
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
    
    # Opakowania
    "hotpack": "Hotpack Packaging L.L.C",
    "falconpack": "Falconpack Investory LLC",
    "falcon": "Falconpack Investory LLC",
    "fallonpack": "FALLONPACK INDUSTRY",
    
    # Stacje paliw
    "adnoc": "ADNOC",
    "enoc": "ENOC",
    "emarat": "Emarat",
    "brothers gas": "Brothers Gas",
    "eppco": "EPPCO",
    
    # Inne
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
    # ingredients
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
    
    # packaging
    "hotpack": "packaging",
    "falconpack": "packaging",
    "falcon": "packaging",
    "fallonpack": "packaging",
    
    # fuel stations
    "adnoc": "fuel",
    "enoc": "fuel",
    "emarat": "fuel",
    "brothers gas": "gas",
    "eppco": "fuel",
    
    # salary
    "al ansari": "salary",
    "ansari": "salary",
    
    # maintenance
    "sudhi": "maintenance",
    "al ershad": "maintenance",
    "al mumtaz": "maintenance",
    "fahen": "maintenance",
    
    # others
    "foodics": "others",
    "drc": "others",
    "value bag": "others",
    "harf": "others",
    "ruads": "others"
}

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
    """Formatowanie daty z paragonu (z kodu Unity)"""
    raw_date = raw_date.strip()
    
    # Popraw błędne formaty (np. 19/20 na 19/02)
    if raw_date.contains("/20") and len(raw_date) == 5:
        return raw_date.replace("/20", "/02")
    if raw_date.contains("/19") and len(raw_date) == 5:
        return raw_date.replace("/19", "/01")
    
    match = re.search(r'(\d{4})-(\d{2})-(\d{2})|(\d{2})[\.\/-](\d{2})[\.\/-](\d{4})|(\d{2})[\.\/-](\d{2})', raw_date)
    
    if match:
        if match.group(1):
            return f"{match.group(3)}/{match.group(2)}"
        elif match.group(4):
            return f"{match.group(4)}/{match.group(5)}"
        elif match.group(7):
            return f"{match.group(7)}/{match.group(8)}"
    return "UNKNOWN"

def normalize_payment(raw):
    """Normalizacja metody płatności (z kodu Unity)"""
    raw = raw.lower()
    if any(x in raw for x in ['card', 'karta', 'credit', 'debit', 'visa', 'master', 'carta', 'carte']):
        return "card"
    elif any(x in raw for x in ['cash', 'gotowka', 'gotówka', 'kontant']):
        return "cash"
    return "UNKNOWN"

def clean_amount(raw_amount):
    """Czyszczenie kwoty (z kodu Unity)"""
    cleaned = re.sub(r'[^\d.,]', '', raw_amount)
    cleaned = cleaned.replace('.', ',')
    if cleaned.count(',') > 1:
        cleaned = cleaned.replace(',', '')
        if len(cleaned) > 2:
            cleaned = cleaned[:-2] + ',' + cleaned[-2:]
    return cleaned

def find_supplier(text):
    """Znajdź dostawcę w tekście (z kodu Unity)"""
    text_lower = text.lower()
    for key, value in known_suppliers.items():
        if key in text_lower:
            return value
    return "UNKNOWN"

def classify_receipt(supplier, amount_str, products=""):
    """Klasyfikacja paragonu (dokładna kopia z Unity)"""
    supplier_lower = supplier.lower()
    
    # Al Ansari Exchange - salary
    if 'ansari' in supplier_lower:
        return "salary", "salary"
    
    # Brothers Gas - gas
    if 'brothers gas' in supplier_lower:
        return "gas", "utilities"
    
    # Stacje paliw
    if any(x in supplier_lower for x in ['adnoc', 'enoc', 'emarat', 'eppco']):
        try:
            amount = float(amount_str.replace(',', '.'))
            expense = "bike fuel" if amount < 40 else "car fuel"
            return expense, "others"
        except:
            return "car fuel", "others"
    
    # Dostawcy opakowań
    if any(x in supplier_lower for x in ['hotpack', 'falconpack', 'falcon', 'pack']):
        return "packaging", "packaging"
    
    # Warsztaty
    if any(x in supplier_lower for x in ['sudhi', 'al ershad', 'al mumtaz', 'fahen']):
        if 'oil' in products.lower():
            return "bike oil", "others"
        return "maintenance", "maintenance"
    
    # Kategoria z słownika
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
    
    # Domyślnie
    return "ingredients", "ingredients"

def extract_bill_number(text):
    """Wyodrębnij numer paragonu"""
    patterns = [
        r'order[:\s]*([a-zA-Z0-9\-_]+)',
        r'bill[:\s]*([a-zA-Z0-9\-_]+)',
        r'invoice[:\s]*([a-zA-Z0-9\-_]+)',
        r'no[.:\s]*([a-zA-Z0-9\-_]+)',
        r'#\s*([a-zA-Z0-9\-_]+)'
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return "UNKNOWN"

# ==================== FUNKCJE GOOGLE SHEETS ====================
def get_google_sheet():
    """Połączenie z Google Sheets z pełnym logowaniem"""
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

def save_to_sheet(data):
    """Zapis danych do Google Sheets (dokładnie tak, jak w Twojej tabeli)"""
    logging.info("=== PRÓBA ZAPISU DO GOOGLE SHEETS ===")
    
    try:
        sheet = get_google_sheet()
        if not sheet:
            logging.error("❌ Nie można uzyskać dostępu do arkusza")
            return False
        
        # KOLEJNOŚĆ KOLUMN w Twojej tabeli:
        # B: data | C: dostawca | D: numer paragonu | E: płatność | F: expense item | G: kategoria | H: puste | I: kwota
        row = [
            data.get('date', ''),           # Kolumna B
            data.get('supplier', ''),        # Kolumna C
            data.get('bill_number', ''),     # Kolumna D
            data.get('payment', ''),         # Kolumna E
            data.get('expense_item', ''),    # Kolumna F
            data.get('category', ''),        # Kolumna G
            '',                               # Kolumna H (pusta)
            data.get('amount', '')            # Kolumna I
        ]
        
        logging.info(f"   Próba zapisu wiersza: {row}")
        sheet.append_row(row)
        logging.info(f"✅ Zapisano do Google Sheets")
        return True
        
    except Exception as e:
        logging.error(f"❌ Błąd zapisu: {str(e)}")
        return False

# ==================== GŁÓWNA LOGIKA BOTA ====================
def handle_start(chat_id):
    welcome_text = """
🤖 <b>Receipt Scanner Bot v3.0</b>

📸 <b>Co potrafię:</b>
• Rozpoznaję tekst z paragonów
• Klasyfikuję dostawców (jak w twoim kodzie Unity)
• Rozróżniam metody płatności
• Zapisuję dane do Google Sheets (dokładnie w twoich kolumnach)

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
        if update['message']['text'] == '/start':
            handle_start(update['message']['chat']['id'])
            return
    
    if 'message' not in update or 'photo' not in update['message']:
        return

    chat_id = update['message']['chat']['id']
    send_message(chat_id, "🔍 <b>Analizuję paragon...</b>")

    try:
        file_id = update['message']['photo'][-1]['file_id']
        file_info = requests.get(API_URL + f"getFile?file_id={file_id}", timeout=10).json()
        file_path = file_info['result']['file_path']
        file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
        
        img_data = requests.get(file_url, timeout=30).content
        with open("receipt.jpg", "wb") as f:
            f.write(img_data)
        logging.info(f"📸 Pobrano zdjęcie: {len(img_data)} bajtów")

        with open("receipt.jpg", "rb") as f:
            file_data = base64.b64encode(f.read()).decode("utf-8")

        headers = {"Authorization": f"token {PADDLE_TOKEN}", "Content-Type": "application/json"}
        payload = {
            "file": file_data,
            "fileType": 1,
            "useDocOrientationClassify": False,
            "useDocUnwarping": False,
            "useChartRecognition": False,
        }

        max_retries = 3
        for attempt in range(max_retries):
            try:
                logging.info(f"📤 Próba {attempt + 1}/{max_retries} do PaddleOCR...")
                r = requests.post(PADDLE_URL, json=payload, headers=headers, timeout=60)
                
                if r.status_code == 200:
                    result = r.json()
                    
                    if result.get("errorCode") == 0:
                        all_text = []
                        products_text = []
                        
                        if "result" in result and "layoutParsingResults" in result["result"]:
                            for res in result["result"]["layoutParsingResults"]:
                                if "prunedResult" in res and "parsing_res_list" in res["prunedResult"]:
                                    for block in res["prunedResult"]["parsing_res_list"]:
                                        if block.get("block_label") == "text" and block.get("block_content"):
                                            content = block["block_content"]
                                            all_text.append(content)
                                            if re.search(r'\d+[.,]\d+', content):
                                                products_text.append(content)
                        
                        if all_text:
                            full_text = "\n".join(all_text)
                            products_text_full = "\n".join(products_text)
                            
                            supplier = find_supplier(full_text)
                            date = "UNKNOWN"
                            amount = "UNKNOWN"
                            payment = "UNKNOWN"
                            
                            date_match = re.search(r'(\d{2}[./-]\d{2}[./-]\d{4}|\d{2}[./-]\d{2}[./-]\d{2})', full_text)
                            if date_match:
                                date = format_date(date_match.group(1))
                            
                            amount_matches = re.findall(r'(\d+[.,]\d{2})\s*(?:aed|total|suma|kwota|amount)', full_text.lower())
                            if amount_matches:
                                amount = clean_amount(amount_matches[-1])
                            else:
                                all_amounts = re.findall(r'(\d+[.,]\d{2})', full_text)
                                if all_amounts:
                                    amount = clean_amount(all_amounts[-1])
                            
                            if re.search(r'card|credit|debit|visa|master', full_text, re.IGNORECASE):
                                payment = "card"
                            elif re.search(r'cash|kontant', full_text, re.IGNORECASE):
                                payment = "cash"
                            
                            bill_number = extract_bill_number(full_text)
                            if bill_number == "UNKNOWN":
                                bill_number = os.path.splitext(os.path.basename(file_path))[0]
                            
                            expense_item, category = classify_receipt(supplier, amount, products_text_full)
                            
                            receipt_data = {
                                'supplier': supplier,
                                'date': date,
                                'amount': amount,
                                'payment': payment,
                                'bill_number': bill_number,
                                'expense_item': expense_item,
                                'category': category
                            }
                            
                            saved = save_to_sheet(receipt_data)
                            
                            response = f"✅ <b>Paragon rozpoznany!</b>\n\n"
                            response += f"🏪 <b>Dostawca:</b> {supplier}\n"
                            response += f"📅 <b>Data:</b> {date}\n"
                            response += f"💰 <b>Kwota:</b> {amount}\n"
                            response += f"💳 <b>Płatność:</b> {payment}\n"
                            response += f"🧾 <b>Nr paragonu:</b> {bill_number}\n"
                            response += f"📦 <b>Expense:</b> {expense_item}\n"
                            response += f"📁 <b>Kategoria:</b> {category}\n\n"
                            
                            if saved:
                                response += "📊 <b>✅ Zapisano do Google Sheets!</b>"
                            else:
                                response += "⚠️ <b>Nie udało się zapisać do Sheets</b>"
                            
                            send_message(chat_id, response)
                            logging.info(f"✅ Rozpoznano: {supplier}, {date}, {amount}")
                        else:
                            send_message(chat_id, "😕 Nie znaleziono tekstu na paragonie")
                    else:
                        send_message(chat_id, f"⚠️ Błąd OCR: {result.get('errorMsg')}")
                    break
                    
                elif r.status_code == 500 and attempt < max_retries - 1:
                    time.sleep(3)
                    continue
                else:
                    send_message(chat_id, f"⚠️ Błąd serwera: {r.status_code}")
                    break
                    
            except requests.exceptions.Timeout:
                if attempt < max_retries - 1:
                    time.sleep(5)
                    continue
                else:
                    send_message(chat_id, "⏱ Timeout. Spróbuj później.")
            except Exception as e:
                logging.exception(f"Błąd: {e}")
                if attempt == max_retries - 1:
                    send_message(chat_id, f"⚠️ Błąd: {str(e)[:100]}")

    except Exception as e:
        logging.exception(f"Błąd główny: {e}")
        send_message(chat_id, f"⚠️ Błąd: {str(e)[:100]}")
    finally:
        if os.path.exists("receipt.jpg"):
            os.remove("receipt.jpg")
            logging.info("🧹 Usunięto plik tymczasowy")

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
    logging.info(f"🚀 Bot wystartował na porcie {port}")
    logging.info(f"📊 Google Sheets ID: {SHEET_ID}")
    server.serve_forever()

if __name__ == "__main__":
    main()
