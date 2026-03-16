import requests
import os
import json
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

BOT_TOKEN = "8746910864:AAFiSK85KM_6OGsDHxEIGBm2xWkxIXWfMDc"
OCR_KEY = "sk_QRYWLB9EDt7ntMmseUq9XcHvRSjW0T7i"
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/"

def send_message(chat_id, text):
    url = API_URL + "sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    try:
        r = requests.post(url, json=payload, timeout=10)
        logging.info(f"send_message status: {r.status_code}")
    except Exception as e:
        logging.error(f"send_message error: {e}")

def handle_update(update):
    logging.info("=== НОВОЕ ОБНОВЛЕНИЕ ===")
    logging.info(f"Update keys: {update.keys()}")
    
    if 'message' not in update:
        logging.warning("No message in update")
        return
    
    logging.info(f"Message keys: {update['message'].keys()}")
    
    if 'photo' not in update['message']:
        logging.warning("No photo in message")
        chat_id = update['message']['chat']['id']
        send_message(chat_id, "Пожалуйста, отправь фото чека.")
        return

    chat_id = update['message']['chat']['id']
    logging.info(f"Chat ID: {chat_id}")
    
    send_message(chat_id, "📸 Обрабатываю...")

    try:
        # Получаем file_id
        file_id = update['message']['photo'][-1]['file_id']
        logging.info(f"File ID: {file_id}")
        
        # Получаем информацию о файле
        file_info_url = API_URL + f"getFile?file_id={file_id}"
        logging.info(f"Getting file info from: {file_info_url}")
        
        file_info = requests.get(file_info_url, timeout=10).json()
        logging.info(f"File info response: {file_info}")
        
        if not file_info.get('ok'):
            logging.error(f"File info not OK: {file_info}")
            send_message(chat_id, "❌ Не удалось получить информацию о файле.")
            return

        # Скачиваем фото
        file_path = file_info['result']['file_path']
        file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
        logging.info(f"Downloading from: {file_url}")
        
        img_data = requests.get(file_url, timeout=30).content
        logging.info(f"Downloaded {len(img_data)} bytes")
        
        with open("receipt.jpg", "wb") as f:
            f.write(img_data)
        logging.info("File saved as receipt.jpg")

        # Отправляем в ocrbase
        logging.info("Sending to ocrbase...")
        with open("receipt.jpg", "rb") as f:
            files = {"file": ("receipt.jpg", f, "image/jpeg")}
            headers = {"Authorization": f"Bearer {OCR_KEY}"}
            
            r = requests.post(
                "https://api.ocrbase.dev/v1/parse",
                headers=headers,
                files=files,
                timeout=30
            )

        logging.info(f"ocrbase status: {r.status_code}")
        logging.info(f"ocrbase response: {r.text[:500]}")

        if r.status_code == 200:
            data = r.json()
            logging.info(f"ocrbase JSON: {data}")
            job_id = data.get('id')
            
            if not job_id:
                logging.error("No job_id in response")
                send_message(chat_id, "❌ Нет ID задачи")
                return

            logging.info(f"Job ID: {job_id}")
            send_message(chat_id, f"⏳ Job ID: {job_id}")

            # Проверяем статус
            for attempt in range(1, 11):
                time.sleep(2)
                logging.info(f"Attempt {attempt}/10")
                
                status_r = requests.get(
                    f"https://api.ocrbase.dev/v1/jobs/{job_id}",
                    headers={"Authorization": f"Bearer {OCR_KEY}"}
                )
                
                logging.info(f"Status check {attempt}: {status_r.status_code}")
                
                if status_r.status_code == 200:
                    job_data = status_r.json()
                    logging.info(f"Job data: {job_data}")
                    status = job_data.get('status')
                    
                    if status == 'completed':
                        text = job_data.get('markdownResult') or job_data.get('text', '')
                        if text:
                            send_message(chat_id, f"✅ {text[:4000]}")
                        else:
                            send_message(chat_id, f"❌ Текст не найден")
                        break
                    elif status == 'failed':
                        send_message(chat_id, f"❌ Ошибка обработки")
                        break
                else:
                    send_message(chat_id, f"❌ Ошибка проверки")
                    break
            else:
                send_message(chat_id, f"❌ Таймаут")
        else:
            send_message(chat_id, f"❌ Ошибка ocrbase: {r.status_code}")

    except Exception as e:
        logging.exception(f"ERROR: {e}")
        send_message(chat_id, f"❌ Ошибка: {str(e)[:100]}")
    finally:
        if os.path.exists("receipt.jpg"):
            os.remove("receipt.jpg")
            logging.info("Temp file removed")

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_len = int(self.headers.get('Content-Length', 0))
        post_body = self.rfile.read(content_len)
        logging.info(f"POST request received, length: {content_len}")
        try:
            update = json.loads(post_body)
            handle_update(update)
        except Exception as e:
            logging.exception(f"Error in POST handler: {e}")
        finally:
            self.send_response(200)
            self.end_headers()
            logging.info("POST request handled")

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running")
        logging.info("GET request handled")

def main():
    port = int(os.environ.get('PORT', 10000))
    server = HTTPServer(("0.0.0.0", port), Handler)
    logging.info(f"Starting bot on port {port}")
    server.serve_forever()

if __name__ == "__main__":
    main()
