"""
Модуль обработчиков сообщений и callback-запросов.

Содержит всю логику взаимодействия с пользователем:
- Обработчики команд (/start, /queue)
- Обработчики callback-кнопок (выбор языков, смена языков)
- Основной обработчик текстовых и аудио сообщений
- Worker для обработки очереди задач
"""

import tempfile
import uuid
from pathlib import Path

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command

from .config import TEXT_LIMIT, AUDIO_LIMIT_SEC, fmt_lang
from .keyboards import language_bar, lang_picker, start_text
from .utils import (
    user_settings, enqueue_job, queue_position, remove_job_from_queue,
    safe_download, is_audio_document, human_limit_exceeded,
    USER_BUSY, USER_QUEUED, JOB_QUEUE, PENDING
)
from .text import process_text_message
from .audio import convert_to_wav_mono16k, ffprobe_duration, transcribe_audio
from .translation import pick_auto_dst_from_lang, translate_text


# ============ Обработчики команд ============

def register_handlers(dp: Dispatcher) -> None:
    """
    Регистрирует все обработчики в диспетчере.

    Args:
        dp: Экземпляр диспетчера aiogram
    """
    # Команды
    dp.message.register(cmd_start, Command("start"))
    dp.message.register(cmd_queue, Command("queue"))

    # Callback-кнопки
    dp.callback_query.register(cb_set_src, F.data == "set_src")
    dp.callback_query.register(cb_set_dst, F.data == "set_dst")
    dp.callback_query.register(cb_swap_langs, F.data == "swap_langs")
    dp.callback_query.register(cb_back, F.data == "back_to_bar")
    dp.callback_query.register(cb_pick, F.data.startswith("pick:"))

    # Обработчик сообщений
    dp.message.register(
        handle_any_message,
        F.content_type.in_({"text", "voice", "audio", "document"})
    )


async def cmd_start(message: types.Message) -> None:
    """
    Обработчик команды /start.

    Инициализирует настройки пользователя и показывает приветствие.
    """
    uid = message.from_user.id
    settings = user_settings(uid)
    await message.answer(
        start_text(settings),
        reply_markup=language_bar(settings)
    )


async def cmd_queue(message: types.Message) -> None:
    """
    Обработчик команды /queue.

    Показывает информацию о текущей очереди задач.
    """
    uid = message.from_user.id
    settings = user_settings(uid)

    # Получаем ID всех задач в очереди
    pos_list = [jid for jid, _, _ in PENDING]

    pos_preview = pos_list[:10]
    more = "..." if len(pos_list) > 10 else ""
    await message.answer(
        f"🧾 В очереди сейчас: {len(PENDING)}.\n"
        f"Активные заявки (id): {pos_preview}{more}",
        reply_markup=language_bar(settings)
    )


# ============ Обработчики callback-кнопок ============

async def cb_set_src(cb: types.CallbackQuery) -> None:
    """Открывает меню выбора исходного языка."""
    await cb.message.edit_reply_markup(reply_markup=lang_picker("src"))
    await cb.answer()


async def cb_set_dst(cb: types.CallbackQuery) -> None:
    """Открывает меню выбора целевого языка."""
    await cb.message.edit_reply_markup(reply_markup=lang_picker("dst"))
    await cb.answer()


async def cb_swap_langs(cb: types.CallbackQuery) -> None:
    """
    Меняет языки ввода и вывода местами.

    Особенность: если исходный язык 'auto', обмен не производится.
    """
    settings = user_settings(cb.from_user.id)

    if settings["src"] == "auto":
        # Нельзя поменять 'auto' с конкретным языком
        settings["dst"] = settings.get("dst", "en")
    else:
        # Меняем местами
        settings["src"], settings["dst"] = settings["dst"], settings["src"]
        # Если после обмена src стал 'auto', сохраняем его
        if settings["src"] == "auto":
            settings["src"] = "auto"

    await cb.message.edit_reply_markup(reply_markup=language_bar(settings))
    await cb.answer("Языки поменял местами")


async def cb_back(cb: types.CallbackQuery) -> None:
    """Возвращает к главной панели управления языками."""
    settings = user_settings(cb.from_user.id)
    await cb.message.edit_reply_markup(reply_markup=language_bar(settings))
    await cb.answer()


async def cb_pick(cb: types.CallbackQuery) -> None:
    """
    Обработчик выбора конкретного языка.

    Формат callback_data: 'pick:kind:code'
    где kind = 'src' или 'dst', code = код языка
    """
    _, kind, code = cb.data.split(":")
    settings = user_settings(cb.from_user.id)

    if kind == "src":
        settings["src"] = code
    else:
        # Для целевого языка не допускаем 'auto'
        settings["dst"] = code if code != "auto" else settings.get("dst", "en")

    await cb.message.edit_reply_markup(reply_markup=language_bar(settings))

    lang_type = "ввод" if kind == "src" else "вывод"
    await cb.answer(f"Ок, {lang_type} = {fmt_lang(code)}")


