from __future__ import annotations
import json
import random
import uuid
from datetime import datetime, timezone
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.quiz import AnswerOption, Question, Quiz
from app.models.result import QuizAttempt, AttemptAnswer
from app.models.user import User


async def start_attempt(
    db: AsyncSession,
    user_id: uuid.UUID,
    quiz_id: uuid.UUID,
    questions: list | None = None,
    shuffle: bool = False,
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

    question_order = None
    if questions and shuffle:
        shuffled = list(questions)
        random.shuffle(shuffled)
        question_order = json.dumps([str(q.id) for q in shuffled])

    attempt = QuizAttempt(user_id=user_id, quiz_id=quiz_id, question_order=question_order)
    db.add(attempt)
    await db.flush()
    await db.refresh(attempt)
    return attempt


def get_ordered_questions(attempt: QuizAttempt, questions: list) -> list:
    """Return questions in the order stored on this attempt, falling back to natural order."""
    if not attempt.question_order:
        return list(questions)
    id_order = json.loads(attempt.question_order)
    id_map = {str(q.id): q for q in questions}
    ordered = [id_map[qid] for qid in id_order if qid in id_map]
    # Append any questions added to the quiz after the attempt was started
    stored_set = set(id_order)
    for q in questions:
        if str(q.id) not in stored_set:
            ordered.append(q)
    return ordered


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
        .options(selectinload(QuizAttempt.quiz).selectinload(Quiz.questions))
        .order_by(QuizAttempt.completed_at.desc())
    )
    return list(result.scalars().all())


async def get_incomplete_attempts_for_user(
    db: AsyncSession, user_id: uuid.UUID
) -> dict[uuid.UUID, QuizAttempt]:
    """Returns the most recent incomplete attempt per quiz for a user, keyed by quiz_id."""
    result = await db.execute(
        select(QuizAttempt)
        .where(
            QuizAttempt.user_id == user_id,
            QuizAttempt.completed_at == None,
        )
        .order_by(QuizAttempt.started_at.desc())
    )
    by_quiz: dict[uuid.UUID, QuizAttempt] = {}
    for attempt in result.scalars().all():
        if attempt.quiz_id not in by_quiz:
            by_quiz[attempt.quiz_id] = attempt
    return by_quiz


async def get_in_progress_attempt(
    db: AsyncSession, user_id: uuid.UUID, quiz_id: uuid.UUID
) -> QuizAttempt | None:
    """Returns an existing incomplete attempt, or None. Does NOT create one."""
    result = await db.execute(
        select(QuizAttempt).where(
            QuizAttempt.user_id == user_id,
            QuizAttempt.quiz_id == quiz_id,
            QuizAttempt.completed_at == None,
        )
    )
    return result.scalar_one_or_none()


async def get_latest_completed_attempt(
    db: AsyncSession, user_id: uuid.UUID, quiz_id: uuid.UUID
) -> QuizAttempt | None:
    """Returns the most recent completed attempt for a specific quiz, or None."""
    result = await db.execute(
        select(QuizAttempt)
        .where(
            QuizAttempt.user_id == user_id,
            QuizAttempt.quiz_id == quiz_id,
            QuizAttempt.completed_at != None,
        )
        .order_by(QuizAttempt.completed_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_latest_attempts_for_user(
    db: AsyncSession, user_id: uuid.UUID
) -> dict[uuid.UUID, QuizAttempt]:
    """Returns the latest completed attempt per quiz for a user, keyed by quiz_id."""
    result = await db.execute(
        select(QuizAttempt)
        .where(
            QuizAttempt.user_id == user_id,
            QuizAttempt.completed_at != None,
        )
        .order_by(QuizAttempt.completed_at.desc())
    )
    attempts = result.scalars().all()
    # Keep only the most recent attempt per quiz
    by_quiz: dict[uuid.UUID, QuizAttempt] = {}
    for attempt in attempts:
        if attempt.quiz_id not in by_quiz:
            by_quiz[attempt.quiz_id] = attempt
    return by_quiz


async def get_answered_question_ids(
    db: AsyncSession, attempt_id: uuid.UUID
) -> list[uuid.UUID]:
    result = await db.execute(
        select(AttemptAnswer.question_id).where(
            AttemptAnswer.attempt_id == attempt_id
        )
    )
    return [row[0] for row in result.all()]


async def get_trainee_statistics(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    """Повна статистика стажиста для профілю."""
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

    scores = []
    for attempt in attempts:
        total_q = len(attempt.quiz.questions)
        if total_q > 0 and attempt.score is not None:
            scores.append(round(attempt.score / total_q * 100, 1))

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
        "attempts": attempts,
        "quiz_stats": quiz_stats,
        "recent_activity": attempts[0].completed_at if attempts else None,
    }


async def get_all_trainees_with_stats(
    db: AsyncSession,
) -> list[dict]:
    """Список всіх стажистів зі зведеною статистикою."""
    users_result = await db.execute(
        select(User)
        .where(User.role == "trainee")
        .order_by(User.name)
    )
    trainees = list(users_result.scalars().all())

    result = []
    for trainee in trainees:
        count_result = await db.execute(
            select(func.count())
            .select_from(QuizAttempt)
            .where(
                QuizAttempt.user_id == trainee.id,
                QuizAttempt.completed_at != None,
            )
        )
        attempts_count = count_result.scalar() or 0

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
