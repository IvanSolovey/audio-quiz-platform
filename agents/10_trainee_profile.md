# Агент 10 — Trainee Profile & Statistics

> Прочитай CLAUDE.md перед виконанням.
> Залежить від: Агенти 1-5, Агент 9 (permissions).

---

## Огляд

Замість таблиці результатів — повноцінна картка стажиста з:
- Загальною статистикою (пройдено квізів, середній бал, кращий результат)
- Прогрес-барами по кожному квізу
- Хронологією спроб
- Резервним місцем для графіка (Chart.js — фаза 2)
- Доступ через `/admin/trainees/{user_id}`

---

## Завдання 1 — app/services/result_service.py

Додай нові функції статистики в кінець файлу:

```python
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

async def get_trainee_statistics(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    """
    Повна статистика стажиста для профілю.
    Повертає dict з усіма метриками.
    """
    from app.models.quiz import Quiz, Question

    # Всі завершені спроби
    attempts_result = await db.execute(
        select(QuizAttempt)
        .where(
            QuizAttempt.user_id == user_id,
            QuizAttempt.completed_at != None,
        )
        .options(
            selectinload(QuizAttempt.quiz).selectinload(Quiz.questions),
            selectinload(QuizAttempt.answers),
        )
        .order_by(QuizAttempt.completed_at.desc())
    )
    attempts = list(attempts_result.scalars().all())

    if not attempts:
        return {
            "total_attempts": 0,
            "unique_quizzes": 0,
            "average_score": None,
            "best_score": None,
            "worst_score": None,
            "attempts": [],
            "quiz_stats": [],
            "recent_activity": None,
        }

    # Базові метрики
    scores = []
    for attempt in attempts:
        total_q = len(attempt.quiz.questions)
        if total_q > 0 and attempt.score is not None:
            scores.append(round(attempt.score / total_q * 100, 1))

    # Групування по квізах (найкращий результат по кожному)
    quiz_best: dict[uuid.UUID, dict] = {}
    for attempt in attempts:
        qid = attempt.quiz_id
        total_q = len(attempt.quiz.questions)
        pct = round(attempt.score / total_q * 100, 1) if total_q > 0 and attempt.score is not None else 0

        if qid not in quiz_best or pct > quiz_best[qid]["best_pct"]:
            quiz_best[qid] = {
                "quiz_id": qid,
                "quiz_title": attempt.quiz.title,
                "best_pct": pct,
                "attempts_count": 0,
                "last_attempt": attempt.completed_at,
            }
        quiz_best[qid]["attempts_count"] += 1

    quiz_stats = sorted(
        quiz_best.values(),
        key=lambda x: x["best_pct"],
        reverse=True,
    )

    return {
        "total_attempts": len(attempts),
        "unique_quizzes": len(quiz_best),
        "average_score": round(sum(scores) / len(scores), 1) if scores else None,
        "best_score": max(scores) if scores else None,
        "worst_score": min(scores) if scores else None,
        "attempts": attempts,          # повна хронологія
        "quiz_stats": quiz_stats,      # найкращі результати по квізах
        "recent_activity": attempts[0].completed_at if attempts else None,
    }


async def get_all_trainees_with_stats(
    db: AsyncSession,
) -> list[dict]:
    """
    Список всіх стажистів зі зведеною статистикою.
    Для таблиці в адмін панелі.
    """
    from app.models.quiz import Quiz

    # Всі стажисти
    users_result = await db.execute(
        select(User)
        .where(User.role == "trainee")
        .order_by(User.name)
    )
    trainees = list(users_result.scalars().all())

    result = []
    for trainee in trainees:
        # Кількість завершених спроб
        count_result = await db.execute(
            select(func.count())
            .select_from(QuizAttempt)
            .where(
                QuizAttempt.user_id == trainee.id,
                QuizAttempt.completed_at != None,
            )
        )
        attempts_count = count_result.scalar() or 0

        # Середній бал (якщо є спроби)
        avg_score = None
        last_activity = None

        if attempts_count > 0:
            attempts_data = await db.execute(
                select(QuizAttempt)
                .where(
                    QuizAttempt.user_id == trainee.id,
                    QuizAttempt.completed_at != None,
                )
                .options(
                    selectinload(QuizAttempt.quiz).selectinload(Quiz.questions)
                )
                .order_by(QuizAttempt.completed_at.desc())
            )
            all_attempts = list(attempts_data.scalars().all())

            scores = []
            for a in all_attempts:
                total_q = len(a.quiz.questions)
                if total_q > 0 and a.score is not None:
                    scores.append(a.score / total_q * 100)

            if scores:
                avg_score = round(sum(scores) / len(scores), 1)

            last_activity = all_attempts[0].completed_at if all_attempts else None

        result.append({
            "user": trainee,
            "attempts_count": attempts_count,
            "avg_score": avg_score,
            "last_activity": last_activity,
        })

    return result
```

