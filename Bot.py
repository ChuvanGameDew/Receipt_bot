import requests
import os
import time
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
import asyncio
import logging

# Твои данные
BOT_TOKEN = "8746910864:AAFiSK85KM_6OGsDHxEIGBm2xWkxIXWfMDc"
OCR_KEY = "sk_QRYWLB9EDt7ntMmseUq9XcHvRSjW0T7i"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer("👋 Отправь фото чека")


@dp.message(lambda m: m.photo)
async def photo(message: types.Message):
    await message.answer("📸 Обрабатываю...")

    # Скачиваем фото
    file = await bot.get_file(message.photo[-1].file_id)
    await bot.download_file(file.file_path, "receipt.jpg")

    # Отправляем фото в ocrbase
    with open("receipt.jpg", "rb") as f:
        files = {"file": ("receipt.jpg", f, "image/jpeg")}
        headers = {"Authorization": f"Bearer {OCR_KEY}"}
        
        r = requests.post(
            "https://api.ocrbase.dev/v1/parse",
            headers=headers,
            files=files,
            timeout=30
        )

    if r.status_code == 200:
        data = r.json()
        job_id = data.get('id')
        
        if not job_id:
            await message.answer("❌ Нет ID задачи")
            return

        # Отправляем сообщение о начале проверок
        status_msg = await message.answer("⏳ Проверяю статус...")
        
        # Делаем 10 проверок с интервалом 2 секунды
        for attempt in range(1, 11):
            await asyncio.sleep(2)
            
            # Обновляем сообщение о попытке
            await status_msg.edit_text(f"⏳ Проверка {attempt}/10...")
            
            # Проверяем статус
            status_r = requests.get(
                f"https://api.ocrbase.dev/v1/jobs/{job_id}",
                headers={"Authorization": f"Bearer {OCR_KEY}"}
            )
            
            if status_r.status_code == 200:
                job_data = status_r.json()
                status = job_data.get('status')
                
                if status == 'completed':
                    # Задача выполнена - получаем текст
                    text = job_data.get('markdownResult') or job_data.get('text', '')
                    if text:
                        await status_msg.edit_text(f"✅ Готово!")
                        await message.answer(f"✅ {text[:4000]}")
                    else:
                        await status_msg.edit_text(f"❌ Текст не найден")
                    break
                elif status == 'failed':
                    await status_msg.edit_text(f"❌ Ошибка обработки")
                    break
                elif attempt == 10:
                    await status_msg.edit_text(f"❌ Таймаут - задача не обработалась")
            else:
                await status_msg.edit_text(f"❌ Ошибка проверки статуса")
                break
        else:
            await status_msg.edit_text(f"❌ Таймаут ожидания")
    else:
        await message.answer(f"❌ Ошибка: {r.status_code}")

    # Удаляем временный файл
    if os.path.exists("receipt.jpg"):
        os.remove("receipt.jpg")


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
