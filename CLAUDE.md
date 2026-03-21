# CLAUDE.md — Головний контекст проєкту

> Цей файл читають усі агенти перед початком роботи.
> Не змінюй цей файл під час виконання завдань.

---

## Що ми будуємо

Внутрішня навчальна платформа для стажистів компанії.
**Основна фіча:** стажист слухає аудіокліп і обирає правильну відповідь із кількох варіантів (аудіо-квіз).

Дві ролі користувачів:
- **trainee** — слухає аудіо, відповідає на питання, бачить свій прогрес
- **admin** — завантажує аудіофайли, створює квізи та питання, переглядає результати

---

## Технологічний стек

| Шар | Технологія | Версія |
|-----|-----------|--------|
| Web framework | FastAPI | ≥ 0.111 |
| Шаблони | Jinja2 | вбудований у FastAPI |
| Інтерактивність | HTMX | 2.x (CDN) |
| Стилі | TailwindCSS | 3.x (CDN) |
| База даних | PostgreSQL | 15+ |
| ORM | SQLAlchemy (async) | 2.x |
| Міграції | Alembic | latest |
| Аудіо сховище | Cloudflare R2 (S3-сумісний) | — |
| Аудіо конвертація | ffmpeg (системний) | — |
| Автентифікація | JWT у httpOnly cookie | python-jose |
| Паролі | bcrypt | passlib |
| Python | 3.11+ | — |

**Важливо:** Жодного окремого JS-фреймворку (React, Vue тощо).
Tailwind і HTMX підключаються через CDN у base.html.

---

## Структура проєкту

```
audio-quiz-platform/
├── CLAUDE.md                  ← цей файл
├── AGENTS.md                  ← список агентів
├── agents/                    ← інструкції для кожного агента
│
├── app/
│   ├── main.py                ← FastAPI app instance, middleware, router registration
│   ├── config.py              ← pydantic-settings, .env змінні
│   ├── database.py            ← async engine, SessionLocal, get_db dependency
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── user.py            ← User модель
│   │   ├── quiz.py            ← Quiz, Question, AnswerOption моделі
│   │   └── result.py          ← QuizAttempt, AttemptAnswer моделі
│   │
│   ├── schemas/               ← Pydantic схеми (request/response)
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── quiz.py
│   │   └── result.py
│   │
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── auth.py            ← GET/POST /login, POST /logout
│   │   ├── trainee.py         ← GET /dashboard, /quiz/{id}, /progress
│   │   └── admin.py           ← GET/POST /admin/*
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── auth_service.py    ← логіка JWT, перевірка паролів
│   │   ├── quiz_service.py    ← бізнес-логіка квізів
│   │   ├── result_service.py  ← збереження відповідей, підрахунок балів
│   │   └── audio_service.py   ← завантаження в R2, ffmpeg конвертація
│   │
│   ├── dependencies.py        ← get_current_user, require_admin
│   │
│   └── templates/
│       ├── base.html          ← html, head (CDN), nav, flash messages
│       ├── auth/
│       │   └── login.html
│       ├── trainee/
│       │   ├── dashboard.html
│       │   ├── quiz.html      ← аудіоплеєр + HTMX відповіді
│       │   ├── result.html
│       │   └── progress.html
│       ├── admin/
│       │   ├── dashboard.html
│       │   ├── quiz_list.html
│       │   ├── quiz_edit.html
│       │   └── results.html
│       └── partials/          ← HTMX фрагменти (не повні сторінки)
│           ├── question.html
│           └── answer_result.html
│
├── alembic/
│   ├── env.py
│   └── versions/
│
├── static/                    ← тільки якщо потрібні локальні файли
├── .env.example
├── .env                       ← НЕ комітити в git
├── .gitignore
├── requirements.txt
└── README.md
```

---

## База даних — схема сутностей