---

## Завдання 2 — Оновити app/routers/admin.py

Заміни старий `/results` і `/users` на нові ендпоінти:

```python
from app.services.result_service import get_all_trainees_with_stats, get_trainee_statistics
from app.models.user import User as UserModel

# Замінити старий results_page на:
@router.get("/trainees", response_class=HTMLResponse)
async def trainees_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: UserModel = Depends(require_permission("view_results")),
):
    """Список всіх стажистів з короткою статистикою."""
    trainees_data = await get_all_trainees_with_stats(db)

    return templates.TemplateResponse("admin/trainees.html", {
        "request": request,
        "trainees_data": trainees_data,
        "user": admin,
    })


@router.get("/trainees/{user_id}", response_class=HTMLResponse)
async def trainee_profile(
    request: Request,
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: UserModel = Depends(require_permission("view_results")),
):
    """Детальний профіль стажиста."""
    from sqlalchemy import select
    result = await db.execute(
        select(UserModel).where(UserModel.id == user_id)
    )
    trainee = result.scalar_one_or_none()

    if not trainee or trainee.role != "trainee":
        raise HTTPException(status_code=404, detail="Стажиста не знайдено")

    stats = await get_trainee_statistics(db, user_id)

    return templates.TemplateResponse("admin/trainee_profile.html", {
        "request": request,
        "trainee": trainee,
        "stats": stats,
        "user": admin,
    })
```

Також оновити посилання в `admin/dashboard.html` — `/admin/results` → `/admin/trainees`.

---

## Завдання 3 — app/templates/admin/trainees.html

