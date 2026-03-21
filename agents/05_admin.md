# Агент 5 — Admin Panel

> Прочитай CLAUDE.md перед виконанням завдань.
> Залежить від: Агент 2 (моделі), Агент 3 (require_admin dependency), Агент 6 (audio_service для завантаження файлів).
> Примітка: Агент 6 може виконуватись паралельно з цим агентом, але audio_service.upload_audio() повинен існувати до фінального тестування.

---

## Твоє завдання

Створити повну адмін панель:
- Список всіх квізів (published / draft)
- Створення та редагування квізу
- Додавання питань з завантаженням аудіо
- Перегляд результатів стажистів
- Управління користувачами (список + додавання)

---

## Завдання 1 — app/routers/admin.py

```python
from __future__ import annotations
import uuid
from fastapi import APIRouter, Request, Depends, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.dependencies import require_admin
from app.models.user import User
from app.models.quiz import Quiz, Question, AnswerOption
from app.models.result import QuizAttempt
from app.services.auth_service import create_user, get_user_by_email
from app.services.quiz_service import get_quiz_with_questions
from app.services import audio_service

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="app/templates")


# ─── Dashboard ────────────────────────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    quizzes_result = await db.execute(
        select(Quiz).order_by(Quiz.created_at.desc())
    )
    quizzes = list(quizzes_result.scalars().all())

    users_result = await db.execute(
        select(func.count()).select_from(User).where(User.role == "trainee")
    )
    trainee_count = users_result.scalar()

    attempts_result = await db.execute(
        select(func.count()).select_from(QuizAttempt).where(
            QuizAttempt.completed_at != None
        )
    )
    attempts_count = attempts_result.scalar()

    return templates.TemplateResponse("admin/dashboard.html", {
        "request": request,
        "quizzes": quizzes,
        "trainee_count": trainee_count,
        "attempts_count": attempts_count,
        "user": admin,
    })


# ─── Quiz CRUD ────────────────────────────────────────────────────────────────

@router.get("/quiz/new", response_class=HTMLResponse)
async def new_quiz_page(
    request: Request,
    admin: User = Depends(require_admin),
):
    return templates.TemplateResponse("admin/quiz_edit.html", {
        "request": request,
        "quiz": None,
        "user": admin,
    })


@router.post("/quiz/new")
async def create_quiz(
    request: Request,
    title: str = Form(...),
    description: str = Form(""),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    quiz = Quiz(
        title=title.strip(),
        description=description.strip() or None,
        created_by=admin.id,
        is_published=False,
    )
    db.add(quiz)
    await db.flush()
    await db.commit()

    request.session["flash"] = {"type": "success", "message": "Квіз створено!"}
    return RedirectResponse(f"/admin/quiz/{quiz.id}", status_code=303)


@router.get("/quiz/{quiz_id}", response_class=HTMLResponse)
async def edit_quiz_page(
    request: Request,
    quiz_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    quiz = await get_quiz_with_questions(db, quiz_id)
    if not quiz:
        raise HTTPException(status_code=404, detail="Квіз не знайдено")

    return templates.TemplateResponse("admin/quiz_edit.html", {
        "request": request,
        "quiz": quiz,
        "user": admin,
    })


@router.post("/quiz/{quiz_id}/update")
async def update_quiz(
    request: Request,
    quiz_id: uuid.UUID,
    title: str = Form(...),
    description: str = Form(""),
    is_published: bool = Form(False),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    result = await db.execute(select(Quiz).where(Quiz.id == quiz_id))
    quiz = result.scalar_one_or_none()
    if not quiz:
        raise HTTPException(status_code=404)

    quiz.title = title.strip()
    quiz.description = description.strip() or None
    quiz.is_published = is_published
    await db.commit()

    request.session["flash"] = {"type": "success", "message": "Збережено!"}
    return RedirectResponse(f"/admin/quiz/{quiz_id}", status_code=303)


@router.post("/quiz/{quiz_id}/delete")
async def delete_quiz(
    quiz_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    result = await db.execute(
        select(Quiz).where(Quiz.id == quiz_id).options(
            selectinload(Quiz.questions)
        )
    )
    quiz = result.scalar_one_or_none()
    if quiz:
        # Видалити аудіо файли з R2
        for question in quiz.questions:
            await audio_service.delete_audio(question.audio_key)
        await db.delete(quiz)
        await db.commit()

    return RedirectResponse("/admin", status_code=303)


# ─── Question CRUD ─────────────────────────────────────────────────────────────

@router.post("/quiz/{quiz_id}/question/add")
async def add_question(
    request: Request,
    quiz_id: uuid.UUID,
    text: str = Form(...),
    audio_file: UploadFile = File(...),
    option_1: str = Form(...),
    option_2: str = Form(...),
    option_3: str = Form(""),
    option_4: str = Form(""),
    correct_option: int = Form(...),  # 1, 2, 3, або 4
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    quiz = await get_quiz_with_questions(db, quiz_id)
    if not quiz:
        raise HTTPException(status_code=404)

    # Завантажити аудіо
    question_id = uuid.uuid4()
    audio_url, audio_key = await audio_service.upload_audio(
        file=audio_file,
        quiz_id=quiz_id,
        question_id=question_id,
    )

    # Створити питання
    question = Question(
        id=question_id,
        quiz_id=quiz_id,
        text=text.strip(),
        audio_url=audio_url,
        audio_key=audio_key,
        order_index=len(quiz.questions),
    )
    db.add(question)
    await db.flush()

    # Створити варіанти відповідей
    options_text = [option_1, option_2, option_3, option_4]
    for idx, opt_text in enumerate(options_text, start=1):
        if not opt_text.strip():
            continue
        option = AnswerOption(
            question_id=question_id,
            text=opt_text.strip(),
            is_correct=(idx == correct_option),
        )
        db.add(option)

    await db.commit()
    request.session["flash"] = {"type": "success", "message": "Питання додано!"}
    return RedirectResponse(f"/admin/quiz/{quiz_id}", status_code=303)


@router.post("/quiz/{quiz_id}/question/{question_id}/delete")
async def delete_question(
    quiz_id: uuid.UUID,
    question_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    result = await db.execute(select(Question).where(Question.id == question_id))
    question = result.scalar_one_or_none()
    if question:
        await audio_service.delete_audio(question.audio_key)
        await db.delete(question)
        await db.commit()

    return RedirectResponse(f"/admin/quiz/{quiz_id}", status_code=303)


# ─── Results ───────────────────────────────────────────────────────────────────

@router.get("/results", response_class=HTMLResponse)
async def results_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    result = await db.execute(
        select(QuizAttempt)
        .where(QuizAttempt.completed_at != None)
        .options(
            selectinload(QuizAttempt.user),
            selectinload(QuizAttempt.quiz).selectinload(Quiz.questions),
        )
        .order_by(QuizAttempt.completed_at.desc())
    )
    attempts = list(result.scalars().all())

    return templates.TemplateResponse("admin/results.html", {
        "request": request,
        "attempts": attempts,
        "user": admin,
    })


# ─── Users ─────────────────────────────────────────────────────────────────────

@router.get("/users", response_class=HTMLResponse)
async def users_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    result = await db.execute(
        select(User).order_by(User.created_at.desc())
    )
    users = list(result.scalars().all())

    return templates.TemplateResponse("admin/users.html", {
        "request": request,
        "users": users,
        "user": admin,
    })


@router.post("/users/add")
async def add_user(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    existing = await get_user_by_email(db, email)
    if existing:
        request.session["flash"] = {
            "type": "error",
            "message": f"Користувач {email} вже існує",
        }
        return RedirectResponse("/admin/users", status_code=303)

    await create_user(db=db, email=email, name=name, password=password, role="trainee")
    await db.commit()

    request.session["flash"] = {
        "type": "success",
        "message": f"Стажиста {name} додано!",
    }
    return RedirectResponse("/admin/users", status_code=303)
```

