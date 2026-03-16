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

def handle_update(update):
    logging.info("=== НОВОЕ ОБНОВЛЕНИЕ ===")
    
    if 'message' not in update or 'photo' not in update['message']:
        return

    chat_id = update['message']['chat']['id']
    send_message(chat_id, "📸 Обрабатываю...")

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

        logging.info("Sending to PaddleOCR...")
        r = requests.post(PADDLE_URL, json=payload, headers=headers, timeout=30)
        logging.info(f"PaddleOCR status: {r.status_code}")

        if r.status_code == 200:
            result = r.json()
            logging.info(f"PaddleOCR response: {json.dumps(result)[:500]}")
            
            if result.get("errorCode") == 0:
                # Извлекаем текст
                text = ""
                if "result" in result and "layoutParsingResults" in result["result"]:
                    results = result["result"]["layoutParsingResults"]
                    if results and len(results) > 0:
                        if "prunedResult" in results[0]:
                            text = results[0]["prunedResult"].get("text", "")
                        elif "markdown" in results[0]:
                            text = results[0]["markdown"].get("text", "")
                
                if text:
                    send_message(chat_id, f"✅ {text[:4000]}")
                else:
                    send_message(chat_id, "❌ Текст не найден")
            else:
                send_message(chat_id, f"❌ Ошибка PaddleOCR: {result.get('errorMsg')}")
        else:
            send_message(chat_id, f"❌ Ошибка HTTP: {r.status_code}")

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
        logging.info("GET request handled")

def main():
    port = int(os.environ.get('PORT', 10000))
    server = HTTPServer(("0.0.0.0", port), Handler)
    logging.info(f"Starting bot on port {port}")
    server.serve_forever()

if __name__ == "__main__":
    main()