```html
{% extends "base.html" %}
{% block title %}Стажери{% endblock %}

{% block content %}
<div class="flex items-center justify-between mb-8">
  <div class="flex items-center gap-3">
    <a href="/admin" class="text-sm hover:underline"
       style="color: var(--color-text-muted);">← Адмін панель</a>
    <h1 class="text-2xl font-bold" style="font-family: var(--font-display);">
      👥 Стажери
    </h1>
  </div>
  {% if user.has_permission('manage_users') %}
  <a href="/admin/users"
     class="px-4 py-2 rounded-xl text-sm font-semibold text-white"
     style="background: var(--color-primary);">
    + Додати стажиста
  </a>
  {% endif %}
</div>

{% if trainees_data %}
<div class="rounded-2xl overflow-hidden"
     style="background: var(--color-surface);
            border: 1px solid var(--color-border);
            box-shadow: var(--shadow-sm);">
  <table class="w-full text-sm">
    <thead style="background: var(--color-bg);
                  border-bottom: 2px solid var(--color-border);">
      <tr>
        <th class="text-left px-6 py-3 text-xs font-semibold uppercase tracking-wide"
            style="color: var(--color-text-muted);">Стажист</th>
        <th class="text-left px-6 py-3 text-xs font-semibold uppercase tracking-wide"
            style="color: var(--color-text-muted);">Пройдено</th>
        <th class="text-left px-6 py-3 text-xs font-semibold uppercase tracking-wide"
            style="color: var(--color-text-muted);">Середній бал</th>
        <th class="text-left px-6 py-3 text-xs font-semibold uppercase tracking-wide"
            style="color: var(--color-text-muted);">Остання активність</th>
        <th class="px-6 py-3"></th>
      </tr>
    </thead>
    <tbody class="divide-y" style="border-color: var(--color-border);">
      {% for item in trainees_data %}
      <tr class="hover:bg-gray-50 transition-colors">
        <td class="px-6 py-4">
          <div class="flex items-center gap-3">
            <div class="w-8 h-8 rounded-full flex items-center justify-center
                        text-white text-xs font-bold"
                 style="background: var(--color-primary);">
              {{ item.user.name[0] | upper }}
            </div>
            <div>
              <p class="font-semibold text-sm"
                 style="font-family: var(--font-display);">
                {{ item.user.name }}
              </p>
              <p class="text-xs" style="color: var(--color-text-muted);">
                {{ item.user.email }}
              </p>
            </div>
          </div>
        </td>
        <td class="px-6 py-4">
          <span class="font-semibold">{{ item.attempts_count }}</span>
          <span class="text-xs ml-1" style="color: var(--color-text-muted);">
            квізів
          </span>
        </td>
        <td class="px-6 py-4">
          {% if item.avg_score is not none %}
          <div class="flex items-center gap-2">
            <div class="w-24 h-1.5 rounded-full"
                 style="background: var(--color-border);">
              <div class="h-1.5 rounded-full"
                   style="width: {{ item.avg_score }}%;
                     background: {% if item.avg_score >= 80 %}var(--color-success)
                     {% elif item.avg_score >= 60 %}var(--color-accent)
                     {% else %}var(--color-error){% endif %};">
              </div>
            </div>
            <span class="font-semibold text-sm
              {% if item.avg_score >= 80 %}text-green-600
              {% elif item.avg_score >= 60 %}text-orange-500
              {% else %}text-red-500{% endif %}">
              {{ item.avg_score }}%
            </span>
          </div>
          {% else %}
          <span style="color: var(--color-text-muted);">—</span>
          {% endif %}
        </td>
        <td class="px-6 py-4 text-sm" style="color: var(--color-text-muted);">
          {% if item.last_activity %}
            {{ item.last_activity.strftime('%d.%m.%Y') }}
          {% else %}
            Ще не починав
          {% endif %}
        </td>
        <td class="px-6 py-4 text-right">
          <a href="/admin/trainees/{{ item.user.id }}"
             class="text-sm font-medium hover:underline"
             style="color: var(--color-primary);">
            Профіль →
          </a>
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</div>
{% else %}
<div class="text-center py-16" style="color: var(--color-text-muted);">
  <p class="text-4xl mb-4">👥</p>
  <p>Стажерів ще немає</p>
  {% if user.has_permission('manage_users') %}
  <a href="/admin/users" class="text-sm mt-2 block hover:underline"
     style="color: var(--color-primary);">
    Додати першого стажиста
  </a>
  {% endif %}
</div>
{% endif %}
{% endblock %}
```

---

## Завдання 4 — app/templates/admin/trainee_profile.html