---

## Завдання 2 — app/templates/admin/dashboard.html

```html
{% extends "base.html" %}
{% block title %}Адмін панель{% endblock %}

{% block content %}
<div class="flex items-center justify-between mb-8">
    <h1 class="text-2xl font-bold">Адмін панель</h1>
    <a href="/admin/quiz/new"
       class="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition-colors text-sm font-medium">
        + Новий квіз
    </a>
</div>

<!-- Статистика -->
<div class="grid grid-cols-3 gap-4 mb-8">
    <div class="bg-white rounded-xl border border-gray-200 p-5">
        <p class="text-3xl font-bold">{{ quizzes | length }}</p>
        <p class="text-gray-500 text-sm mt-1">Квізів</p>
    </div>
    <div class="bg-white rounded-xl border border-gray-200 p-5">
        <p class="text-3xl font-bold">{{ trainee_count }}</p>
        <p class="text-gray-500 text-sm mt-1">Стажистів</p>
    </div>
    <div class="bg-white rounded-xl border border-gray-200 p-5">
        <p class="text-3xl font-bold">{{ attempts_count }}</p>
        <p class="text-gray-500 text-sm mt-1">Пройдених квізів</p>
    </div>
</div>

<!-- Навігація -->
<div class="flex gap-2 mb-6 text-sm">
    <a href="/admin/results" class="px-4 py-2 border border-gray-200 rounded-lg hover:bg-gray-50">
        📊 Результати
    </a>
    <a href="/admin/users" class="px-4 py-2 border border-gray-200 rounded-lg hover:bg-gray-50">
        👥 Користувачі
    </a>
</div>

<!-- Список квізів -->
<div class="bg-white rounded-xl border border-gray-200 overflow-hidden">
    {% if quizzes %}
    <table class="w-full text-sm">
        <thead class="bg-gray-50 border-b border-gray-200">
            <tr>
                <th class="text-left px-6 py-3 text-gray-500 font-medium">Назва</th>
                <th class="text-left px-6 py-3 text-gray-500 font-medium">Питань</th>
                <th class="text-left px-6 py-3 text-gray-500 font-medium">Статус</th>
                <th class="text-left px-6 py-3 text-gray-500 font-medium">Дії</th>
            </tr>
        </thead>
        <tbody class="divide-y divide-gray-100">
            {% for quiz in quizzes %}
            <tr class="hover:bg-gray-50">
                <td class="px-6 py-4 font-medium">{{ quiz.title }}</td>
                <td class="px-6 py-4 text-gray-400">{{ quiz.questions | length }}</td>
                <td class="px-6 py-4">
                    {% if quiz.is_published %}
                    <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-700">
                        Опубліковано
                    </span>
                    {% else %}
                    <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-600">
                        Чернетка
                    </span>
                    {% endif %}
                </td>
                <td class="px-6 py-4">
                    <a href="/admin/quiz/{{ quiz.id }}"
                       class="text-blue-600 hover:underline mr-3">Редагувати</a>
                    <form action="/admin/quiz/{{ quiz.id }}/delete" method="post" class="inline"
                          onsubmit="return confirm('Видалити квіз та всі питання?')">
                        <button type="submit" class="text-red-500 hover:underline">Видалити</button>
                    </form>
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
    {% else %}
    <div class="text-center py-12 text-gray-400">
        <p class="text-3xl mb-3">📝</p>
        <p>Квізів ще немає. <a href="/admin/quiz/new" class="text-blue-600 hover:underline">Створити перший</a></p>
    </div>
    {% endif %}
</div>
{% endblock %}
```

