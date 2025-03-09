import asyncio
import aiohttp
import re
from datetime import datetime, timezone
from telegram import Bot
from dotenv import load_dotenv
import os

# Загружаем переменные окружения из файла .env
load_dotenv()

# Конфигурация из переменных окружения
WALLET_ADDRESS = os.getenv("WALLET_ADDRESS")
TONAPI_TRANSACTIONS_URL = f"https://tonapi.io/v2/blockchain/accounts/{WALLET_ADDRESS}/transactions"
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")

# Глобальная переменная для хранения последней обработанной транзакции
last_processed_tx_hash = None

async def fetch_transactions():
    """
    Запрашивает последние транзакции для указанного кошелька.
    """
    async with aiohttp.ClientSession() as session:
        async with session.get(TONAPI_TRANSACTIONS_URL) as response:
            if response.status == 200:
                return await response.json()
            else:
                print(f"Failed to fetch transactions: {response.status}")
                return None

async def process_transactions(transactions, bot):
    """
    Обрабатывает список транзакций и отправляет новые в Telegram-канал.
    """
    global last_processed_tx_hash

    if not transactions:
        print("No transactions data received.")
        return

    # Берем только последнюю транзакцию
    latest_transaction = transactions.get("transactions", [])[0] if transactions.get("transactions") else None

    if not latest_transaction:
        print("No transactions found in the response.")
        return

    tx_hash = latest_transaction.get("hash")

    # Если это уже обработанная транзакция, пропускаем
    if tx_hash == last_processed_tx_hash:
        print("No new transactions found.")
        return

    # Проверяем наличие обязательных полей
    if not all(key in latest_transaction for key in ["utime", "in_msg"]):
        print("Transaction is missing required fields:", latest_transaction)
        return

    # Дата транзакции
    utime = latest_transaction["utime"]
    transaction_date = datetime.fromtimestamp(utime, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    # Извлекаем данные из in_msg
    in_msg = latest_transaction["in_msg"]
    decoded_body = in_msg.get("decoded_body", {})
    payload = decoded_body.get("payload", [])

    if not payload:
        print(f"Transaction {tx_hash} has no payload.")
        return

    # Обрабатываем каждое сообщение в payload
    for msg in payload:
        message = msg.get("message", {})
        message_internal = message.get("message_internal", {})
        body = message_internal.get("body", {})
        body_value = body.get("value", {})
        text = body_value.get("value", {}).get("text", "")

        # Проверяем, содержит ли текст "telegram stars"
        if "telegram stars" in text.lower():
            # Используем регулярное выражение для извлечения числа перед "Telegram Stars"
            match = re.search(r"(\d+)\s*Telegram Stars", text)
            if match:
                stars_amount = int(match.group(1))  # Извлекаем число из найденного совпадения
            else:
                print(f"Could not extract stars amount from text: {text}")
                continue

            # Извлекаем количество TON
            ton_amount = int(message_internal.get("value", {}).get("grams", 0)) / 1e9  # Переводим наноТОН в TON

            message_text = (
                f"<b>Ruslan</b> @zolotov bought <b>⭐️{stars_amount} stars</b> for <code>{ton_amount:.4f} TON</code>\n"
                f"— <i>{transaction_date}</i>\n"
            )

            # Отправляем сообщение в Telegram-канал
            await bot.send_message(
                chat_id=TELEGRAM_CHANNEL_ID,
                text=message_text,
                parse_mode="HTML"
            )

            # Обновляем последнюю обработанную транзакцию
            last_processed_tx_hash = tx_hash
            print(f"New transaction processed and sent to Telegram: {tx_hash}")
            break  # Прерываем цикл, чтобы не обрабатывать старые транзакции

async def monitor_transactions():
    """
    Основная функция для мониторинга новых транзакций.
    """
    # Инициализация Telegram-бота
    bot = Bot(token=TELEGRAM_BOT_TOKEN)

    while True:
        print("Fetching transactions...")
        transactions = await fetch_transactions()
        if transactions:
            await process_transactions(transactions, bot)
        else:
            print("No transactions data to process.")

        # Ждем 60 секунд перед следующим запросом
        await asyncio.sleep(60)

# Запуск асинхронного цикла
asyncio.run(monitor_transactions())