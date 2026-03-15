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

    file = await bot.get_file(message.photo[-1].file_id)
    await bot.download_file(file.file_path, "receipt.jpg")

    # 1. Отправляем фото
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

        await message.answer("⏳ Задача в очереди, жду результат...")

        # 2. Ждем и проверяем статус
        for _ in range(10):  # 10 попыток
            time.sleep(2)  # ждем 2 секунды

            status_r = requests.get(
                f"https://api.ocrbase.dev/v1/jobs/{job_id}",
                headers={"Authorization": f"Bearer {OCR_KEY}"}
            )

            if status_r.status_code == 200:
                job_data = status_r.json()
                status = job_data.get('status')

                if status == 'completed':
                    # Задача выполнена
                    text = job_data.get('markdownResult') or job_data.get('text', '')
                    if text:
                        await message.answer(f"✅ {text[:4000]}")
                    else:
                        await message.answer("❌ Текст не найден")
                    break
                elif status == 'failed':
                    await message.answer(f"❌ Ошибка обработки")
                    break
                elif status == 'pending' or status == 'processing':
                    await message.answer(f"⏳ Еще обрабатывается...")
            else:
                await message.answer(f"❌ Ошибка проверки статуса")
                break
        else:
            await message.answer("❌ Таймаут ожидания")
    else:
        await message.answer(f"❌ Ошибка: {r.status_code}")

    os.remove("receipt.jpg")


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())