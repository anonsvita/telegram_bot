"""
Модуль вспомогательных функций.

Содержит утилиты для работы с файлами,
очередью задач и настройками пользователей.
"""

import asyncio
from pathlib import Path
from typing import Dict, Tuple, List

from aiogram import Bot, types

from .config import AUDIO_EXTS, TEXT_LIMIT, AUDIO_LIMIT_SEC


# ============ Хранилище состояний ============

USER_SETTINGS: Dict[int, Dict[str, str]] = {}
"""Настройки пользователей: {user_id: {'src': код_языка, 'dst': код_языка}}"""

USER_BUSY: Dict[int, bool] = {}
"""Флаги занятости пользователей: {user_id: bool}"""

USER_QUEUED: Dict[int, bool] = {}
"""Флаги нахождения в очереди: {user_id: bool}"""

# Очередь задач: (job_id, user_id, message)
JOB_QUEUE: "asyncio.Queue[Tuple[int, int, types.Message]]" = asyncio.Queue()
"""Очередь задач для обработки"""

PENDING: List[Tuple[int, int, types.Message]] = []
"""Список ожидающих задач для отслеживания позиции в очереди"""

JOB_COUNTER = 0
"""Счетчик задач для генерации уникальных ID"""

QUEUE_LOCK = asyncio.Lock()
"""Блокировка для синхронизации доступа к очереди"""


# ============ Функции работы с настройками ============

def user_settings(user_id: int) -> Dict[str, str]:
    """
    Получает или создает настройки пользователя.

    Если пользователь новый, создаются настройки по умолчанию:
    - src: 'auto' (автоопределение языка ввода)
    - dst: 'en' (английский язык вывода)

    Args:
        user_id: ID пользователя Telegram

    Returns:
        Dict[str, str]: Словарь настроек {'src': код, 'dst': код}
    """
    if user_id not in USER_SETTINGS:
        USER_SETTINGS[user_id] = {"src": "auto", "dst": "en"}
    return USER_SETTINGS[user_id]


# ============ Функции работы с очередью ============

async def enqueue_job(user_id: int, message: types.Message) -> Tuple[int, int]:
    """
    Добавляет задачу в очередь обработки.

    Args:
        user_id: ID пользователя
        message: Сообщение для обработки

    Returns:
        Tuple[int, int]: (ID задачи, позиция в очереди)
    """
    global JOB_COUNTER

    async with QUEUE_LOCK:
        JOB_COUNTER += 1
        job_id = JOB_COUNTER

        # Добавляем в список ожидающих и в очередь
        PENDING.append((job_id, user_id, message))
        await JOB_QUEUE.put((job_id, user_id, message))

        # Определяем позицию в очереди
        pos = next(
            (
                i
                for i, (jid, _, _) in enumerate(PENDING)
                if jid == job_id
            ),
            -1,
        )
        return job_id, pos + 1


def queue_position(job_id: int) -> int:
    """
    Определяет текущую позицию задачи в очереди.

    Args:
        job_id: ID задачи

    Returns:
        int: Позиция в очереди (начиная с 1) или -1 если задача не найдена
    """
    for i, (jid, _, _) in enumerate(PENDING):
        if jid == job_id:
            return i + 1
    return -1


async def remove_job_from_queue(job_id: int) -> None:
    """
    Удаляет задачу из списка ожидающих после завершения обработки.

    Args:
        job_id: ID задачи для удаления
    """
    async with QUEUE_LOCK:
        for i, (jid, uid, _) in enumerate(PENDING):
            if jid == job_id:
                PENDING.pop(i)
                break


# ============ Функции работы с файлами ============

async def safe_download(bot: Bot, file_id: str, dest: Path) -> None:
    """
    Безопасно скачивает файл от Telegram.

    Пробует два метода загрузки для совместимости с разными версиями aiogram.

    Args:
        bot: Экземпляр бота
        file_id: ID файла в Telegram
        dest: Путь для сохранения файла

    Raises:
        RuntimeError: Если не удалось скачать файл обоими методами
    """
    try:
        # Первый способ (aiogram 3.x)
        file = await bot.get_file(file_id)
        if not file.file_path:
            raise RuntimeError("Не удалось получить путь к файлу от Telegram.")
        await bot.download_file(file.file_path, destination=dest)
    except Exception:
        try:
            # Второй способ (альтернативный метод)
            await bot.download(file=file_id, destination=dest)
        except Exception as e:
            raise RuntimeError(f"Не удалось скачать файл: {e}")


def is_audio_document(doc: types.Document) -> bool:
    """
    Проверяет, является ли документ аудио файлом.

    Проверка проводится по:
    1. MIME-типу (начинается с 'audio/')
    2. Расширению файла (список в AUDIO_EXTS)

    Args:
        doc: Объект документа Telegram

    Returns:
        bool: True если документ - аудио файл
    """
    if not doc:
        return False

    # Проверяем MIME-тип
    mime_type = (doc.mime_type or "").lower()
    if mime_type.startswith("audio/"):
        return True

    # Проверяем расширение файла
    ext = Path(doc.file_name or "").suffix.lower()
    return ext in AUDIO_EXTS


# ============ Текстовые сообщения для пользователя ============

def human_limit_exceeded(kind: str) -> str:
    """
    Генерирует сообщение о превышении лимита.

    Args:
        kind: Тип лимита ('text' или 'audio')

    Returns:
        str: Сообщение об ошибке для пользователя
    """
    if kind == "text":
        return (
            f"⚠️ Превышен лимит текста ({TEXT_LIMIT} символов). "
            "Сократи, пожалуйста."
        )
    if kind == "audio":
        return (
            f"⚠️ Аудио дольше {AUDIO_LIMIT_SEC // 60} минут — "
            "сократи, пожалуйста."
        )
    return "⚠️ Превышен лимит."
