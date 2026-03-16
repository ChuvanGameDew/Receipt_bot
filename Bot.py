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
SHEET_NAME = "Аркуш1"  # ZMIEŃ NA SWOJĄ NAZWĘ ARKUSZA

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
    """Formatowanie daty - czyszczenie i konwersja do formatu DD/MM"""
    if not raw_date or raw_date == "UNKNOWN":
        return "UNKNOWN"
    
    # Usuń wszystkie znaki specjalne, zostaw tylko cyfry i ukośniki
    raw_date = re.sub(r'[^\d/]', '', raw_date)
    
    # Szukaj wzorca DD/MM lub DD/MM/YYYY
    match = re.search(r'(\d{1,2})/?(\d{1,2})', raw_date)
    if match:
        day = match.group(1).zfill(2)
        month = match.group(2).zfill(2)
        return f"{day}/{month}"
    
    return "UNKNOWN"

def normalize_payment(raw):
    raw = raw.lower()
    if any(x in raw for x in ['card', 'karta', 'credit', 'debit', 'visa', 'master', 'carta', 'carte']):
        return "card"
    elif any(x in raw for x in ['cash', 'gotowka', 'gotówka', 'kontant']):
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

def save_to_sheet(data):
    logging.info("=== PRÓBA ZAPISU DO GOOGLE SHEETS ===")
    
    def clean_value(value):
        if value == "UNKNOWN" or not value:
            return ""
        return str(value).strip()
    
    try:
        sheet = get_google_sheet()
        if not sheet:
            logging.error("❌ Nie można uzyskać dostępu do arkusza")
            return False
        
        row = [
            '',
            clean_value(data.get('date', '')),
            clean_value(data.get('supplier', '')),
            clean_value(data.get('bill_number', '')),
            clean_value(data.get('payment', '')),
            clean_value(data.get('expense_item', '')),
            clean_value(data.get('category', '')),
            '',
            clean_value(data.get('amount', ''))
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
🤖 <b>Receipt Scanner Bot v4.0</b>

📸 <b>Co potrafię:</b>
• Rozpoznaję tekst z paragonów
• Klasyfikuję dostawców
• Rozróżniam metody płatności
• Zapisuję dane do Google Sheets

📋 <b>Jak używać:</b>
1. Wyślij mi zdjęcie paragonu
2. AI przeanalizuje obraz
3. Otrzymasz podsumowanie
4. Dane trafią do tabeli
"""
    send_message(chat_id, welcome_text)

# Zbiór przetworzonych już ID, żeby nie analizować wielokrotnie
processed_updates = set()

def handle_update(update):
    global processed_updates
    
    logging.info("=== NOWA WIADOMOŚĆ ===")
    
    # Zapobieganie wielokrotnemu przetwarzaniu
    update_id = update.get('update_id')
    if update_id in processed_updates:
        logging.info(f"Pominięto już przetworzone update_id: {update_id}")
        return
    processed_updates.add(update_id)
    
    # Ograniczenie wielkości zbioru
    if len(processed_updates) > 100:
        processed_updates = set(list(processed_updates)[-50:])
    
    # Obsługa komendy /start
    if 'message' in update and 'text' in update['message']:
        if update['message']['text'] == '/start':
            chat_id = update['message']['chat']['id']
            send_message(chat_id, "👋 Bot wystartował! Wyślij zdjęcie paragonu.")
            return
    
    # Sprawdzenie czy to zdjęcie
    if 'message' not in update or 'photo' not in update['message']:
        return

    chat_id = update['message']['chat']['id']
    send_message(chat_id, "🔍 Analizuję paragon...")

    try:
        # Pobranie i zapis zdjęcia
        file_id = update['message']['photo'][-1]['file_id']
        file_info = requests.get(API_URL + f"getFile?file_id={file_id}", timeout=10).json()
        file_path = file_info['result']['file_path']
        file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
        
        img_data = requests.get(file_url, timeout=30).content
        with open("receipt.jpg", "wb") as f:
            f.write(img_data)
        logging.info(f"📸 Pobrano zdjęcie: {len(img_data)} bajtów")

        # Kodowanie do base64
        with open("receipt.jpg", "rb") as f:
            file_data = base64.b64encode(f.read()).decode("utf-8")

        # Wysłanie do PaddleOCR
        headers = {
            "Authorization": f"token {PADDLE_TOKEN}",
            "Content-Type": "application/json"
        }
        
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
                        # Zbieranie tekstu z odpowiedzi
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
                            
                            # ===== WYODRĘBNIANIE DANYCH =====
                            supplier = find_supplier(full_text)
                            
                            # ===== SZUKANIE DATY =====
                            date = "UNKNOWN"
                            
                            # Najpierw szukaj w całym tekście wzorca daty
                            date_match = re.search(r'(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})', full_text)
                            if date_match:
                                day = date_match.group(1).zfill(2)
                                month = date_match.group(2).zfill(2)
                                date = f"{day}/{month}"
                                logging.info(f"Znaleziono datę: {date}")
                            
                            # ===== SZUKANIE KWOTY - ULEPSZONE =====
                            amount = "UNKNOWN"
                            best_candidates = []
                            
                            # Przejdź przez wszystkie linie
                            for line in all_text:
                                line_lower = line.lower()
                                
                                # Sprawdź czy linia zawiera słowa kluczowe dla kwoty całkowitej
                                total_keywords = ['total', 'bill amount', 'paid amount', 'amount', 'razem', 'suma', 'kwota', 'tot', 'subtotal', 'invoice', 'grand total']
                                is_total_line = any(keyword in line_lower for keyword in total_keywords)
                                
                                # Znajdź wszystkie kwoty w linii
                                numbers = re.findall(r'(\d+[.,]\d{2})', line)
                                
                                for num in numbers:
                                    try:
                                        # Konwertuj na float dla porównania
                                        val = float(num.replace(',', '.'))
                                        
                                        # Zapisz kandydata z informacją o wadze
                                        weight = 0
                                        
                                        # Linia z TOTAL ma najwyższy priorytet
                                        if is_total_line:
                                            weight += 100
                                        
                                        # Linia z ceną całkowitą często ma wyższą wagę
                                        if val > 10:
                                            weight += 10
                                        if val > 50:
                                            weight += 20
                                        if val > 100:
                                            weight += 30
                                        
                                        # Unikaj podejrzanie małych kwot (chyba że to TOTAL)
                                        if val < 1 and not is_total_line:
                                            weight -= 50
                                        
                                        # Sprawdź czy to może być kwota z podatkiem
                                        if 'vat' in line_lower or 'tax' in line_lower:
                                            if 'total' in line_lower or 'amount' in line_lower:
                                                weight += 50
                                        
                                        best_candidates.append((weight, val, num))
                                    except:
                                        pass
                            
                            # Wybierz najlepszego kandydata (najwyższa waga)
                            if best_candidates:
                                best_candidates.sort(reverse=True)
                                amount = clean_amount(best_candidates[0][2])
                                logging.info(f"Wybrano kwotę: {amount} (waga: {best_candidates[0][0]})")
                            
                            # Jeśli nie znaleziono, szukaj wszystkich liczb i weź największą
                            if amount == "UNKNOWN":
                                all_numbers = []
                                for line in all_text:
                                    numbers = re.findall(r'(\d+[.,]\d{2})', line)
                                    for num in numbers:
                                        try:
                                            val = float(num.replace(',', '.'))
                                            all_numbers.append((val, num))
                                        except:
                                            pass
                                
                                if all_numbers:
                                    all_numbers.sort(reverse=True)
                                    amount = clean_amount(all_numbers[0][1])
                                    logging.info(f"Znaleziono kwotę (największa): {amount}")
                            
                            # ===== SZUKANIE PŁATNOŚCI =====
                            payment = "UNKNOWN"
                            payment_text = ' '.join(all_text).lower()
                            
                            card_keywords = ['card', 'credit', 'debit', 'visa', 'mastercard', 'karta']
                            cash_keywords = ['cash', 'gotówka', 'gotowka', 'kontant']
                            
                            if any(kw in payment_text for kw in card_keywords):
                                payment = "card"
                            elif any(kw in payment_text for kw in cash_keywords):
                                payment = "cash"
                            
                            # 🔥 NUMER PARAGONU = NAZWA PLIKU
                            bill_number = os.path.splitext(os.path.basename(file_path))[0]
                            
                            # Klasyfikacja
                            expense_item, category = classify_receipt(supplier, amount, products_text_full)
                            
                            # ===== PRZYGOTOWANIE DANYCH =====
                            receipt_data = {
                                'supplier': supplier,
                                'date': date,
                                'amount': amount,
                                'payment': payment,
                                'bill_number': bill_number,
                                'expense_item': expense_item,
                                'category': category
                            }
                            
                            # ===== ZAPIS DO GOOGLE SHEETS =====
                            saved = save_to_sheet(receipt_data)
                            
                            # ===== ODPOWIEDŹ DLA UŻYTKOWNIKA =====
                            response = f"✅ Paragon rozpoznany!\n\n"
                            response += f"🏪 Dostawca: {supplier}\n"
                            response += f"📅 Data: {date}\n"
                            response += f"💰 Kwota: {amount}\n"
                            response += f"💳 Płatność: {payment}\n"
                            response += f"🧾 Nr paragonu: {bill_number}\n"
                            response += f"📦 Expense: {expense_item}\n"
                            response += f"📁 Kategoria: {category}\n\n"
                            
                            if saved:
                                response += "📊 Zapisano do Google Sheets!"
                            else:
                                response += "⚠️ Nie udało się zapisać do Sheets"
                            
                            send_message(chat_id, response)
                            logging.info(f"✅ Rozpoznano: {supplier}, {date}, {amount}, nr: {bill_number}")
                            
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
