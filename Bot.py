import requests
import os
import json
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
        if r.status_code != 200:
            logging.error(f"Failed to send message: {r.status_code}")
    except Exception as e:
        logging.error(f"Exception while sending message: {e}")

def handle_update(update):
    logging.info(f"Received update")

    if 'message' not in update:
        return
    if 'photo' not in update['message']:
        chat_id = update['message']['chat']['id']
        send_message(chat_id, "Пожалуйста, отправь фото чека.")
        return

    chat_id = update['message']['chat']['id']
    send_message(chat_id, "📸 Обрабатываю...")

    try:
        file_id = update['message']['photo'][-1]['file_id']
        file_info = requests.get(API_URL + f"getFile?file_id={file_id}", timeout=10).json()
        file_path = file_info['result']['file_path']
        file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"

        img_data = requests.get(file_url, timeout=30).content
        with open("receipt.jpg", "wb") as f:
            f.write(img_data)

        with open("receipt.jpg", "rb") as f:
            r = requests.post(
                "https://api.ocrbase.dev/v1/parse",
                headers={"Authorization": f"Bearer {OCR_KEY}"},
                files={"file": f},
                timeout=60
            )

        if r.status_code == 200:
            data = r.json()
            # Отправляем ВЕСЬ ответ, чтобы увидеть структуру
            send_message(chat_id, f"✅ Ответ OCR:\n{json.dumps(data, indent=2, ensure_ascii=False)[:4000]}")
        else:
            send_message(chat_id, f"❌ Ошибка OCR API: {r.status_code}")
            logging.error(f"ocrbase error: {r.text}")

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
