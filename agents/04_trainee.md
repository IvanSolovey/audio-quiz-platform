# Агент 4 — Trainee Interface

> Прочитай CLAUDE.md перед виконанням завдань.
> Залежить від: Агент 2 (моделі), Агент 3 (автентифікація, dependencies).

---

## Твоє завдання

Створити весь інтерфейс стажиста:
- Дашборд зі списком доступних квізів
- Сторінка проходження квізу з аудіоплеєром та HTMX
- Сторінка результатів
- Сторінка особистого прогресу

---

## Завдання 1 — app/services/quiz_service.py

```python
from __future__ import annotations
import uuid
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.quiz import Quiz, Question, AnswerOption


async def get_published_quizzes(db: AsyncSession) -> list[Quiz]:
    result = await db.execute(
        select(Quiz)
        .where(Quiz.is_published == True)
        .order_by(Quiz.created_at.desc())
    )
    return list(result.scalars().all())


async def get_quiz_with_questions(
    db: AsyncSession, quiz_id: uuid.UUID
) -> Quiz | None:
    result = await db.execute(
        select(Quiz)
        .where(Quiz.id == quiz_id)
        .options(
            selectinload(Quiz.questions).selectinload(Question.options)
        )
    )
    return result.scalar_one_or_none()


async def get_question_with_options(
    db: AsyncSession, question_id: uuid.UUID
) -> Question | None:
    result = await db.execute(
        select(Question)
        .where(Question.id == question_id)
        .options(selectinload(Question.options))
    )
    return result.scalar_one_or_none()
```

---

## Завдання 2 — app/services/result_service.py

```python
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.quiz import AnswerOption, Question
from app.models.result import QuizAttempt, AttemptAnswer


async def start_attempt(
    db: AsyncSession, user_id: uuid.UUID, quiz_id: uuid.UUID
) -> QuizAttempt:
    # Перевірити чи є незавершена спроба
    existing = await db.execute(
        select(QuizAttempt).where(
            QuizAttempt.user_id == user_id,
            QuizAttempt.quiz_id == quiz_id,
            QuizAttempt.completed_at == None,
        )
    )
    attempt = existing.scalar_one_or_none()
    if attempt:
        return attempt

    attempt = QuizAttempt(user_id=user_id, quiz_id=quiz_id)
    db.add(attempt)
    await db.flush()
    await db.refresh(attempt)
    return attempt


async def save_answer(
    db: AsyncSession,
    attempt_id: uuid.UUID,
    question_id: uuid.UUID,
    selected_option_id: uuid.UUID,
) -> tuple[AttemptAnswer, bool]:
    # Перевірити правильність
    option_result = await db.execute(
        select(AnswerOption).where(AnswerOption.id == selected_option_id)
    )
    option = option_result.scalar_one()
    is_correct = option.is_correct

    answer = AttemptAnswer(
        attempt_id=attempt_id,
        question_id=question_id,
        selected_option_id=selected_option_id,
        is_correct=is_correct,
    )
    db.add(answer)
    await db.flush()
    return answer, is_correct


async def complete_attempt(
    db: AsyncSession, attempt_id: uuid.UUID
) -> QuizAttempt:
    result = await db.execute(
        select(QuizAttempt)
        .where(QuizAttempt.id == attempt_id)
        .options(selectinload(QuizAttempt.answers))
    )
    attempt = result.scalar_one()

    correct_count = sum(1 for a in attempt.answers if a.is_correct)
    attempt.score = correct_count
    attempt.completed_at = datetime.now(timezone.utc)

    await db.flush()
    await db.refresh(attempt)
    return attempt


async def get_user_progress(
    db: AsyncSession, user_id: uuid.UUID
) -> list[QuizAttempt]:
    result = await db.execute(
        select(QuizAttempt)
        .where(
            QuizAttempt.user_id == user_id,
            QuizAttempt.completed_at != None,
        )
        .options(selectinload(QuizAttempt.quiz))
        .order_by(QuizAttempt.completed_at.desc())
    )
    return list(result.scalars().all())


async def get_answered_question_ids(
    db: AsyncSession, attempt_id: uuid.UUID
) -> list[uuid.UUID]:
    result = await db.execute(
        select(AttemptAnswer.question_id).where(
            AttemptAnswer.attempt_id == attempt_id
        )
    )
    return [row[0] for row in result.all()]
```

---

## Завдання 3 — app/routers/trainee.py

