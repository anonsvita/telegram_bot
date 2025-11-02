"""
Модуль для создания клавиатур и UI элементов бота.

Содержит функции для генерации inline-клавиатур для выбора языков.
"""

from typing import Dict
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .config import LANGS, fmt_lang, TEXT_LIMIT


def language_bar(user_settings: Dict[str, str]) -> InlineKeyboardMarkup:
    """
    Создает главную панель управления языками.

    Отображает текущие настройки языков ввода и вывода,
    а также кнопку для обмена языков местами.

    Args:
        user_settings:
            Словарь с настройками {'src': код_языка, 'dst': код_языка}

    Returns:
        InlineKeyboardMarkup: Клавиатура с кнопками управления языками
    """
    src = user_settings["src"]
    dst = user_settings["dst"]

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=f"🌐 Ввод: {fmt_lang(src)}",
                callback_data="set_src"
            ),
            InlineKeyboardButton(
                text=f"🎯 Вывод: {fmt_lang(dst)}",
                callback_data="set_dst"
            )
        ],
        [
            InlineKeyboardButton(
                text="🔁 Поменять местами",
                callback_data="swap_langs"
            )
        ]
    ])

    return keyboard


def lang_picker(kind: str, page: int = 0) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру для выбора языка.

    Args:
        kind: Тип выбора языка ('src' для исходного, 'dst' для целевого)
        page: Номер страницы (зарезервировано для будущего использования)

    Returns:
        InlineKeyboardMarkup: Клавиатура со списком доступных языков
    """
    # Получаем список всех языков
    order = list(LANGS.keys())

    # Для целевого языка убираем опцию 'auto' (нельзя переводить на "авто")
    if kind == "dst" and "auto" in order:
        order.remove("auto")

    # Создаем кнопки для каждого языка
    per_row = 3  # Количество кнопок в одной строке
    items = []

    for code in order:
        items.append(
            InlineKeyboardButton(
                text=fmt_lang(code),
                callback_data=f"pick:{kind}:{code}"
            )
        )

    # Разбиваем кнопки на строки
    rows = [items[i:i + per_row] for i in range(0, len(items), per_row)]

    # Добавляем кнопку "Назад"
    rows.append([
        InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data="back_to_bar"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def start_text(user_settings: Dict[str, str]) -> str:
    """
    Генерирует приветственное сообщение для команды /start.

    Args:
        user_settings: Словарь с настройками пользователя

    Returns:
        str: Форматированный текст приветствия
    """
    return (
        "Привет! 👋\n"
        "Я — бот-переводчик текста и аудио.\n\n"
        "Что умею:\n"
        "• Автоматически понимаю, что ты прислал: текст или аудио.\n"
        "• Для аудио сам конвертирую в WAV 16kHz "
        "mono, чтобы Whisper работал без ошибок.\n"
        "• Транскрибирую аудио (Whisper) и перевожу.\n"
        f"• Лимиты: аудио до 5 минут, текст до {TEXT_LIMIT} символов.\n\n"
        f"Текущие языки: Ввод = {fmt_lang(user_settings['src'])}, "
        f"Вывод = {fmt_lang(user_settings['dst'])}.\n"
        "Отправь текст/аудио — остальное сделаю сам 😉"
    )
