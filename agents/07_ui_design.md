# Агент 7 — UI/UX Design Upgrade

> Прочитай CLAUDE.md і agents/osd_brand.md перед виконанням.
> Цей агент працює ТІЛЬКИ з шаблонами — не чіпає Python код.
> Залежить від: всі попередні агенти завершені.

---

## Твоє завдання

Провести повний UI audit всіх Jinja2 шаблонів і впровадити
production-grade дизайн для корпоративної навчальної платформи OSD.

Контекст: B2B компанія з продажів, 21 рік на ринку, стажери — молоді люди.
Тон: професійний, впевнений, без зайвої офіційності.

---

## Крок 1 — Аудит (прочитай всі шаблони перед змінами)

Прочитай кожен файл і зафіксуй проблеми:

```
app/templates/base.html
app/templates/auth/login.html
app/templates/trainee/dashboard.html
app/templates/trainee/quiz.html
app/templates/trainee/result.html
app/templates/trainee/progress.html
app/templates/partials/question.html
app/templates/admin/dashboard.html
app/templates/admin/quiz_edit.html
app/templates/admin/results.html
app/templates/admin/users.html
```

Для кожного файлу перевір:
- Чи консистентні відступи і розміри?
- Чи є візуальна ієрархія (заголовки, підзаголовки, контент)?
- Чи читабельний текст (контраст, розмір шрифту)?
- Чи є порожні стани (empty states)?
- Чи адаптований для різних розмірів екрану?

---

## Крок 2 — Design System у base.html

Впровадь CSS змінні і Google Fonts у `<head>` тегу `base.html`:

```html
<!-- Google Fonts: Manrope для заголовків, Inter для тексту -->
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">

<style>
  :root {
    /* OSD Brand Colors */
    --color-primary: #1A3A5C;
    --color-primary-dark: #122840;
    --color-primary-light: #2A5280;
    --color-accent: #F4871F;
    --color-accent-dark: #D4720F;

    /* Neutrals */
    --color-bg: #F5F7FA;
    --color-surface: #FFFFFF;
    --color-border: #E2E8F0;
    --color-text: #1A2332;
    --color-text-muted: #64748B;

    /* Semantic */
    --color-success: #16A34A;
    --color-success-bg: #F0FDF4;
    --color-warning: #D97706;
    --color-warning-bg: #FFFBEB;
    --color-error: #DC2626;
    --color-error-bg: #FEF2F2;

    /* Typography */
    --font-display: 'Manrope', sans-serif;
    --font-body: 'Inter', sans-serif;

    /* Shadows */
    --shadow-sm: 0 1px 3px rgba(26,58,92,0.08), 0 1px 2px rgba(26,58,92,0.04);
    --shadow-md: 0 4px 12px rgba(26,58,92,0.10), 0 2px 4px rgba(26,58,92,0.06);
    --shadow-lg: 0 10px 30px rgba(26,58,92,0.12), 0 4px 8px rgba(26,58,92,0.08);

    /* Radius */
    --radius-sm: 8px;
    --radius-md: 12px;
    --radius-lg: 16px;
    --radius-xl: 24px;
  }

  body {
    font-family: var(--font-body);
    background-color: var(--color-bg);
    color: var(--color-text);
    -webkit-font-smoothing: antialiased;
  }

  h1, h2, h3, h4 {
    font-family: var(--font-display);
    font-weight: 700;
  }
</style>
```

---

## Крок 3 — Navbar (base.html)

Заміни navbar на професійний варіант:

