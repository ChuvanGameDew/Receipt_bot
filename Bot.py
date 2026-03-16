import requests
import os
import json
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Твои данные
BOT_TOKEN = "8746910864:AAFiSK85KM_6OGsDHxEIGBm2xWkxIXWfMDc"
OCR_KEY = "sk_QRYWLB9EDt7ntMmseUq9XcHvRSjW0T7i"
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/"

def send_message(chat_id, text):
    """Отправляет сообщение в Telegram"""
    url = API_URL + "sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code != 200:
            logging.error(f"Failed to send message: {r.status_code} - {r.text}")
        else:
            logging.info(f"Message sent to {chat_id}")
    except Exception as e:
        logging.error(f"Exception while sending message: {e}")

def handle_update(update):
    """Обрабатывает входящее обновление от Telegram"""
    logging.info(f"Received update: {json.dumps(update)[:200]}...")

    # Проверяем, что есть фото
    if 'message' not in update:
        return
    if 'photo' not in update['message']:
        chat_id = update['message']['chat']['id']
        send_message(chat_id, "Пожалуйста, отправь фото чека.")
        return

    chat_id = update['message']['chat']['id']
    send_message(chat_id, "📸 Обрабатываю...")

    try:
        # Получаем информацию о файле
        file_id = update['message']['photo'][-1]['file_id']
        file_info = requests.get(API_URL + f"getFile?file_id={file_id}", timeout=10).json()
        
        if not file_info.get('ok'):
            logging.error(f"Failed to get file info: {file_info}")
            send_message(chat_id, "❌ Не удалось получить информацию о файле.")
            return

        # Скачиваем фото
        file_path = file_info['result']['file_path']
        file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
        
        img_data = requests.get(file_url, timeout=30).content
        with open("receipt.jpg", "wb") as f:
            f.write(img_data)
        logging.info(f"File downloaded, size: {len(img_data)} bytes")

        # Отправляем в ocrbase
        with open("receipt.jpg", "rb") as f:
            files = {"file": ("receipt.jpg", f, "image/jpeg")}
            headers = {"Authorization": f"Bearer {OCR_KEY}"}
            
            r = requests.post(
                "https://api.ocrbase.dev/v1/parse",
                headers=headers,
                files=files,
                timeout=30
            )

        logging.info(f"ocrbase response status: {r.status_code}")

        if r.status_code == 200:
            data = r.json()
            job_id = data.get('id')
            
            if not job_id:
                send_message(chat_id, "❌ Нет ID задачи")
                return

            # Отправляем сообщение о начале проверок
            status_msg = "⏳ Проверяю статус..."
            send_message(chat_id, status_msg)
            
            # Делаем 10 проверок с интервалом 2 секунды
            for attempt in range(1, 11):
                time.sleep(2)
                
                # Обновляем сообщение о попытке (отправляем новое)
                send_message(chat_id, f"⏳ Проверка {attempt}/10...")
                
                # Проверяем статус
                status_r = requests.get(
                    f"https://api.ocrbase.dev/v1/jobs/{job_id}",
                    headers={"Authorization": f"Bearer {OCR_KEY}"}
                )
                
                if status_r.status_code == 200:
                    job_data = status_r.json()
                    status = job_data.get('status')
                    
                    if status == 'completed':
                        text = job_data.get('markdownResult') or job_data.get('text', '')
                        if text:
                            send_message(chat_id, f"✅ Готово!")
                            send_message(chat_id, f"✅ {text[:4000]}")
                        else:
                            send_message(chat_id, f"❌ Текст не найден")
                        break
                    elif status == 'failed':
                        send_message(chat_id, f"❌ Ошибка обработки")
                        break
                    elif attempt == 10:
                        send_message(chat_id, f"❌ Таймаут - задача не обработалась")
                else:
                    send_message(chat_id, f"❌ Ошибка проверки статуса")
                    break
            else:
                send_message(chat_id, f"❌ Таймаут ожидания")
        else:
            send_message(chat_id, f"❌ Ошибка ocrbase: {r.status_code}")

    except Exception as e:
        logging.exception(f"Error: {e}")
        send_message(chat_id, f"❌ Ошибка: {str(e)[:100]}")
    finally:
        if os.path.exists("receipt.jpg"):
            os.remove("receipt.jpg")

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_len = int(self.headers.get('Content-Length', 0))
        post_body = self.rfile.read(content_len)
        try:
            update = json.loads(post_body)
            handle_update(update)
        except Exception as e:
            logging.exception("Error in POST handler")
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
    logging.info(f"Starting bot on port {port}")
    server.serve_forever()

if __name__ == "__main__":
    main()
