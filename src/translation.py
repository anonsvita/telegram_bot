"""
Модуль для работы с переводами текста.

Использует deep_translator для перевода между языками.
"""

import re


def translate_text(text: str, src: str, dst: str) -> str:
    """
    Переводит текст с одного языка на другой.

    Args:
        text: Текст для перевода
        src: Исходный язык ('auto' для автоопределения)
        dst: Целевой язык (не может быть 'auto')

    Returns:
        str: Переведенный текст или исходный текст при ошибке
    """
    try:
        from deep_translator import GoogleTranslator
        # None означает автоопределение для GoogleTranslator
        source = None if src == "auto" else src
        translator = GoogleTranslator(source=source or "auto", target=dst)
        return translator.translate(text)
    except Exception as e:
        # В случае ошибки возвращаем исходный текст
        print(f"[WARN] Translation failed: {e}")
        return text


# ============ Определение языка текста ============

_CYRILLIC_RE = re.compile(r"[\u0400-\u04FF]")
"""Регулярное выражение для поиска кириллических символов"""


def text_looks_russian(text: str) -> bool:
    """
    Определяет, выглядит ли текст как русский (по наличию кириллицы).

    Это простая эвристика для быстрого определения языка текста.
    Если в тексте есть хотя бы один кириллический символ, считаем его русским.

    Args:
        text: Текст для проверки

    Returns:
        bool: True если текст содержит кириллицу, иначе False
    """
    return bool(_CYRILLIC_RE.search(text))


def pick_auto_dst_from_lang(lang_code: str) -> str:
    """
    Выбирает целевой язык по правилу автоопределения.

    Правило:
    - Если исходный язык русский (ru) -> переводим на английский (en)
    - Если исходный любой другой -> переводим на русский (ru)

    Args:
        lang_code: Код определенного языка (например, 'ru', 'en', 'de')

    Returns:
        str: Код целевого языка ('en' или 'ru')
    """
    return "en" if lang_code == "ru" else "ru"
