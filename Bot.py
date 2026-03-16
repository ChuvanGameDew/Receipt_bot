import requests
import os
import json
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
import logging
import base64

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

BOT_TOKEN = "8746910864:AAFiSK85KM_6OGsDHxEIGBm2xWkxIXWfMDc"
PADDLE_TOKEN = "e4ade03b3e21505f809528f4f3c74eb31097c93a"
PADDLE_URL = "https://i8w753gcm0e7e7y0.aistudio-app.com/layout-parsing"
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/"

def send_message(chat_id, text):
    url = API_URL + "sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    try:
        r = requests.post(url, json=payload, timeout=10)
        logging.info(f"send_message status: {r.status_code}")
    except Exception as e:
        logging.error(f"send_message error: {e}")

def handle_start(chat_id):
    """Красивое приветствие"""
    welcome_text = """
🤖 <b>Receipt Scanner Bot</b>

Привет! Я бот для распознавания чеков. 
Просто отправь мне фото чека, и я извлеку из него текст.

📸 <b>Как пользоваться:</b>
1. Нажми на скрепку 📎
2. Выбери фото чека
3. Отправь мне
4. Получи результат

⚡️ <i>Работает 24/7 на сервере</i>
"""
    send_message(chat_id, welcome_text)

def handle_update(update):
    logging.info("=== НОВОЕ ОБНОВЛЕНИЕ ===")
    
    # Обработка команды /start
    if 'message' in update and 'text' in update['message']:
        if update['message']['text'] == '/start':
            chat_id = update['message']['chat']['id']
            handle_start(chat_id)
            return
    
    # Проверка на фото
    if 'message' not in update or 'photo' not in update['message']:
        chat_id = update['message']['chat']['id']
        send_message(chat_id, "❌ Пожалуйста, отправь фото чека.")
        return

    chat_id = update['message']['chat']['id']
    send_message(chat_id, "🔍 Обрабатываю фото...")

    try:
        # Получаем file_id и скачиваем фото
        file_id = update['message']['photo'][-1]['file_id']
        file_info = requests.get(API_URL + f"getFile?file_id={file_id}", timeout=10).json()
        file_path = file_info['result']['file_path']
        file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
        
        img_data = requests.get(file_url, timeout=30).content
        with open("receipt.jpg", "wb") as f:
            f.write(img_data)
        logging.info(f"Downloaded {len(img_data)} bytes")

        # Кодируем в base64
        with open("receipt.jpg", "rb") as f:
            file_data = base64.b64encode(f.read()).decode("utf-8")

        # Отправляем в PaddleOCR
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
                logging.info(f"Attempt {attempt + 1}/{max_retries} to PaddleOCR...")
                r = requests.post(PADDLE_URL, json=payload, headers=headers, timeout=60)
                
                if r.status_code == 200:
                    result = r.json()
                    
                    if result.get("errorCode") == 0:
                        # Собираем ТОЛЬКО текст из блоков
                        text_parts = []
                        if "result" in result and "layoutParsingResults" in result["result"]:
                            for res in result["result"]["layoutParsingResults"]:
                                if "prunedResult" in res and "parsing_res_list" in res["prunedResult"]:
                                    for block in res["prunedResult"]["parsing_res_list"]:
                                        if block.get("block_label") == "text" and block.get("block_content"):
                                            text_parts.append(block["block_content"])
                        
                        if text_parts:
                            # Объединяем текст с переносами строк
                            full_text = "\n".join(text_parts)
                            send_message(chat_id, f"📄 <b>Текст с чека:</b>\n\n{full_text}")
                        else:
                            send_message(chat_id, "😕 Не удалось найти текст на фото")
                    else:
                        send_message(chat_id, f"⚠️ Ошибка распознавания: {result.get('errorMsg')}")
                    break
                    
                elif r.status_code == 500 and attempt < max_retries - 1:
                    time.sleep(3)
                    continue
                else:
                    send_message(chat_id, f"⚠️ Ошибка сервера: {r.status_code}")
                    break
                    
            except requests.exceptions.Timeout:
                if attempt < max_retries - 1:
                    time.sleep(5)
                    continue
                else:
                    send_message(chat_id, "⏱ Таймаут. Попробуй позже.")
            except Exception as e:
                logging.exception(f"Exception: {e}")
                if attempt == max_retries - 1:
                    send_message(chat_id, f"⚠️ Ошибка: {str(e)[:100]}")

    except Exception as e:
        logging.exception(f"ERROR: {e}")
        send_message(chat_id, f"⚠️ Ошибка: {str(e)[:100]}")
    finally:
        if os.path.exists("receipt.jpg"):
            os.remove("receipt.jpg")
            logging.info("Temp file removed")

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_len = int(self.headers.get('Content-Length', 0))
        post_body = self.rfile.read(content_len)
        try:
            update = json.loads(post_body)
            handle_update(update)
        except Exception as e:
            logging.exception(f"Error in POST handler: {e}")
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
    logging.info(f"🚀 Bot started on port {port}")
    server.serve_forever()

if __name__ == "__main__":
    main()