```python
from __future__ import annotations
import uuid
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.dependencies import require_user
from app.models.user import User
from app.services import quiz_service, result_service

router = APIRouter(tags=["trainee"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    quizzes = await quiz_service.get_published_quizzes(db)
    return templates.TemplateResponse("trainee/dashboard.html", {
        "request": request,
        "quizzes": quizzes,
        "user": current_user,
    })


@router.get("/quiz/{quiz_id}", response_class=HTMLResponse)
async def quiz_page(
    request: Request,
    quiz_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    quiz = await quiz_service.get_quiz_with_questions(db, quiz_id)
    if not quiz or not quiz.is_published:
        return RedirectResponse("/dashboard", status_code=303)

    # Стартуємо або відновлюємо спробу
    attempt = await result_service.start_attempt(db, current_user.id, quiz_id)
    await db.commit()

    # Знаходимо перше питання без відповіді
    answered_ids = await result_service.get_answered_question_ids(db, attempt.id)
    unanswered = [q for q in quiz.questions if q.id not in answered_ids]

    if not unanswered:
        # Всі питання вже answered — завершити і показати результат
        completed = await result_service.complete_attempt(db, attempt.id)
        await db.commit()
        return RedirectResponse(f"/quiz/{quiz_id}/result/{attempt.id}", status_code=303)

    current_question = unanswered[0]
    progress = len(answered_ids)
    total = len(quiz.questions)

    return templates.TemplateResponse("trainee/quiz.html", {
        "request": request,
        "quiz": quiz,
        "question": current_question,
        "attempt_id": str(attempt.id),
        "progress": progress,
        "total": total,
        "user": current_user,
    })


@router.post("/quiz/{quiz_id}/answer", response_class=HTMLResponse)
async def submit_answer(
    request: Request,
    quiz_id: uuid.UUID,
    attempt_id: str = Form(...),
    question_id: str = Form(...),
    option_id: str = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    attempt_uuid = uuid.UUID(attempt_id)
    question_uuid = uuid.UUID(question_id)
    option_uuid = uuid.UUID(option_id)

    # Зберегти відповідь
    _, is_correct = await result_service.save_answer(
        db, attempt_uuid, question_uuid, option_uuid
    )
    await db.commit()

    # Знайти наступне питання
    quiz = await quiz_service.get_quiz_with_questions(db, quiz_id)
    answered_ids = await result_service.get_answered_question_ids(db, attempt_uuid)
    unanswered = [q for q in quiz.questions if q.id not in answered_ids]

    if not unanswered:
        # Квіз завершено
        completed = await result_service.complete_attempt(db, attempt_uuid)
        await db.commit()

        # HTMX фрагмент — редирект через hx-redirect header
        response = HTMLResponse("")
        response.headers["HX-Redirect"] = f"/quiz/{quiz_id}/result/{attempt_uuid}"
        return response

    # Повернути фрагмент наступного питання
    next_question = unanswered[0]
    progress = len(answered_ids)
    total = len(quiz.questions)

    return templates.TemplateResponse("partials/question.html", {
        "request": request,
        "quiz": quiz,
        "question": next_question,
        "attempt_id": attempt_id,
        "progress": progress,
        "total": total,
        "is_correct": is_correct,
    })


@router.get("/quiz/{quiz_id}/result/{attempt_id}", response_class=HTMLResponse)
async def quiz_result(
    request: Request,
    quiz_id: uuid.UUID,
    attempt_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    from sqlalchemy.orm import selectinload
    from sqlalchemy import select
    from app.models.result import QuizAttempt

    result = await db.execute(
        select(QuizAttempt)
        .where(QuizAttempt.id == attempt_id)
        .options(
            selectinload(QuizAttempt.answers),
            selectinload(QuizAttempt.quiz),
        )
    )
    attempt = result.scalar_one_or_none()
    quiz = await quiz_service.get_quiz_with_questions(db, quiz_id)

    total = len(quiz.questions)
    score = attempt.score or 0
    percent = round(score / total * 100) if total > 0 else 0

    return templates.TemplateResponse("trainee/result.html", {
        "request": request,
        "quiz": quiz,
        "attempt": attempt,
        "score": score,
        "total": total,
        "percent": percent,
        "user": current_user,
    })


@router.get("/progress", response_class=HTMLResponse)
async def progress_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    attempts = await result_service.get_user_progress(db, current_user.id)
    return templates.TemplateResponse("trainee/progress.html", {
        "request": request,
        "attempts": attempts,
        "user": current_user,
    })
```

