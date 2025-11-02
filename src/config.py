"""
Модуль конфигурации бота.

Содержит все настройки, константы и функции для определения окружения.
"""

import os
from pathlib import Path


def _load_environment() -> None:
    """
    Загружает переменные окружения из .env файла, если он существует.

    Используется для локальной разработки. В продакшене переменные
    должны быть заданы через Docker или системное окружение.
    """
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        # Если dotenv не установлен или файла нет, продолжаем без него
        pass


def pick_device() -> str:
    """
    Автоматически определяет устройство для Whisper (cuda или cpu).

    Приоритет выбора:
    1. Если задана переменная WHISPER_DEVICE (cuda/cpu), используем её
    2. Проверяем доступность CUDA через ctranslate2
    3. По умолчанию используем CPU

    Returns:
        str: 'cuda' если доступна GPU, иначе 'cpu'
    """
    dev = os.getenv("WHISPER_DEVICE")
    if dev in {"cuda", "cpu"}:
        return dev

    # Пытаемся определить наличие CUDA
    try:
        import ctranslate2
        if hasattr(ctranslate2, "get_cuda_device_count"):
            if ctranslate2.get_cuda_device_count() > 0:
                return "cuda"
    except Exception:
        pass

    return "cpu"


# Загружаем переменные окружения
_load_environment()

# ============ Основные настройки ============
BOT_TOKEN = os.getenv("BOT_TOKEN")
"""Токен Telegram бота (обязательная переменная)"""

WHISPER_DEVICE = pick_device()
"""Устройство для Whisper: 'cuda' или 'cpu'"""

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")
"""Модель Whisper: tiny, base, small, medium, large-v3"""

COMPUTE_TYPE = "float16" if WHISPER_DEVICE == "cuda" else "int8"
"""Тип вычислений для Whisper: float16 для GPU, int8 для CPU"""

# ============ Лимиты ============
TEXT_LIMIT = 10_000
"""Максимальная длина текста для перевода (символы)"""

AUDIO_LIMIT_SEC = 5 * 60  # 5 минут
"""Максимальная длительность аудио (секунды)"""

# ============ Пути ============
DATA_DIR = Path("./data")
"""Директория для временных файлов"""
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ============ Поддерживаемые форматы аудио ============
AUDIO_EXTS = {
    ".mp3", ".wav", ".m4a", ".aac", ".ogg", ".oga",
    ".opus", ".flac", ".webm", ".amr", ".wma"
}
"""Расширения файлов, которые считаются аудио"""

# ============ Поддерживаемые языки ============
LANGS = {
    "auto": "Авто",
    "en": "English",
    "ru": "Русский",
    "de": "Deutsch",
    "fr": "Français",
    "es": "Español",
    "it": "Italiano",
    "tr": "Türkçe",
    "ar": "العربية",
    "zh": "中文",
}
"""Словарь поддерживаемых языков: код -> название"""


def fmt_lang(code: str) -> str:
    """
    Форматирует код языка для отображения пользователю.

    Args:
        code: Код языка (например, 'en', 'ru', 'auto')

    Returns:
        str: Отформатированная строка (например, 'English (en)' или 'Авто')
    """
    if code == "auto":
        return LANGS["auto"]
    return f"{LANGS.get(code, code)} ({code})"
