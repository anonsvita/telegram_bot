"""
Модуль для обработки текстовых сообщений.

Содержит логику определения языка и перевода текстовых сообщений.
"""

from typing import Tuple

from .translation import (
    text_looks_russian,
    pick_auto_dst_from_lang,
    translate_text,
)


def process_text_message(
    text: str,
    src_lang: str,
    configured_dst: str
) -> Tuple[str, str, str, bool]:
    """
    Обрабатывает текстовое сообщение: определяет язык и переводит.

    Логика работы:
    1. Если src_lang='auto', определяем язык по наличию кириллицы
    2. Выбираем целевой язык по правилу: RU->EN, остальные->RU
    3. Переводим текст на целевой язык

    Args:
        text: Текст для обработки
        src_lang: Исходный язык ('auto' для автоопределения)
        configured_dst: Настроенный пользователем целевой язык

    Returns:
        Tuple содержит:
            - translated_text (str): Переведенный текст
            - detected_lang (str): Определенный язык исходного текста
            - effective_dst (str): Фактически использованный целевой язык
            - lang_was_switched (bool):
                True, если целевой язык был изменен автоматически
    """

    # Определяем язык исходного текста
    if src_lang == "auto":
        # Простая эвристика: есть кириллица -> русский, иначе -> английский
        looks_ru = text_looks_russian(text)
        detected_lang = "ru" if looks_ru else "en"
    else:
        # Язык задан явно
        detected_lang = src_lang

    # Выбираем целевой язык по правилу автоопределения
    effective_dst = pick_auto_dst_from_lang(detected_lang)

    # Проверяем, был ли изменен целевой язык
    lang_was_switched = (configured_dst != effective_dst)

    # Переводим текст
    translated = translate_text(text, "auto", effective_dst)

    return translated, detected_lang, effective_dst, lang_was_switched
