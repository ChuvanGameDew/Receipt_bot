import requests
import os
import time
import json
from http.server import HTTPServer, BaseHTTPRequestHandler

BOT_TOKEN = "8746910864:AAFiSK85KM_6OGsDHxEIGBm2xWkxIXWfMDc"
OCR_KEY = "sk_QRYWLB9EDt7ntMmseUq9XcHvRSjW0T7i"
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/"

def send_message(chat_id, text):
    requests.post(API_URL + "sendMessage", json={"chat_id": chat_id, "text": text})

def handle_update(update):
    if 'message' not in update or 'photo' not in update['message']:
        return
    chat_id = update['message']['chat']['id']
    send_message(chat_id, "📸 Обрабатываю...")

    file_id = update['message']['photo'][-1]['file_id']
    file_info = requests.get(API_URL + f"getFile?file_id={file_id}").json()
    file_path = file_info['result']['file_path']
    file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"

    # Скачиваем фото
    img_data = requests.get(file_url).content
    with open("receipt.jpg", "wb") as f:
        f.write(img_data)

    # Отправляем в ocrbase
    with open("receipt.jpg", "rb") as f:
        r = requests.post(
            "https://api.ocrbase.dev/v1/parse",
            headers={"Authorization": f"Bearer {OCR_KEY}"},
            files={"file": f}
        )

    if r.status_code == 200:
        data = r.json()
        text = data.get('text', '')
        if text:
            send_message(chat_id, f"✅ {text[:4000]}")
        else:
            send_message(chat_id, "❌ Текст не найден")
    else:
        send_message(chat_id, f"❌ Ошибка: {r.status_code}")

    os.remove("receipt.jpg")

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_len = int(self.headers.get('Content-Length', 0))
        post_body = self.rfile.read(content_len)
        update = json.loads(post_body)
        handle_update(update)
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running")

def main():
    port = int(os.environ.get('PORT', 10000))
    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"Starting bot on port {port}")
    server.serve_forever()

if __name__ == "__main__":
    main()
