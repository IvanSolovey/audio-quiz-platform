from __future__ import annotations
import os
import uuid
import tempfile
import subprocess
from pathlib import Path
import boto3
from botocore.config import Config
from fastapi import UploadFile, HTTPException
from app.config import settings

# Дозволені формати на вхід
ALLOWED_CONTENT_TYPES = {
    "audio/mpeg",
    "audio/mp3",
    "audio/wav",
    "audio/x-wav",
    "audio/ogg",
    "audio/mp4",
    "audio/x-m4a",
    "audio/m4a",
    "audio/flac",
}

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


def _get_r2_client():
    """Повертає boto3 клієнт для Cloudflare R2."""
    return boto3.client(
        "s3",
        endpoint_url=f"https://{settings.r2_account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


def _convert_to_mp3(input_path: str, output_path: str) -> None:
    """Конвертує аудіо файл у mp3 128kbps через ffmpeg."""
    result = subprocess.run(
        [
            "ffmpeg",
            "-i", input_path,
            "-vn",                    # без відео
            "-acodec", "libmp3lame", # кодек
            "-b:a", "128k",          # бітрейт
            "-ar", "44100",          # sample rate
            "-y",                    # перезаписати без питань
            output_path,
        ],
        capture_output=True,
        text=True,
        timeout=120,  # максимум 2 хвилини
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg error: {result.stderr}")


async def upload_audio(
    file: UploadFile,
    quiz_id: uuid.UUID,
    question_id: uuid.UUID,
) -> tuple[str, str]:
    """
    Завантажує аудіофайл у R2 після конвертації у mp3.

    Returns:
        (audio_url, audio_key) — публічний URL і ключ в R2
    """
    # Перевірка типу файлу
    content_type = file.content_type or ""
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Непідтримуваний формат файлу: {content_type}. "
                   f"Дозволені: mp3, wav, ogg, m4a, flac",
        )

    # Читаємо файл у пам'ять (перевірка розміру)
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"Файл завеликий. Максимум: {MAX_FILE_SIZE // 1024 // 1024} МБ",
        )

    # Визначаємо чи потрібна конвертація
    needs_conversion = content_type not in {"audio/mpeg", "audio/mp3"}

    # Ключ файлу в R2
    audio_key = f"audio/{quiz_id}/{question_id}.mp3"

    # Конвертація і завантаження через temp файли
    with tempfile.TemporaryDirectory() as tmpdir:
        # Зберегти оригінал
        original_suffix = _get_suffix_for_content_type(content_type)
        original_path = os.path.join(tmpdir, f"original{original_suffix}")
        with open(original_path, "wb") as f:
            f.write(content)

        # Конвертувати якщо потрібно
        if needs_conversion:
            mp3_path = os.path.join(tmpdir, "output.mp3")
            _convert_to_mp3(original_path, mp3_path)
        else:
            mp3_path = original_path

        # Завантажити в R2
        if settings.r2_account_id:
            client = _get_r2_client()
            with open(mp3_path, "rb") as f:
                client.put_object(
                    Bucket=settings.r2_bucket_name,
                    Key=audio_key,
                    Body=f,
                    ContentType="audio/mpeg",
                )
            audio_url = f"{settings.r2_public_url}/{audio_key}"
        else:
            # Fallback: локальне зберігання для dev без R2
            audio_url = await _save_locally(mp3_path, audio_key)

    return audio_url, audio_key


async def delete_audio(audio_key: str) -> None:
    """Видаляє аудіофайл з R2. Не кидає помилку якщо файл не знайдено."""
    if not audio_key or not settings.r2_account_id:
        return
    try:
        client = _get_r2_client()
        client.delete_object(Bucket=settings.r2_bucket_name, Key=audio_key)
    except Exception as e:
        # Логуємо але не зупиняємо виконання
        print(f"Warning: не вдалось видалити аудіо {audio_key}: {e}")


def _get_suffix_for_content_type(content_type: str) -> str:
    mapping = {
        "audio/mpeg": ".mp3",
        "audio/mp3": ".mp3",
        "audio/wav": ".wav",
        "audio/x-wav": ".wav",
        "audio/ogg": ".ogg",
        "audio/mp4": ".m4a",
        "audio/x-m4a": ".m4a",
        "audio/m4a": ".m4a",
        "audio/flac": ".flac",
    }
    return mapping.get(content_type, ".audio")


async def _save_locally(mp3_path: str, audio_key: str) -> str:
    """
    Fallback для локальної розробки без R2.
    Зберігає у static/audio/ і повертає локальний URL.
    """
    local_dir = Path("static") / Path(audio_key).parent
    local_dir.mkdir(parents=True, exist_ok=True)

    local_path = Path("static") / audio_key
    import shutil
    shutil.copy2(mp3_path, local_path)

    # Повертаємо URL відносно статичного маунту
    return f"/static/{audio_key}"