# ============ Основной обработчик сообщений ============

async def handle_any_message(message: types.Message) -> None:
    """
    Обрабатывает входящие текстовые и аудио сообщения.

    Логика:
    1. Проверяет, не занят ли пользователь другой задачей
    2. Проверяет лимиты (текст/аудио)
    3. Добавляет задачу в очередь
    """
    uid = message.from_user.id

    # Игнорируем команды (обрабатываются отдельно)
    if message.text and message.text.startswith("/"):
        return

    # Проверяем, не занят ли пользователь
    if USER_BUSY.get(uid) or USER_QUEUED.get(uid):
        # Ищем задачу пользователя в очереди
        my_job_id = None
        for jid, u, _ in PENDING:
            if u == uid:
                my_job_id = jid
                break

        if my_job_id:
            pos = queue_position(my_job_id)
            await message.answer(
                f"⏳ Уже есть активный запрос. "
                f"Жду завершения.\n"
                f"Твоя позиция в очереди: {pos}/{len(PENDING)}.",
                reply_markup=language_bar(user_settings(uid))
            )
        else:
            await message.answer(
                "⏳ Уже обрабатываю твой предыдущий запрос. "
                "Дождись, пожалуйста.",
                reply_markup=language_bar(user_settings(uid))
            )
        return

    # Быстрая проверка лимита текста
    if message.text and len(message.text) > TEXT_LIMIT:
        await message.answer(
            human_limit_exceeded("text"),
            reply_markup=language_bar(user_settings(uid))
        )
        return

    # Добавляем в очередь
    USER_QUEUED[uid] = True
    job_id, pos = await enqueue_job(uid, message)

    await message.answer(
        f"✅ Принял запрос (#{job_id}). "
        f"Твоя позиция в очереди: {pos}/{len(PENDING)}.",
        reply_markup=language_bar(user_settings(uid))
    )


# ============ Worker для обработки очереди ============

async def worker(bot: Bot) -> None:
    """
    Worker для последовательной обработки задач из очереди.

    Бесконечный цикл, который:
    1. Берет задачу из очереди
    2. Обрабатывает её (текст или аудио)
    3. Отправляет результат пользователю
    4. Помечает задачу как завершенную

    Args:
        bot: Экземпляр бота для отправки сообщений
    """
    while True:
        # Ждем новую задачу
        job_id, user_id, message = await JOB_QUEUE.get()

        # Помечаем пользователя как занятого
        USER_BUSY[user_id] = True
        USER_QUEUED[user_id] = False

        try:
            await process_job(bot, job_id, user_id, message)
        except Exception as e:
            # Обрабатываем ошибки и уведомляем пользователя
            try:
                settings = user_settings(user_id)
                await message.answer(
                    f"❌ Ошибка обработки: {e}",
                    reply_markup=language_bar(settings)
                )
            except Exception:
                # Если даже отправка ошибки не удалась, просто логируем
                print(
                    f"[ERROR] Failed to send error msg to user "
                    f"{user_id}: {e}"
                )
        finally:
            # Очищаем состояние пользователя
            await remove_job_from_queue(job_id)
            USER_BUSY[user_id] = False
            JOB_QUEUE.task_done()


# ============ Обработка задачи ============

async def process_job(
    bot: Bot,
    job_id: int,
    user_id: int,
    message: types.Message
) -> None:
    """
    Обрабатывает одну задачу из очереди.

    Определяет тип сообщения (текст или аудио) и
    вызывает соответствующий обработчик.

    Args:
        bot: Экземпляр бота
        job_id: ID задачи
        user_id: ID пользователя
        message: Сообщение для обработки
    """
    settings = user_settings(user_id)
    src = settings["src"]
    configured_dst = settings["dst"]

    # Уведомляем о начале обработки
    try:
        await message.answer(
            f"🚀 Начинаю обработку (заявка #{job_id}). "
            f"Текущая очередь: {len(PENDING)}.",
            reply_markup=language_bar(settings)
        )
    except Exception:
        pass

    # ========== Обработка ТЕКСТА ==========
    if message.text and not message.text.startswith("/"):
        await process_text_job(message, user_id, settings, src, configured_dst)
        return

    # ========== Обработка АУДИО ==========
    await process_audio_job(
        bot,
        message,
        user_id,
        settings,
        src,
        configured_dst
    )