---

## Завдання 4 — app/templates/trainee/dashboard.html

```html
{% extends "base.html" %}
{% block title %}Квізи{% endblock %}

{% block content %}
<h1 class="text-2xl font-bold mb-6">Доступні квізи</h1>

{% if quizzes %}
<div class="grid gap-4 sm:grid-cols-2">
    {% for quiz in quizzes %}
    <a href="/quiz/{{ quiz.id }}"
       class="block bg-white border border-gray-200 rounded-xl p-6 hover:border-blue-400 hover:shadow-sm transition-all">
        <div class="flex items-start justify-between">
            <div>
                <h2 class="font-semibold text-lg mb-1">{{ quiz.title }}</h2>
                {% if quiz.description %}
                <p class="text-gray-500 text-sm">{{ quiz.description }}</p>
                {% endif %}
            </div>
            <span class="text-2xl">🎧</span>
        </div>
        <div class="mt-4 text-sm text-gray-400">
            {{ quiz.questions | length }} питань
        </div>
    </a>
    {% endfor %}
</div>
{% else %}
<div class="text-center py-16 text-gray-400">
    <p class="text-4xl mb-4">🎯</p>
    <p>Квізів поки немає. Зачекай поки адміністратор додасть матеріали.</p>
</div>
{% endif %}
{% endblock %}
```

---

## Завдання 5 — app/templates/trainee/quiz.html

```html
{% extends "base.html" %}
{% block title %}{{ quiz.title }}{% endblock %}

{% block content %}
<div class="max-w-2xl mx-auto">
    <!-- Заголовок і прогрес -->
    <div class="mb-6">
        <h1 class="text-xl font-bold mb-3">{{ quiz.title }}</h1>
        <div class="flex items-center gap-3 text-sm text-gray-500">
            <span>Питання {{ progress + 1 }} з {{ total }}</span>
            <div class="flex-1 bg-gray-200 rounded-full h-2">
                <div class="bg-blue-500 h-2 rounded-full transition-all"
                     style="width: {{ (progress / total * 100) | int }}%"></div>
            </div>
        </div>
    </div>

    <!-- Контейнер питання (HTMX замінює цей блок) -->
    <div id="quiz-container">
        {% include "partials/question.html" %}
    </div>
</div>
{% endblock %}
```

---

## Завдання 6 — app/templates/partials/question.html

```html
<div class="bg-white rounded-2xl border border-gray-200 p-6">
    <!-- Текст питання -->
    <p class="text-gray-700 mb-5 font-medium">{{ question.text }}</p>

    <!-- Аудіоплеєр -->
    <div class="mb-6 p-4 bg-gray-50 rounded-xl">
        <p class="text-xs text-gray-400 mb-2 uppercase tracking-wide">Прослухай аудіо</p>
        <audio
            id="audio-player"
            controls
            preload="metadata"
            class="w-full"
            src="{{ question.audio_url }}">
            Ваш браузер не підтримує аудіо.
        </audio>
    </div>

    <!-- Варіанти відповідей — заблоковані до кінця аудіо -->
    <div id="answers" class="space-y-3 opacity-40 pointer-events-none transition-opacity duration-300">
        <p class="text-xs text-gray-400 mb-3">↑ Спочатку прослухай аудіо</p>
        {% for option in question.options %}
        <button
            hx-post="/quiz/{{ quiz.id }}/answer"
            hx-target="#quiz-container"
            hx-swap="innerHTML"
            hx-include="#attempt-data"
            hx-vals='{"question_id": "{{ question.id }}", "option_id": "{{ option.id }}"}'
            class="w-full text-left px-4 py-3 border border-gray-200 rounded-xl
                   hover:border-blue-400 hover:bg-blue-50 transition-all font-medium">
            {{ option.text }}
        </button>
        {% endfor %}
    </div>

    <!-- Приховані дані спроби -->
    <div id="attempt-data">
        <input type="hidden" name="attempt_id" value="{{ attempt_id }}">
    </div>
</div>

<!-- Розблокування після прослуховування -->
<script>
(function() {
    const audio = document.getElementById('audio-player');
    const answers = document.getElementById('answers');

    if (audio && answers) {
        audio.addEventListener('ended', function() {
            answers.classList.remove('opacity-40', 'pointer-events-none');
            answers.querySelector('p').remove(); // прибрати підказку
        });
    }
})();
</script>
```

---

## Завдання 7 — app/templates/trainee/result.html