---

## Завдання 3 — app/templates/admin/quiz_edit.html

```html
{% extends "base.html" %}
{% block title %}{% if quiz %}Редагування{% else %}Новий квіз{% endif %}{% endblock %}

{% block content %}
<div class="max-w-3xl">
    <div class="flex items-center gap-3 mb-8">
        <a href="/admin" class="text-gray-400 hover:text-gray-600">← Назад</a>
        <h1 class="text-2xl font-bold">
            {% if quiz %}{{ quiz.title }}{% else %}Новий квіз{% endif %}
        </h1>
    </div>

    <!-- Форма квізу -->
    <div class="bg-white rounded-xl border border-gray-200 p-6 mb-6">
        <h2 class="font-semibold mb-4">Загальна інформація</h2>
        <form action="{% if quiz %}/admin/quiz/{{ quiz.id }}/update{% else %}/admin/quiz/new{% endif %}"
              method="post" class="space-y-4">
            <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Назва квізу</label>
                <input type="text" name="title" required
                       value="{{ quiz.title if quiz else '' }}"
                       class="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none">
            </div>
            <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Опис (необов'язково)</label>
                <textarea name="description" rows="2"
                          class="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none">{{ quiz.description if quiz else '' }}</textarea>
            </div>
            {% if quiz %}
            <div class="flex items-center gap-2">
                <input type="checkbox" id="is_published" name="is_published" value="true"
                       {% if quiz.is_published %}checked{% endif %}
                       class="w-4 h-4 text-blue-600">
                <label for="is_published" class="text-sm text-gray-700">
                    Опублікувати (стажисти побачать цей квіз)
                </label>
            </div>
            {% endif %}
            <button type="submit"
                    class="bg-blue-600 text-white px-5 py-2 rounded-lg hover:bg-blue-700 transition-colors text-sm font-medium">
                {% if quiz %}Зберегти зміни{% else %}Створити квіз{% endif %}
            </button>
        </form>
    </div>

    {% if quiz %}
    <!-- Список питань -->
    <div class="bg-white rounded-xl border border-gray-200 p-6 mb-6">
        <h2 class="font-semibold mb-4">Питання ({{ quiz.questions | length }})</h2>

        {% if quiz.questions %}
        <div class="space-y-3 mb-6">
            {% for question in quiz.questions %}
            <div class="flex items-start gap-3 p-4 bg-gray-50 rounded-xl">
                <span class="text-gray-400 text-sm font-mono mt-0.5">{{ loop.index }}</span>
                <div class="flex-1">
                    <p class="font-medium text-sm mb-1">{{ question.text }}</p>
                    <audio controls src="{{ question.audio_url }}" class="w-full h-8 mt-2"></audio>
                    <div class="flex gap-2 mt-2 flex-wrap">
                        {% for option in question.options %}
                        <span class="text-xs px-2 py-1 rounded
                            {% if option.is_correct %}bg-green-100 text-green-700
                            {% else %}bg-gray-200 text-gray-600{% endif %}">
                            {% if option.is_correct %}✓ {% endif %}{{ option.text }}
                        </span>
                        {% endfor %}
                    </div>
                </div>
                <form action="/admin/quiz/{{ quiz.id }}/question/{{ question.id }}/delete"
                      method="post"
                      onsubmit="return confirm('Видалити це питання?')">
                    <button type="submit" class="text-red-400 hover:text-red-600 text-sm">×</button>
                </form>
            </div>
            {% endfor %}
        </div>
        {% endif %}

        <!-- Форма нового питання -->
        <h3 class="font-medium text-sm text-gray-700 mb-3">+ Додати питання</h3>
        <form action="/admin/quiz/{{ quiz.id }}/question/add"
              method="post"
              enctype="multipart/form-data"
              class="space-y-4 border border-gray-200 rounded-xl p-4">

            <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">
                    Текст питання / інструкція
                </label>
                <input type="text" name="text" required placeholder="Наприклад: Яке слово вимовляє диктор?"
                       class="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none text-sm">
            </div>

            <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">
                    Аудіофайл (mp3, wav, ogg, m4a — до 50 МБ)
                </label>
                <input type="file" name="audio_file" required
                       accept="audio/mpeg,audio/wav,audio/ogg,audio/mp4,audio/x-m4a"
                       class="w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100">
            </div>

            <div class="grid grid-cols-2 gap-3">
                <div>
                    <label class="block text-xs font-medium text-gray-600 mb-1">Варіант 1 *</label>
                    <input type="text" name="option_1" required
                           class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none">
                </div>
                <div>
                    <label class="block text-xs font-medium text-gray-600 mb-1">Варіант 2 *</label>
                    <input type="text" name="option_2" required
                           class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none">
                </div>
                <div>
                    <label class="block text-xs font-medium text-gray-600 mb-1">Варіант 3</label>
                    <input type="text" name="option_3"
                           class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none">
                </div>
                <div>
                    <label class="block text-xs font-medium text-gray-600 mb-1">Варіант 4</label>
                    <input type="text" name="option_4"
                           class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none">
                </div>
            </div>

            <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Правильна відповідь</label>
                <select name="correct_option" required
                        class="px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none">
                    <option value="1">Варіант 1</option>
                    <option value="2">Варіант 2</option>
                    <option value="3">Варіант 3</option>
                    <option value="4">Варіант 4</option>
                </select>
            </div>

            <button type="submit"
                    class="bg-green-600 text-white px-5 py-2 rounded-lg hover:bg-green-700 transition-colors text-sm font-medium">
                Додати питання
            </button>
        </form>
    </div>
    {% endif %}
</div>
{% endblock %}
```

