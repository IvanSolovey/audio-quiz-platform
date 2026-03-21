# Audio Quiz Platform

Внутрішня платформа аудіо-квізів для стажистів.

## Технології
- FastAPI + Jinja2 + HTMX + TailwindCSS
- PostgreSQL + SQLAlchemy (async) + Alembic
- Cloudflare R2 для аудіо файлів

## Запуск локально

1. Скопіюй змінні середовища:
   cp .env.example .env
   # Відредагуй .env

2. Встанови залежності:
   pip install -r requirements.txt

3. Застосуй міграції:
   alembic upgrade head

4. Запусти:
   uvicorn app.main:app --reload

5. Відкрий http://localhost:8000

## Налаштування Cloudflare R2

1. Зайди на https://dash.cloudflare.com → R2 → Create bucket
   - Назви bucket: `audio-quiz-files`

2. Налаштуй Public Access:
   - Bucket Settings → Public Access → Allow Access
   - Скопіюй Public Bucket URL (вигляд: https://pub-xxxx.r2.dev)

3. Створи API токен:
   - R2 → Manage R2 API Tokens → Create API Token
   - Permissions: Object Read & Write для твого bucket
   - Скопіюй Access Key ID та Secret Access Key

4. Заповни .env:
   R2_ACCOUNT_ID=твій-account-id (з URL cloudflare: dash.cloudflare.com/ACCOUNT_ID)
   R2_ACCESS_KEY_ID=...
   R2_SECRET_ACCESS_KEY=...
   R2_BUCKET_NAME=audio-quiz-files
   R2_PUBLIC_URL=https://pub-xxxx.r2.dev

## Локальна розробка без R2

Залиш R2_ACCOUNT_ID порожнім у .env — файли збережуться у static/audio/
і будуть доступні через http://localhost:8000/static/audio/...