```html
{% extends "base.html" %}
{% block title %}{{ trainee.name }}{% endblock %}

{% block content %}
<div class="max-w-4xl mx-auto">

  <!-- Breadcrumb -->
  <div class="flex items-center gap-2 text-sm mb-6"
       style="color: var(--color-text-muted);">
    <a href="/admin" class="hover:underline"
       style="color: var(--color-primary);">Адмін панель</a>
    <span>›</span>
    <a href="/admin/trainees" class="hover:underline"
       style="color: var(--color-primary);">Стажери</a>
    <span>›</span>
    <span>{{ trainee.name }}</span>
  </div>

  <!-- Profile header -->
  <div class="flex items-center gap-5 mb-8 p-6 rounded-2xl"
       style="background: var(--color-surface);
              border: 1px solid var(--color-border);
              box-shadow: var(--shadow-sm);">
    <div class="w-16 h-16 rounded-2xl flex items-center justify-center
                text-white text-2xl font-bold flex-shrink-0"
         style="background: var(--color-primary);
                font-family: var(--font-display);">
      {{ trainee.name[0] | upper }}
    </div>
    <div class="flex-1">
      <h1 class="text-2xl font-bold" style="font-family: var(--font-display);">
        {{ trainee.name }}
      </h1>
      <p class="text-sm mt-0.5" style="color: var(--color-text-muted);">
        {{ trainee.email }}
      </p>
      <p class="text-xs mt-1" style="color: var(--color-text-muted);">
        У команді з {{ trainee.created_at.strftime('%d.%m.%Y') }}
      </p>
    </div>
    {% if stats.recent_activity %}
    <div class="text-right">
      <p class="text-xs" style="color: var(--color-text-muted);">
        Остання активність
      </p>
      <p class="text-sm font-semibold mt-0.5">
        {{ stats.recent_activity.strftime('%d.%m.%Y о %H:%M') }}
      </p>
    </div>
    {% endif %}
  </div>

  {% if stats.total_attempts > 0 %}

  <!-- Stats grid -->
  <div class="grid grid-cols-4 gap-4 mb-6">

    <div class="p-5 rounded-2xl text-center"
         style="background: var(--color-surface);
                border: 1px solid var(--color-border);
                box-shadow: var(--shadow-sm);">
      <p class="text-3xl font-bold" style="font-family: var(--font-display);
         color: var(--color-primary);">
        {{ stats.unique_quizzes }}
      </p>
      <p class="text-xs mt-1" style="color: var(--color-text-muted);">
        Квізів пройдено
      </p>
    </div>

    <div class="p-5 rounded-2xl text-center"
         style="background: var(--color-surface);
                border: 1px solid var(--color-border);
                box-shadow: var(--shadow-sm);">
      <p class="text-3xl font-bold" style="font-family: var(--font-display);
         color: var(--color-primary);">
        {{ stats.total_attempts }}
      </p>
      <p class="text-xs mt-1" style="color: var(--color-text-muted);">
        Всього спроб
      </p>
    </div>

    <div class="p-5 rounded-2xl text-center"
         style="background: var(--color-surface);
                border: 1px solid var(--color-border);
                box-shadow: var(--shadow-sm);">
      <p class="text-3xl font-bold" style="font-family: var(--font-display);
         color: {% if stats.average_score >= 80 %}var(--color-success)
         {% elif stats.average_score >= 60 %}var(--color-accent)
         {% else %}var(--color-error){% endif %};">
        {% if stats.average_score %}{{ stats.average_score }}%{% else %}—{% endif %}
      </p>
      <p class="text-xs mt-1" style="color: var(--color-text-muted);">
        Середній бал
      </p>
    </div>

    <div class="p-5 rounded-2xl text-center"
         style="background: var(--color-surface);
                border: 1px solid var(--color-border);
                box-shadow: var(--shadow-sm);">
      <p class="text-3xl font-bold" style="font-family: var(--font-display);
         color: var(--color-success);">
        {% if stats.best_score %}{{ stats.best_score }}%{% else %}—{% endif %}
      </p>
      <p class="text-xs mt-1" style="color: var(--color-text-muted);">
        Кращий результат
      </p>
    </div>

  </div>

  <!-- Chart placeholder (резерв для Chart.js) -->
  <div class="p-6 mb-6 rounded-2xl flex items-center justify-center"
       style="background: var(--color-surface);
              border: 1px solid var(--color-border);
              border-style: dashed;
              min-height: 160px;">
    <div class="text-center" style="color: var(--color-text-muted);">
      <p class="text-2xl mb-2">📈</p>
      <p class="text-sm font-medium">Графік динаміки</p>
      <p class="text-xs mt-1">Буде доступний у наступному оновленні</p>
    </div>
  </div>

  <!-- Quiz results with progress bars -->
  <div class="mb-6 rounded-2xl overflow-hidden"
       style="background: var(--color-surface);
              border: 1px solid var(--color-border);
              box-shadow: var(--shadow-sm);">

    <div class="px-6 py-4"
         style="border-bottom: 2px solid var(--color-border);
                background: var(--color-bg);">
      <h2 class="font-bold text-sm" style="font-family: var(--font-display);">
        Результати по квізах
      </h2>
    </div>

    <div class="divide-y" style="border-color: var(--color-border);">
      {% for qs in stats.quiz_stats %}
      <div class="px-6 py-4">
        <div class="flex items-center justify-between mb-2">
          <span class="font-medium text-sm"
                style="font-family: var(--font-display);">
            {{ qs.quiz_title }}
          </span>
          <div class="flex items-center gap-3">
            <span class="text-xs" style="color: var(--color-text-muted);">
              {{ qs.attempts_count }} спроб
            </span>
            <span class="font-bold text-sm
              {% if qs.best_pct >= 80 %}text-green-600
              {% elif qs.best_pct >= 60 %}text-orange-500
              {% else %}text-red-500{% endif %}">
              {{ qs.best_pct }}%
            </span>
          </div>
        </div>
        <!-- Progress bar -->
        <div class="w-full h-2 rounded-full"
             style="background: var(--color-border);">
          <div class="h-2 rounded-full transition-all"
               style="width: {{ qs.best_pct }}%;
                 background: {% if qs.best_pct >= 80 %}var(--color-success)
                 {% elif qs.best_pct >= 60 %}var(--color-accent)
                 {% else %}var(--color-error){% endif %};">
          </div>
        </div>
        <p class="text-xs mt-1" style="color: var(--color-text-muted);">
          Остання спроба: {{ qs.last_attempt.strftime('%d.%m.%Y') }}
        </p>
      </div>
      {% endfor %}
    </div>
  </div>

  <!-- Activity timeline -->
  <div class="rounded-2xl overflow-hidden"
       style="background: var(--color-surface);
              border: 1px solid var(--color-border);
              box-shadow: var(--shadow-sm);">

    <div class="px-6 py-4"
         style="border-bottom: 2px solid var(--color-border);
                background: var(--color-bg);">
      <h2 class="font-bold text-sm" style="font-family: var(--font-display);">
        Хронологія спроб
      </h2>
    </div>

    <div class="divide-y" style="border-color: var(--color-border);">
      {% for attempt in stats.attempts %}
      {% set total_q = attempt.quiz.questions | length %}
      {% set pct = (attempt.score / total_q * 100) | round(1) if total_q > 0 and attempt.score is not none else 0 %}
      <div class="flex items-center gap-4 px-6 py-3">
        <div class="w-8 h-8 rounded-lg flex items-center justify-center text-xs font-bold flex-shrink-0"
             style="background: {% if pct >= 80 %}var(--color-success-bg){% elif pct >= 60 %}#FFF7ED{% else %}var(--color-error-bg){% endif %};
                    color: {% if pct >= 80 %}var(--color-success){% elif pct >= 60 %}var(--color-accent){% else %}var(--color-error){% endif %};">
          {{ pct | int }}%
        </div>
        <div class="flex-1">
          <p class="text-sm font-medium">{{ attempt.quiz.title }}</p>
          <p class="text-xs" style="color: var(--color-text-muted);">
            {{ attempt.score }} з {{ total_q }} правильних
          </p>
        </div>
        <p class="text-xs" style="color: var(--color-text-muted);">
          {{ attempt.completed_at.strftime('%d.%m.%Y о %H:%M') }}
        </p>
      </div>
      {% endfor %}
    </div>
  </div>

  {% else %}

  <!-- Empty state -->
  <div class="text-center py-20 rounded-2xl"
       style="background: var(--color-surface);
              border: 1px solid var(--color-border);">
    <p class="text-5xl mb-4">🎯</p>
    <h2 class="text-lg font-bold mb-2" style="font-family: var(--font-display);">
      Стажист ще не проходив квізів
    </h2>
    <p class="text-sm" style="color: var(--color-text-muted);">
      Результати з'являться після першого проходження
    </p>
  </div>

  {% endif %}

</div>
{% endblock %}
```

---

## Завдання 5 — Оновити навігацію в admin/dashboard.html

Заміни посилання Results:

```html
<!-- Було: -->
<a href="/admin/results" ...>📊 Результати</a>

<!-- Стало: -->
{% if user.has_permission('view_results') %}
<a href="/admin/trainees" ...>👥 Стажери</a>
{% endif %}
```

---

## Перевірка після виконання

```bash
uvicorn app.main:app --reload
```

Чекліст:
- [ ] `/admin/trainees` — таблиця з прогрес-барами і посиланнями на профілі
- [ ] `/admin/trainees/{id}` — повний профіль зі статистикою
- [ ] Порожній стан якщо стажист не проходив квізів
- [ ] Статистика правильно рахується (середній, кращий бал)
- [ ] Chart placeholder видно (пунктирна рамка з текстом)
- [ ] Хронологія спроб відсортована від нових до старих
- [ ] Прогрес-бари зафарбовані правильними кольорами (зелений/оранжевий/червоний)
