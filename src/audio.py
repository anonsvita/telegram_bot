"""
Модуль для работы с аудио файлами.

Включает функции для:
- Конвертации аудио в формат WAV mono 16kHz (требование Whisper)
- Определения длительности аудио
- Транскрибации речи через Whisper
- Проверки FFmpeg
"""

import subprocess
from pathlib import Path
from typing import Optional, Tuple

from faster_whisper import WhisperModel

from .config import WHISPER_MODEL


# ============ Глобальная модель Whisper ============
# Используем ленивую инициализацию для экономии памяти
_whisper_model: Optional[WhisperModel] = None
# Храним текущие настройки устройства
_current_device = None
_current_compute_type = None


def get_whisper() -> WhisperModel:
    """
    Получает или создает глобальный экземпляр модели Whisper.

    Модель создается только один раз при первом вызове (lazy init).
    При ошибке загрузки на CUDA автоматически откатывается на CPU.

    Returns:
        WhisperModel: Экземпляр модели Whisper

    Raises:
        RuntimeError: Если не удалось загрузить модель
    """
    global _whisper_model, _current_device, _current_compute_type

    # Импортируем настройки устройства при первом вызове
    from .config import WHISPER_DEVICE, COMPUTE_TYPE

    if _whisper_model is None:
        try:
            _whisper_model = WhisperModel(
                WHISPER_MODEL,
                device=WHISPER_DEVICE,
                compute_type=COMPUTE_TYPE,
            )
            _current_device = WHISPER_DEVICE
            _current_compute_type = COMPUTE_TYPE
            print(
                f"[INFO] Whisper загружен: модель={WHISPER_MODEL}, "
                f"устройство={WHISPER_DEVICE}"
            )
        except Exception as e:
            # Попытка отката на CPU при ошибке с CUDA
            print(
                f"[WARN] Не удалось загрузить Whisper "
                f"на {WHISPER_DEVICE} ({e}). Пробую CPU..."
            )
            _whisper_model = WhisperModel(
                WHISPER_MODEL,
                device="cpu",
                compute_type="int8",
            )
            _current_device = "cpu"
            _current_compute_type = "int8"
            print("[INFO] Whisper загружен на CPU")

    return _whisper_model


# ============ FFmpeg утилиты ============

def _run_ffmpeg_command(cmd: list) -> None:
    """
    Выполняет команду FFmpeg и проверяет успешность выполнения.

    Args:
        cmd: Список аргументов команды для subprocess

    Raises:
        RuntimeError: Если команда завершилась с ошибкой
    """
    completed = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    if completed.returncode != 0:
        error_msg = completed.stderr.decode(errors='ignore')
        raise RuntimeError(
            f"Команда {' '.join(cmd)} завершилась ошибкой:\n{error_msg}"
        )


def ensure_ffmpeg_installed() -> None:
    """
    Проверяет наличие установленных ffmpeg и ffprobe в системе.

    Raises:
        RuntimeError: Если ffmpeg или ffprobe не найдены в PATH
    """
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True
        )
        subprocess.run(
            ["ffprobe", "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True
        )
    except Exception:
        raise RuntimeError(
            "Необходим установленный ffmpeg/ffprobe в PATH.\n"
            "Установите FFmpeg: https://ffmpeg.org/download.html"
        )


def ffprobe_duration(path: Path) -> float:
    """
    Определяет длительность аудио файла через ffprobe.

    Args:
        path: Путь к аудио файлу

    Returns:
        float: Длительность в секундах или 0.0 при ошибке
    """
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "a:0",  # Только первый аудио поток
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path)
    ]

    completed = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    if completed.returncode != 0:
        return 0.0

    try:
        return float(completed.stdout.decode().strip())
    except (ValueError, AttributeError):
        return 0.0


def convert_to_wav_mono16k(src: Path) -> Path:
    """
    Конвертирует аудио файл в формат WAV mono 16kHz.

    Whisper требует именно этот формат для оптимальной работы:
    - 1 канал (моно)
    - 16000 Hz частота дискретизации
    - PCM 16-bit кодирование

    Args:
        src: Путь к исходному аудио файлу

    Returns:
        Path: Путь к сконвертированному WAV файлу

    Raises:
        RuntimeError: Если ffmpeg не установлен или конвертация не удалась
    """
    ensure_ffmpeg_installed()

    # Создаем файл с тем же именем, но расширением .wav
    out = src.with_suffix(".wav")

    cmd = [
        "ffmpeg", "-y",  # -y = перезаписывать без подтверждения
        "-i", str(src),  # Входной файл
        "-ac", "1",  # 1 канал (моно)
        "-ar", "16000",  # 16000 Hz
        "-c:a", "pcm_s16le",  # PCM 16-bit little-endian
        str(out),
    ]

    _run_ffmpeg_command(cmd)
    return out


# ============ Транскрибация ============

def transcribe_audio(
    audio_path: Path,
    language: Optional[str] = None
) -> Tuple[str, str]:
    """
    Транскрибирует аудио файл в текст с помощью Whisper.

    Args:
        audio_path: Путь к аудио файлу (желательно WAV mono 16kHz)
        language: Код языка ('ru', 'en', и т.д.) или None для автоопределения

    Returns:
        Tuple[str, str]: Кортеж (текст транскрипции, определенный код языка)
                         Если определить язык не удалось, возвращается 'auto'

    Raises:
        Exception: При ошибках загрузки модели или транскрибации
    """
    model = get_whisper()

    # Запускаем транскрибацию
    # beam_size=5 обеспечивает хороший баланс между скоростью и качеством
    segments, info = model.transcribe(
        str(audio_path),
        language=language,
        beam_size=5
    )

    # Определенный язык
    detected_lang = info.language or "auto"

    # Собираем весь текст из сегментов
    transcript = "".join(seg.text for seg in segments).strip()

    return transcript, detected_lang