```
User
  id            UUID PK
  email         String UNIQUE NOT NULL
  name          String NOT NULL
  role          Enum('trainee', 'admin') DEFAULT 'trainee'
  password_hash String NOT NULL
  created_at    DateTime DEFAULT now()

Quiz
  id            UUID PK
  title         String NOT NULL
  description   String NULLABLE
  created_by    UUID FK → User.id
  is_published  Boolean DEFAULT false
  created_at    DateTime DEFAULT now()

Question
  id            UUID PK
  quiz_id       UUID FK → Quiz.id CASCADE DELETE
  text          String NOT NULL        ← підпис або інструкція до аудіо
  audio_url     String NOT NULL        ← публічний URL в R2
  audio_key     String NOT NULL        ← ключ об'єкта в R2 (для видалення)
  order_index   Integer NOT NULL       ← порядок питань у квізі
  created_at    DateTime DEFAULT now()

AnswerOption
  id            UUID PK
  question_id   UUID FK → Question.id CASCADE DELETE
  text          String NOT NULL
  is_correct    Boolean DEFAULT false

QuizAttempt
  id            UUID PK
  user_id       UUID FK → User.id
  quiz_id       UUID FK → Quiz.id
  started_at    DateTime DEFAULT now()
  completed_at  DateTime NULLABLE
  score         Integer NULLABLE       ← кількість правильних відповідей

AttemptAnswer
  id               UUID PK
  attempt_id       UUID FK → QuizAttempt.id CASCADE DELETE
  question_id      UUID FK → Question.id
  selected_option  UUID FK → AnswerOption.id
  is_correct       Boolean NOT NULL
  answered_at      DateTime DEFAULT now()
```

---

## Змінні середовища (.env)

```
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/audioquiz
SECRET_KEY=your-super-secret-jwt-key-min-32-chars
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=480

R2_ACCOUNT_ID=your-cloudflare-account-id
R2_ACCESS_KEY_ID=your-r2-access-key
R2_SECRET_ACCESS_KEY=your-r2-secret-key
R2_BUCKET_NAME=audio-quiz-files
R2_PUBLIC_URL=https://pub-xxxx.r2.dev

ADMIN_EMAIL=admin@company.com
ADMIN_PASSWORD=changeme123
```

---

## Ключові правила для всіх агентів

### Код
- Весь Python код — async/await (SQLAlchemy async session)
- UUID як primary key для всіх моделей (`uuid.uuid4`)
- Pydantic v2 для схем (не v1 синтаксис)
- F-strings для форматування, не `.format()`
- Типізація всюди — `from __future__ import annotations`

### Шаблони
- Завжди наслідуватись від `base.html` через `{% extends "base.html" %}`
- HTMX атрибути: `hx-post`, `hx-get`, `hx-target`, `hx-swap`
- Tailwind класи напряму в HTML — без окремих CSS файлів
- Flash повідомлення через сесію: `request.session["flash"]`

### Безпека
- JWT зберігати ТІЛЬКИ в httpOnly cookie (не localStorage)
- Перевірка ролі через dependency `require_admin` на всіх `/admin/*` роутах
- Паролі — тільки bcrypt, ніколи plain text

### Аудіо
- Приймати: mp3, wav, ogg, m4a, flac
- Зберігати: завжди конвертувати в mp3 128kbps через ffmpeg перед завантаженням в R2
- Ліміт розміру файлу: 50MB
- Ключ в R2: `audio/{quiz_id}/{question_id}.mp3`

### Що НЕ робити
- Не використовувати синхронний SQLAlchemy
- Не зберігати файли локально в продакшені (тільки temp під час конвертації)
- Не комітити .env файл
- Не писати бізнес-логіку в роутерах (тільки в services/)
- Не використовувати `SELECT *` — завжди явні колонки через ORM

---

## Порядок запуску агентів

Агенти мають запускатись ПОСЛІДОВНО — кожен наступний залежить від попереднього.
Дивись AGENTS.md для деталей.
