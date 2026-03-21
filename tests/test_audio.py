"""
Запуск: python tests/test_audio.py
Потрібен тестовий mp3 файл: tests/sample.mp3
"""
import asyncio
import uuid
from pathlib import Path
from fastapi import UploadFile
from starlette.datastructures import Headers
import io


async def test_local_upload():
    """Тест локального збереження (без R2)."""
    from app.services.audio_service import upload_audio

    # Мінімальний валідний mp3 (44 байти — тиша)
    mp3_bytes = (
        b"\xff\xfb\x90\x00" + b"\x00" * 40
    )

    mock_file = UploadFile(
        filename="test.mp3",
        headers=Headers({"content-type": "audio/mpeg"}),
        file=io.BytesIO(mp3_bytes),
    )

    quiz_id = uuid.uuid4()
    question_id = uuid.uuid4()

    url, key = await upload_audio(mock_file, quiz_id, question_id)
    print(f"✅ Upload OK")
    print(f"   URL: {url}")
    print(f"   Key: {key}")


if __name__ == "__main__":
    asyncio.run(test_local_upload())
