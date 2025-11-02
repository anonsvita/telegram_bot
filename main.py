"""
Telegram бот для перевода текста и аудио.

Основные возможности:
- Автоматическое определение языка текста и аудио
- Перевод текста между несколькими языками
- Транскрибация аудио через Whisper (с поддержкой GPU)
- Очередь задач для последовательной обработки
- Автоматическая конвертация аудио в нужный формат

Использование:
1. Установите переменную окружения BOT_TOKEN
2. Опционально: WHISPER_MODEL, WHISPER_DEVICE
3. Запустите: python main.py
"""

import asyncio

from aiogram import Bot, Dispatcher

from src.config import BOT_TOKEN
from src.handlers import register_handlers, worker


async def main() -> None:
    """
    Главная функция запуска бота.

    Инициализирует:
    - Экземпляр бота с токеном
    - Диспетчер для обработки сообщений
    - Регистрирует все обработчики
    - Запускает worker для обработки очереди
    - Запускает polling для получения обновлений
    """
    # Проверяем наличие токена
    if not BOT_TOKEN:
        raise ValueError(
            "Не задан BOT_TOKEN!\n"
            "Установите переменную окружения BOT_TOKEN или создайте файл .env"
        )

    # Создаем бота и диспетчер
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    # Регистрируем обработчики
    register_handlers(dp)

    print("[INFO] Бот запущен! Нажмите Ctrl+C для остановки.")

    # Запускаем worker для обработки очереди в фоне
    asyncio.create_task(worker(bot))

    # Запускаем polling (получение обновлений от Telegram)
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[INFO] Бот остановлен пользователем.")
    except Exception as e:
        print(f"[ERROR] Критическая ошибка: {e}")
        raise