```html
{% extends "base.html" %}
{% block title %}Результат{% endblock %}

{% block content %}
<div class="max-w-lg mx-auto text-center">
    <div class="bg-white rounded-2xl border border-gray-200 p-8">
        {% if percent >= 80 %}
            <div class="text-6xl mb-4">🏆</div>
            <h1 class="text-2xl font-bold mb-2 text-green-600">Відмінно!</h1>
        {% elif percent >= 60 %}
            <div class="text-6xl mb-4">👍</div>
            <h1 class="text-2xl font-bold mb-2 text-blue-600">Добре!</h1>
        {% else %}
            <div class="text-6xl mb-4">📚</div>
            <h1 class="text-2xl font-bold mb-2 text-orange-500">Варто повторити</h1>
        {% endif %}

        <p class="text-gray-500 mb-6">{{ quiz.title }}</p>

        <div class="text-5xl font-bold mb-2">{{ percent }}%</div>
        <p class="text-gray-400 mb-8">{{ score }} з {{ total }} правильних відповідей</p>

        <div class="flex gap-3 justify-center">
            <a href="/dashboard"
               class="px-6 py-2.5 border border-gray-200 rounded-xl hover:bg-gray-50 transition-colors">
                До списку квізів
            </a>
            <a href="/progress"
               class="px-6 py-2.5 bg-blue-600 text-white rounded-xl hover:bg-blue-700 transition-colors">
                Мій прогрес
            </a>
        </div>
    </div>
</div>
{% endblock %}
```

---

## Завдання 8 — app/templates/trainee/progress.html

```html
{% extends "base.html" %}
{% block title %}Мій прогрес{% endblock %}

{% block content %}
<h1 class="text-2xl font-bold mb-6">Мій прогрес</h1>

{% if attempts %}
<div class="bg-white rounded-xl border border-gray-200 overflow-hidden">
    <table class="w-full text-sm">
        <thead class="bg-gray-50 border-b border-gray-200">
            <tr>
                <th class="text-left px-6 py-3 text-gray-500 font-medium">Квіз</th>
                <th class="text-left px-6 py-3 text-gray-500 font-medium">Результат</th>
                <th class="text-left px-6 py-3 text-gray-500 font-medium">Дата</th>
            </tr>
        </thead>
        <tbody class="divide-y divide-gray-100">
            {% for attempt in attempts %}
            <tr class="hover:bg-gray-50">
                <td class="px-6 py-4 font-medium">{{ attempt.quiz.title }}</td>
                <td class="px-6 py-4">
                    {% set total = attempt.quiz.questions | length %}
                    {% set pct = (attempt.score / total * 100) | int if total > 0 else 0 %}
                    <span class="inline-flex items-center gap-1.5">
                        <span class="font-semibold
                            {% if pct >= 80 %}text-green-600
                            {% elif pct >= 60 %}text-blue-600
                            {% else %}text-orange-500{% endif %}">
                            {{ pct }}%
                        </span>
                        <span class="text-gray-400">({{ attempt.score }}/{{ total }})</span>
                    </span>
                </td>
                <td class="px-6 py-4 text-gray-400">
                    {{ attempt.completed_at.strftime('%d.%m.%Y %H:%M') }}
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>
{% else %}
<div class="text-center py-16 text-gray-400">
    <p class="text-4xl mb-4">📊</p>
    <p>Ти ще не проходив жодного квізу.</p>
    <a href="/dashboard" class="text-blue-600 hover:underline mt-2 block">Почати зараз</a>
</div>
{% endif %}
{% endblock %}
```

---

## Завдання 9 — Оновити app/main.py

Додати роутер trainee:

```python
from app.routers import auth, trainee

app.include_router(auth.router)
app.include_router(trainee.router)

# Редирект з кореня на дашборд
@app.get("/")
async def root():
    from fastapi.responses import RedirectResponse
    return RedirectResponse("/dashboard")
```

---

## Перевірка після виконання

1. `uvicorn app.main:app --reload`
2. Відкрий http://localhost:8000 → редирект на `/login`
3. Увійди → редирект на `/dashboard`
4. Якщо немає квізів — бачиш порожній стан
5. Відкрий `/progress` → порожня таблиця (ок)

---

## Що НЕ робить цей агент

- Не створює адмін панель (→ Агент 5)
- Не налаштовує завантаження реальних аудіо файлів (→ Агент 6)
- Квіз з тестовим аудіо можна додати вручну через psql для перевірки