async def process_text_job(
    message: types.Message,
    user_id: int,
    settings: dict,
    src: str,
    configured_dst: str
) -> None:
    """
    Обрабатывает текстовое сообщение.

    Args:
        message: Сообщение с текстом
        user_id: ID пользователя
        settings: Настройки пользователя
        src: Исходный язык
        configured_dst: Настроенный целевой язык
    """
    text = message.text.strip()

    # Проверка лимита
    if len(text) > TEXT_LIMIT:
        await message.answer(
            human_limit_exceeded("text"),
            reply_markup=language_bar(settings)
        )
        return

    # Обрабатываем текст (определяем язык, переводим)
    (translated, detected_lang,
     effective_dst, lang_was_switched) = process_text_message(
        text, src, configured_dst
    )

    # Обновляем настройки пользователя если язык был переключен
    if lang_was_switched:
        settings["dst"] = effective_dst

    # Формируем ответ
    response_parts = [
        "📝 Готово!\n",
        f"Определённый язык текста: {fmt_lang(detected_lang)}",
        f"Целевой язык: {fmt_lang(effective_dst)}"
    ]

    # ИСПРАВЛЕНИЕ БАГА: показываем только если язык был переключен
    if lang_was_switched:
        msg = f"🔁 Авто: целевой язык переключён на {fmt_lang(effective_dst)}"
        response_parts.append(msg)

    response_parts.append(f"\n{translated}")

    await message.answer(
        "\n".join(response_parts),
        reply_markup=language_bar(settings)
    )


async def process_audio_job(
    bot: Bot,
    message: types.Message,
    user_id: int,
    settings: dict,
    src: str,
    configured_dst: str
) -> None:
    """
    Обрабатывает аудио сообщение (голосовое, аудио файл или документ).

    Args:
        bot: Экземпляр бота
        message: Сообщение с аудио
        user_id: ID пользователя
        settings: Настройки пользователя
        src: Исходный язык
        configured_dst: Настроенный целевой язык
    """
    # Определяем тип и получаем file_id
    file_id = None
    filename_hint = None
    duration = None

    if message.voice:
        file_id = message.voice.file_id
        filename_hint = f"voice_{file_id}.ogg"
        duration = message.voice.duration
    elif message.audio:
        file_id = message.audio.file_id
        filename_hint = message.audio.file_name or f"audio_{file_id}.mp3"
        duration = message.audio.duration
    elif message.document and is_audio_document(message.document):
        file_id = message.document.file_id
        filename_hint = message.document.file_name or f"audio_{file_id}"
        duration = None
    else:
        # Не поддерживаемый тип
        await message.answer(
            "❓ Это не текст и не поддерживаемое аудио. "
            "Пришли текст или аудиофайл/голосовое.",
            reply_markup=language_bar(settings)
        )
        return

    # Скачиваем файл
    tmpdir = Path(tempfile.mkdtemp(prefix="tgtrans_"))
    raw_path = tmpdir / (filename_hint or f"aud_{uuid.uuid4().hex}.bin")

    try:
        await safe_download(bot, file_id, raw_path)
    except Exception as e:
        await message.answer(
            f"❌ Не удалось скачать файл: {e}",
            reply_markup=language_bar(settings)
        )
        return

    # Проверяем длительность
    if not duration:
        duration = int(ffprobe_duration(raw_path))

    if duration and duration > AUDIO_LIMIT_SEC:
        await message.answer(
            human_limit_exceeded("audio"),
            reply_markup=language_bar(settings)
        )
        return

    # Конвертируем в WAV mono 16kHz
    try:
        wav_path = convert_to_wav_mono16k(raw_path)
    except Exception as e:
        await message.answer(
            f"❌ Не удалось подготовить аудио: {e}",
            reply_markup=language_bar(settings)
        )
        return

    # Транскрибируем
    try:
        w_lang = None if src == "auto" else src
        transcript, detected = transcribe_audio(wav_path, w_lang)
    except Exception as e:
        await message.answer(
            f"❌ Ошибка транскрибации: {e}",
            reply_markup=language_bar(settings)
        )
        return

    if not transcript:
        await message.answer(
            "😕 Не получилось распознать речь. Попробуй запись получше.",
            reply_markup=language_bar(settings)
        )
        return

    # Определяем целевой язык по правилу
    effective_dst = pick_auto_dst_from_lang(detected)
    lang_was_switched = (configured_dst != effective_dst)

    # Обновляем настройки если язык переключился
    if lang_was_switched:
        settings["dst"] = effective_dst

    # Переводим
    source_for_translation = detected if detected != "auto" else "auto"
    translated = translate_text(
        transcript,
        source_for_translation,
        effective_dst
    )

    # Формируем ответ
    response_parts = [
        "🎧 Готово!\n",
        f"Определённый язык аудио: {fmt_lang(detected)}",
        f"Целевой язык перевода: {fmt_lang(effective_dst)}"
    ]

    # ИСПРАВЛЕНИЕ БАГА: показываем только если язык был переключен
    if lang_was_switched:
        msg = f"🔁 Авто: целевой язык переключён на {fmt_lang(effective_dst)}"
        response_parts.append(msg)

    response_parts.extend([
        f"\n🗒 Расшифровка:\n{transcript}",
        f"\n🌍 Перевод:\n{translated}"
    ])

    await message.answer(
        "\n".join(response_parts),
        reply_markup=language_bar(settings)
    )
