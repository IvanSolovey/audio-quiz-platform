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
        .options(selectinload(Quiz.questions))
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