```html
<nav style="background: var(--color-primary); box-shadow: var(--shadow-md);">
  <div class="max-w-6xl mx-auto px-6 py-0">
    <div class="flex items-center justify-between h-16">

      <!-- Logo -->
      <a href="/" class="flex items-center gap-3 group">
        <div style="background: var(--color-accent); border-radius: 8px;"
             class="w-9 h-9 flex items-center justify-center font-bold text-white text-sm">
          OSD
        </div>
        <div>
          <div class="text-white font-bold text-base leading-tight"
               style="font-family: var(--font-display);">OSD</div>
          <div class="text-xs leading-tight" style="color: rgba(255,255,255,0.6);">
            Навчальна платформа
          </div>
        </div>
      </a>

      <!-- Nav links -->
      <div class="flex items-center gap-2 text-sm">
        {% if request.state.user %}
          <span style="color: rgba(255,255,255,0.7);" class="text-sm hidden sm:block">
            {{ request.state.user.name }}
          </span>

          {% if request.state.user.role == 'admin' %}
            <a href="/admin"
               class="px-3 py-1.5 rounded-lg text-white text-sm font-medium transition-all"
               style="background: rgba(255,255,255,0.12);">
              Панель керування
            </a>
          {% else %}
            <a href="/dashboard"
               class="px-3 py-1.5 rounded-lg text-white text-sm transition-all"
               style="background: rgba(255,255,255,0.08);">
              Тести
            </a>
            <a href="/progress"
               class="px-3 py-1.5 rounded-lg text-white text-sm transition-all"
               style="background: rgba(255,255,255,0.08);">
              Мій прогрес
            </a>
          {% endif %}

          <form action="/logout" method="post">
            <button type="submit"
                    class="px-3 py-1.5 rounded-lg text-sm font-medium transition-all"
                    style="color: rgba(255,255,255,0.7); background: rgba(255,255,255,0.06);">
              Вийти
            </button>
          </form>
        {% endif %}
      </div>

    </div>
  </div>
</nav>
```

---

## Крок 4 — Flash повідомлення (base.html)

```html
{% if request.session.get('flash') %}
{% set flash = request.session.pop('flash') %}
<div class="max-w-6xl mx-auto px-6 mt-4">
  <div class="flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium"
       style="
         background: {% if flash.type == 'error' %}var(--color-error-bg){% else %}var(--color-success-bg){% endif %};
         color: {% if flash.type == 'error' %}var(--color-error){% else %}var(--color-success){% endif %};
         border: 1px solid {% if flash.type == 'error' %}#FECACA{% else %}#BBF7D0{% endif %};
       ">
    <span>{% if flash.type == 'error' %}⚠️{% else %}✓{% endif %}</span>
    <span>{{ flash.message }}</span>
  </div>
</div>
{% endif %}
```

---

## Крок 5 — Footer (base.html, перед </body>)

```html
<footer class="mt-16 py-6 border-t" style="border-color: var(--color-border);">
  <div class="max-w-6xl mx-auto px-6 flex flex-col sm:flex-row items-center justify-between gap-2">
    <span class="text-sm" style="color: var(--color-text-muted);">
      © 2024 OSD — Аутсорсинговий відділ збуту
    </span>
    <div class="flex items-center gap-4 text-sm" style="color: var(--color-text-muted);">
      <a href="https://osd24.com" target="_blank" class="hover:underline">osd24.com</a>
      <span>·</span>
      <a href="tel:0800753782" class="hover:underline">0 800 753 782</a>
      <span>·</span>
      <span>09:00–18:00</span>
    </div>
  </div>
</footer>
```

---

## Крок 6 — Login page (auth/login.html)

Повністю перепиши на елегантний centered layout:

```html
{% extends "base.html" %}
{% block title %}Вхід{% endblock %}
{% block content %}
<div class="min-h-[70vh] flex items-center justify-center py-12">
  <div class="w-full max-w-sm">

    <!-- Logo block -->
    <div class="text-center mb-8">
      <div class="inline-flex items-center justify-center w-14 h-14 rounded-2xl mb-4 font-bold text-white text-lg"
           style="background: var(--color-primary); font-family: var(--font-display);">
        OSD
      </div>
      <h1 class="text-2xl font-bold" style="font-family: var(--font-display); color: var(--color-text);">
        OSD — Навчальна платформа
      </h1>
      <p class="text-sm mt-1" style="color: var(--color-text-muted);">
        Введи свої дані щоб увійти до системи
      </p>
    </div>

    <!-- Form card -->
    <div class="p-8 rounded-2xl" style="background: var(--color-surface); box-shadow: var(--shadow-lg); border: 1px solid var(--color-border);">
      <form action="/login" method="post" class="space-y-5">

        <div>
          <label class="block text-sm font-medium mb-1.5" style="color: var(--color-text);">
            Email
          </label>
          <input type="email" name="email" required autofocus
                 placeholder="your.name@osd24.com"
                 class="w-full px-4 py-3 rounded-xl text-sm transition-all outline-none"
                 style="border: 1.5px solid var(--color-border); background: var(--color-bg);
                        font-family: var(--font-body);"
                 onfocus="this.style.borderColor='var(--color-primary)'"
                 onblur="this.style.borderColor='var(--color-border)'">
        </div>

        <div>
          <label class="block text-sm font-medium mb-1.5" style="color: var(--color-text);">
            Пароль
          </label>
          <input type="password" name="password" required
                 placeholder="••••••••"
                 class="w-full px-4 py-3 rounded-xl text-sm transition-all outline-none"
                 style="border: 1.5px solid var(--color-border); background: var(--color-bg);
                        font-family: var(--font-body);"
                 onfocus="this.style.borderColor='var(--color-primary)'"
                 onblur="this.style.borderColor='var(--color-border)'">
        </div>

        <button type="submit"
                class="w-full py-3 px-4 rounded-xl text-white font-semibold text-sm transition-all mt-2"
                style="background: var(--color-primary); font-family: var(--font-display);"
                onmouseover="this.style.background='var(--color-primary-dark)'"
                onmouseout="this.style.background='var(--color-primary)'">
          Увійти →
        </button>

      </form>
    </div>

    <p class="text-center text-xs mt-6" style="color: var(--color-text-muted);">
      Проблеми з входом?
      <a href="mailto:info@osd24.com" class="hover:underline" style="color: var(--color-primary);">
        info@osd24.com
      </a>
    </p>

  </div>
</div>
{% endblock %}
```

---

## Крок 7 — UI Best Practices для всіх шаблонів

Застосуй ці правила до кожного шаблону що ще не оновлений:

### Картки і контейнери
```css
/* Замість border border-gray-200 rounded-xl використовуй: */
style="background: var(--color-surface);
       border: 1px solid var(--color-border);
       border-radius: var(--radius-lg);
       box-shadow: var(--shadow-sm);"
```

### Кнопки — PRIMARY
```html
<button style="background: var(--color-primary); color: white;
               border-radius: var(--radius-sm); font-family: var(--font-display);
               font-weight: 600; padding: 10px 20px; font-size: 14px;
               transition: background 0.2s;"
        onmouseover="this.style.background='var(--color-primary-dark)'"
        onmouseout="this.style.background='var(--color-primary)'">
```

### Кнопки — ACCENT (для головних CTA)
```html
<button style="background: var(--color-accent); color: white;
               border-radius: var(--radius-sm); font-family: var(--font-display);
               font-weight: 600; padding: 10px 20px; font-size: 14px;"
        onmouseover="this.style.background='var(--color-accent-dark)'"
        onmouseout="this.style.background='var(--color-accent)'">
```

### Кнопки — OUTLINE
```html
<button style="background: transparent; color: var(--color-primary);
               border: 1.5px solid var(--color-border);
               border-radius: var(--radius-sm); padding: 10px 20px; font-size: 14px;">
```

### Заголовки сторінок
```html
<h1 style="font-family: var(--font-display); font-size: 1.75rem;
           font-weight: 800; color: var(--color-text);">
```

### Таблиці
```html
<table class="w-full text-sm">
  <thead style="background: var(--color-bg); border-bottom: 2px solid var(--color-border);">
    <tr>
      <th class="text-left px-6 py-3 font-semibold text-xs uppercase tracking-wide"
          style="color: var(--color-text-muted);">
```