---

## Завдання 4 — app/templates/admin/results.html

```html
{% extends "base.html" %}
{% block title %}Результати{% endblock %}

{% block content %}
<div class="flex items-center gap-3 mb-6">
    <a href="/admin" class="text-gray-400 hover:text-gray-600">← Назад</a>
    <h1 class="text-2xl font-bold">Результати стажистів</h1>
</div>

<div class="bg-white rounded-xl border border-gray-200 overflow-hidden">
    {% if attempts %}
    <table class="w-full text-sm">
        <thead class="bg-gray-50 border-b border-gray-200">
            <tr>
                <th class="text-left px-6 py-3 text-gray-500 font-medium">Стажист</th>
                <th class="text-left px-6 py-3 text-gray-500 font-medium">Квіз</th>
                <th class="text-left px-6 py-3 text-gray-500 font-medium">Результат</th>
                <th class="text-left px-6 py-3 text-gray-500 font-medium">Дата</th>
            </tr>
        </thead>
        <tbody class="divide-y divide-gray-100">
            {% for attempt in attempts %}
            {% set total = attempt.quiz.questions | length %}
            {% set pct = (attempt.score / total * 100) | int if total > 0 else 0 %}
            <tr class="hover:bg-gray-50">
                <td class="px-6 py-4">
                    <p class="font-medium">{{ attempt.user.name }}</p>
                    <p class="text-gray-400 text-xs">{{ attempt.user.email }}</p>
                </td>
                <td class="px-6 py-4">{{ attempt.quiz.title }}</td>
                <td class="px-6 py-4">
                    <span class="font-semibold
                        {% if pct >= 80 %}text-green-600
                        {% elif pct >= 60 %}text-blue-600
                        {% else %}text-orange-500{% endif %}">
                        {{ pct }}%
                    </span>
                    <span class="text-gray-400 text-xs ml-1">({{ attempt.score }}/{{ total }})</span>
                </td>
                <td class="px-6 py-4 text-gray-400">
                    {{ attempt.completed_at.strftime('%d.%m.%Y %H:%M') }}
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
    {% else %}
    <div class="text-center py-12 text-gray-400">
        <p class="text-3xl mb-3">📊</p>
        <p>Стажисти ще не проходили квізів</p>
    </div>
    {% endif %}
</div>
{% endblock %}
```

