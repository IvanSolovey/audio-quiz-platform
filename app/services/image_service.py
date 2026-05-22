from __future__ import annotations
import uuid
from pathlib import Path
import boto3
from botocore.config import Config
from fastapi import UploadFile, HTTPException

from app.config import settings

ALLOWED_CONTENT_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
}

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


def _get_r2_client():
    return boto3.client(
        "s3",
        endpoint_url=f"https://{settings.r2_account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


async def upload_image(file: UploadFile) -> str:
    """
    Завантажує зображення у R2.

    Returns:
        public URL рядком
    """
    content_type = file.content_type or ""
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Непідтримуваний формат: {content_type}. "
                   f"Дозволені: jpeg, png, gif, webp, svg",
        )

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"Файл завеликий. Максимум: {MAX_FILE_SIZE // 1024 // 1024} МБ",
        )

    ext = ALLOWED_CONTENT_TYPES[content_type]
    image_key = f"images/docs/{uuid.uuid4()}{ext}"

    if settings.r2_account_id:
        client = _get_r2_client()
        client.put_object(
            Bucket=settings.r2_bucket_name,
            Key=image_key,
            Body=content,
            ContentType=content_type,
        )
        return f"{settings.r2_public_url}/{image_key}"
    else:
        # Fallback: локальне зберігання для dev без R2
        local_path = Path("static") / image_key
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(content)
        return f"/static/{image_key}"
