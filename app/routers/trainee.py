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
from app.services.knowledge_service import get_all_categories

router = APIRouter(tags=["trainee"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    quizzes = await quiz_service.get_published_quizzes(db)
    attempts_by_quiz = await result_service.get_latest_attempts_for_user(db, current_user.id)
    incomplete_by_quiz = await result_service.get_incomplete_attempts_for_user(db, current_user.id)
    categories = await get_all_categories(db, visible_only=True)
    for cat in categories:
        cat.articles = [a for a in cat.articles if a.is_visible]
    categories = [c for c in categories if c.articles]
    return templates.TemplateResponse("trainee/dashboard.html", {
        "request": request,
        "quizzes": quizzes,
        "attempts_by_quiz": attempts_by_quiz,
        "incomplete_by_quiz": incomplete_by_quiz,
        "categories": categories,
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

    # 1. Resume an in-progress attempt if one exists (no creation yet)
    in_progress = await result_service.get_in_progress_attempt(db, current_user.id, quiz_id)
    if in_progress:
        answered_ids = await result_service.get_answered_question_ids(db, in_progress.id)
        unanswered = [q for q in quiz.questions if q.id not in answered_ids]
        if not unanswered:
            completed = await result_service.complete_attempt(db, in_progress.id)
            await db.commit()
            return RedirectResponse(f"/quiz/{quiz_id}/result/{in_progress.id}", status_code=303)
        return templates.TemplateResponse("trainee/quiz.html", {
            "request": request,
            "quiz": quiz,
            "question": unanswered[0],
            "attempt_id": str(in_progress.id),
            "progress": len(answered_ids),
            "total": len(quiz.questions),
            "user": current_user,
        })

    # 2. No in-progress attempt — check for a previous completed one
    previous = await result_service.get_latest_completed_attempt(db, current_user.id, quiz_id)
    if previous:
        total = len(quiz.questions)
        score = previous.score or 0
        pct = round(score / total * 100) if total > 0 else 0
        return templates.TemplateResponse("trainee/quiz_confirm.html", {
            "request": request,
            "quiz": quiz,
            "score": score,
            "total": total,
            "pct": pct,
            "user": current_user,
        })

    # 3. First time — create attempt and start
    attempt = await result_service.start_attempt(db, current_user.id, quiz_id)
    await db.commit()
    return templates.TemplateResponse("trainee/quiz.html", {
        "request": request,
        "quiz": quiz,
        "question": quiz.questions[0],
        "attempt_id": str(attempt.id),
        "progress": 0,
        "total": len(quiz.questions),
        "user": current_user,
    })


@router.post("/quiz/{quiz_id}/start", response_class=HTMLResponse)
async def start_quiz(
    request: Request,
    quiz_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    quiz = await quiz_service.get_quiz_with_questions(db, quiz_id)
    if not quiz or not quiz.is_published:
        return RedirectResponse("/dashboard", status_code=303)

    attempt = await result_service.start_attempt(db, current_user.id, quiz_id)
    await db.commit()
    return templates.TemplateResponse("trainee/quiz.html", {
        "request": request,
        "quiz": quiz,
        "question": quiz.questions[0],
        "attempt_id": str(attempt.id),
        "progress": 0,
        "total": len(quiz.questions),
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