---

## Завдання 5 — app/templates/admin/users.html

```html
{% extends "base.html" %}
{% block title %}Користувачі{% endblock %}

{% block content %}
<div class="flex items-center justify-between mb-6">
    <div class="flex items-center gap-3">
        <a href="/admin" class="text-gray-400 hover:text-gray-600">← Назад</a>
        <h1 class="text-2xl font-bold">Користувачі</h1>
    </div>
</div>

<div class="grid grid-cols-3 gap-6">
    <!-- Список -->
    <div class="col-span-2 bg-white rounded-xl border border-gray-200 overflow-hidden">
        <table class="w-full text-sm">
            <thead class="bg-gray-50 border-b border-gray-200">
                <tr>
                    <th class="text-left px-6 py-3 text-gray-500 font-medium">Ім'я</th>
                    <th class="text-left px-6 py-3 text-gray-500 font-medium">Email</th>
                    <th class="text-left px-6 py-3 text-gray-500 font-medium">Роль</th>
                </tr>
            </thead>
            <tbody class="divide-y divide-gray-100">
                {% for u in users %}
                <tr class="hover:bg-gray-50">
                    <td class="px-6 py-4 font-medium">{{ u.name }}</td>
                    <td class="px-6 py-4 text-gray-500">{{ u.email }}</td>
                    <td class="px-6 py-4">
                        {% if u.role == 'admin' %}
                        <span class="px-2 py-0.5 bg-purple-100 text-purple-700 rounded text-xs font-medium">Адмін</span>
                        {% else %}
                        <span class="px-2 py-0.5 bg-gray-100 text-gray-600 rounded text-xs">Стажист</span>
                        {% endif %}
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>

    <!-- Форма додавання -->
    <div class="bg-white rounded-xl border border-gray-200 p-6 h-fit">
        <h2 class="font-semibold mb-4">Додати стажиста</h2>
        <form action="/admin/users/add" method="post" class="space-y-3">
            <div>
                <label class="block text-xs font-medium text-gray-600 mb-1">Ім'я</label>
                <input type="text" name="name" required
                       class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none">
            </div>
            <div>
                <label class="block text-xs font-medium text-gray-600 mb-1">Email</label>
                <input type="email" name="email" required
                       class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none">
            </div>
            <div>
                <label class="block text-xs font-medium text-gray-600 mb-1">Тимчасовий пароль</label>
                <input type="text" name="password" required
                       class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none">
            </div>
            <button type="submit"
                    class="w-full bg-blue-600 text-white py-2 rounded-lg hover:bg-blue-700 transition-colors text-sm font-medium">
                Додати
            </button>
        </form>
    </div>
</div>
{% endblock %}
```

---

## Завдання 6 — Оновити app/main.py

```python
from app.routers import auth, trainee, admin

app.include_router(auth.router)
app.include_router(trainee.router)
app.include_router(admin.router)
```

---

## Перевірка після виконання

1. `uvicorn app.main:app --reload`
2. Увійди як адмін → `/admin` — бачиш дашборд
3. Створи тестовий квіз → `/admin/quiz/new`
4. Перевір `/admin/results` та `/admin/users`
5. Переконайся що `/admin` недоступний для trainee (403)