### Бейджі статусів
```html
<!-- Опубліковано -->
<span class="inline-flex items-center px-2.5 py-1 rounded-lg text-xs font-semibold"
      style="background: var(--color-success-bg); color: var(--color-success);">
  ✓ Опубліковано
</span>

<!-- Чернетка -->
<span class="inline-flex items-center px-2.5 py-1 rounded-lg text-xs font-semibold"
      style="background: #F1F5F9; color: var(--color-text-muted);">
  Чернетка
</span>
```

### Progress bar (quiz.html)
```html
<div class="w-full rounded-full h-1.5" style="background: var(--color-border);">
  <div class="h-1.5 rounded-full transition-all duration-500"
       style="width: {{ (progress / total * 100) | int }}%;
              background: var(--color-accent);">
  </div>
</div>
```

### Аудіоплеєр (partials/question.html)
```html
<div class="p-5 rounded-xl" style="background: var(--color-bg); border: 1px solid var(--color-border);">
  <div class="flex items-center gap-2 mb-3">
    <span style="color: var(--color-accent);">🎧</span>
    <span class="text-xs font-semibold uppercase tracking-wide"
          style="color: var(--color-text-muted);">
      Уважно прослухай запис
    </span>
  </div>
  <audio controls preload="metadata" class="w-full" id="audio-player"
         src="{{ question.audio_url }}"
         style="border-radius: 8px;">
  </audio>
</div>
```

---

## Крок 8 — Dashboard стажиста (trainee/dashboard.html)

Картка квізу має виглядати як premium product card:

```html
<a href="/quiz/{{ quiz.id }}"
   class="block group transition-all duration-200"
   style="background: var(--color-surface);
          border: 1px solid var(--color-border);
          border-radius: var(--radius-lg);
          box-shadow: var(--shadow-sm);
          padding: 1.5rem;
          text-decoration: none;"
   onmouseover="this.style.boxShadow='var(--shadow-md)'; this.style.borderColor='#A0B8D0';"
   onmouseout="this.style.boxShadow='var(--shadow-sm)'; this.style.borderColor='var(--color-border)';">

  <div class="flex items-start justify-between mb-4">
    <div class="w-10 h-10 rounded-xl flex items-center justify-center text-lg"
         style="background: #EEF4FF;">
      🎧
    </div>
    <!-- Бейдж статусу (завершено / в процесі) -->
  </div>

  <h3 style="font-family: var(--font-display); font-weight: 700;
             color: var(--color-text); font-size: 1rem; margin-bottom: 0.5rem;">
    {{ quiz.title }}
  </h3>

  {% if quiz.description %}
  <p class="text-sm mb-4" style="color: var(--color-text-muted);">
    {{ quiz.description }}
  </p>
  {% endif %}

  <div class="flex items-center justify-between mt-4 pt-4"
       style="border-top: 1px solid var(--color-border);">
    <span class="text-xs" style="color: var(--color-text-muted);">
      {{ quiz.questions | length }} питань · Аудіо формат
    </span>
    <span class="text-sm font-semibold" style="color: var(--color-accent);">
      Розпочати →
    </span>
  </div>
</a>
```

---

## Крок 9 — Фінальна перевірка

Після всіх змін запусти сервер і перевір кожну сторінку:

```bash
uvicorn app.main:app --reload
```

Чекліст перевірки:
- [ ] `http://localhost:8000/login` — логін виглядає як корпоративна сторінка
- [ ] `http://localhost:8000/dashboard` — картки квізів з hover ефектами
- [ ] `/quiz/{id}` — аудіоплеєр в стилі OSD, прогрес бар помаранчевий
- [ ] Результати — різні повідомлення для різних балів
- [ ] `/admin` — таблиці з правильною типографікою
- [ ] Navbar — синій з OSD логотипом
- [ ] Footer — контакти OSD на кожній сторінці
- [ ] Шрифти Manrope/Inter завантажуються (перевір Network tab у DevTools)

---

## Що НЕ робить цей агент

- Не змінює Python код (тільки HTML шаблони)
- Не додає нові функції
- Не змінює структуру даних
- Не чіпає роутери або сервіси
