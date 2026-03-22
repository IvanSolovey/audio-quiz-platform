from __future__ import annotations
import uuid
from fastapi import APIRouter, Request, Depends, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.dependencies import require_admin, require_permission
from app.models.user import User
from app.models.quiz import Quiz, Question, AnswerOption
from app.models.result import QuizAttempt
from app.services.auth_service import create_user, get_user_by_email
from app.services.quiz_service import get_quiz_with_questions
from app.services import audio_service
from app.services.result_service import get_all_trainees_with_stats, get_trainee_statistics

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
        select(Quiz)
        .options(selectinload(Quiz.questions))
        .order_by(Quiz.created_at.desc())
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
    admin: User = Depends(require_permission("manage_quizzes")),
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
    admin: User = Depends(require_permission("manage_quizzes")),
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
    admin: User = Depends(require_permission("manage_quizzes")),
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
    shuffle_questions: bool = Form(False),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_permission("manage_quizzes")),
):
    result = await db.execute(select(Quiz).where(Quiz.id == quiz_id))
    quiz = result.scalar_one_or_none()
    if not quiz:
        raise HTTPException(status_code=404)

    quiz.title = title.strip()
    quiz.description = description.strip() or None
    quiz.is_published = is_published
    quiz.shuffle_questions = shuffle_questions
    await db.commit()

    request.session["flash"] = {"type": "success", "message": "Збережено!"}
    return RedirectResponse(f"/admin/quiz/{quiz_id}", status_code=303)


@router.post("/quiz/{quiz_id}/delete")
async def delete_quiz(
    quiz_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_permission("manage_quizzes")),
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
    audio_file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_permission("manage_quizzes")),
):
    form = await request.form()
    text = (form.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="Текст питання обов'язковий")

    try:
        correct_option = int(form.get("correct_option", 0))
    except ValueError:
        raise HTTPException(status_code=422, detail="Оберіть правильну відповідь")

    # Collect all option_N fields in order, skip blanks
    options: list[tuple[int, str]] = []
    for key, value in form.multi_items():
        if key.startswith("option_"):
            try:
                n = int(key.split("_", 1)[1])
            except ValueError:
                continue
            text_val = value.strip()
            if text_val:
                options.append((n, text_val))
    options.sort(key=lambda x: x[0])

    if len(options) < 2:
        raise HTTPException(status_code=422, detail="Потрібно мінімум 2 варіанти відповіді")
    if not any(n == correct_option for n, _ in options):
        raise HTTPException(status_code=422, detail="Оберіть правильну відповідь")

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
        text=text,
        audio_url=audio_url,
        audio_key=audio_key,
        order_index=len(quiz.questions),
    )
    db.add(question)
    await db.flush()

    # Створити варіанти відповідей
    for n, opt_text in options:
        db.add(AnswerOption(
            question_id=question_id,
            text=opt_text,
            is_correct=(n == correct_option),
        ))

    await db.commit()
    request.session["flash"] = {"type": "success", "message": "Питання додано!"}
    return RedirectResponse(f"/admin/quiz/{quiz_id}", status_code=303)


@router.post("/quiz/{quiz_id}/question/{question_id}/duplicate")
async def duplicate_question(
    request: Request,
    quiz_id: uuid.UUID,
    question_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_permission("manage_quizzes")),
):
    result = await db.execute(
        select(Question)
        .where(Question.id == question_id)
        .options(selectinload(Question.options))
    )
    original = result.scalar_one_or_none()
    if not original:
        raise HTTPException(status_code=404)

    new_question = Question(
        quiz_id=quiz_id,
        text=original.text,
        audio_url=original.audio_url,
        audio_key=original.audio_key,
        order_index=original.order_index + 1,
    )
    db.add(new_question)
    await db.flush()

    for option in original.options:
        db.add(AnswerOption(
            question_id=new_question.id,
            text=option.text,
            is_correct=option.is_correct,
        ))

    await db.commit()
    request.session["flash"] = {"type": "success", "message": "Питання скопійовано!"}
    return RedirectResponse(f"/admin/quiz/{quiz_id}", status_code=303)


@router.post("/quiz/{quiz_id}/question/{question_id}/update")
async def update_question(
    request: Request,
    quiz_id: uuid.UUID,
    question_id: uuid.UUID,
    text: str = Form(...),
    option_1: str = Form(...),
    option_2: str = Form(...),
    option_3: str = Form(""),
    option_4: str = Form(""),
    correct_option: int = Form(...),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_permission("manage_quizzes")),
):
    result = await db.execute(
        select(Question)
        .where(Question.id == question_id)
        .options(selectinload(Question.options))
    )
    question = result.scalar_one_or_none()
    if not question:
        raise HTTPException(status_code=404)

    question.text = text.strip()

    for opt in list(question.options):
        await db.delete(opt)
    await db.flush()

    for idx, opt_text in enumerate([option_1, option_2, option_3, option_4], start=1):
        if not opt_text.strip():
            continue
        db.add(AnswerOption(
            question_id=question_id,
            text=opt_text.strip(),
            is_correct=(idx == correct_option),
        ))

    await db.commit()
    request.session["flash"] = {"type": "success", "message": "Питання оновлено!"}
    return RedirectResponse(f"/admin/quiz/{quiz_id}", status_code=303)


@router.post("/quiz/{quiz_id}/question/{question_id}/delete")
async def delete_question(
    quiz_id: uuid.UUID,
    question_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_permission("manage_quizzes")),
):
    result = await db.execute(select(Question).where(Question.id == question_id))
    question = result.scalar_one_or_none()
    if question:
        await audio_service.delete_audio(question.audio_key)
        await db.delete(question)
        await db.commit()

    return RedirectResponse(f"/admin/quiz/{quiz_id}", status_code=303)


# ─── Trainees ──────────────────────────────────────────────────────────────────

@router.get("/trainees", response_class=HTMLResponse)
async def trainees_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_permission("view_results")),
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
    admin: User = Depends(require_permission("view_results")),
):
    """Детальний профіль стажиста."""
    result = await db.execute(select(User).where(User.id == user_id))
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


# ─── Users ─────────────────────────────────────────────────────────────────────

@router.get("/users", response_class=HTMLResponse)
async def users_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_permission("manage_users")),
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
    admin: User = Depends(require_permission("manage_users")),
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
