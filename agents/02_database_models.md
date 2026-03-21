# Агент 2 — Database Models

> Прочитай CLAUDE.md перед виконанням завдань.
> Залежить від: Агент 1 (структура папок, database.py вже існує).

---

## Твоє завдання

Створити всі SQLAlchemy моделі та налаштувати Alembic міграції.

---

## Завдання 1 — app/models/__init__.py

```python
from app.models.user import User
from app.models.quiz import Quiz, Question, AnswerOption
from app.models.result import QuizAttempt, AttemptAnswer

__all__ = [
    "User",
    "Quiz", "Question", "AnswerOption",
    "QuizAttempt", "AttemptAnswer",
]
```

---

## Завдання 2 — app/models/user.py

```python
from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import String, Enum, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(
        Enum("trainee", "admin", name="user_role"),
        nullable=False,
        default="trainee",
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    quizzes_created: Mapped[list[Quiz]] = relationship(back_populates="creator")
    attempts: Mapped[list[QuizAttempt]] = relationship(back_populates="user")

    def __repr__(self) -> str:
        return f"<User {self.email} ({self.role})>"
```

---

## Завдання 3 — app/models/quiz.py

```python
from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, Integer, ForeignKey, DateTime, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Quiz(Base):
    __tablename__ = "quizzes"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    creator: Mapped[User] = relationship(back_populates="quizzes_created")
    questions: Mapped[list[Question]] = relationship(
        back_populates="quiz",
        cascade="all, delete-orphan",
        order_by="Question.order_index",
    )
    attempts: Mapped[list[QuizAttempt]] = relationship(back_populates="quiz")

    def __repr__(self) -> str:
        return f"<Quiz '{self.title}'>"


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    quiz_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    audio_url: Mapped[str] = mapped_column(String(512), nullable=False)
    audio_key: Mapped[str] = mapped_column(String(512), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    quiz: Mapped[Quiz] = relationship(back_populates="questions")
    options: Mapped[list[AnswerOption]] = relationship(
        back_populates="question",
        cascade="all, delete-orphan",
    )
    attempt_answers: Mapped[list[AttemptAnswer]] = relationship(back_populates="question")

    def __repr__(self) -> str:
        return f"<Question '{self.text[:50]}'>"


class AnswerOption(Base):
    __tablename__ = "answer_options"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    question: Mapped[Question] = relationship(back_populates="options")

    def __repr__(self) -> str:
        return f"<AnswerOption '{self.text[:30]}' correct={self.is_correct}>"
```

---

## Завдання 4 — app/models/result.py

```python
from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import Boolean, Integer, ForeignKey, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    quiz_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Relationships
    user: Mapped[User] = relationship(back_populates="attempts")
    quiz: Mapped[Quiz] = relationship(back_populates="attempts")
    answers: Mapped[list[AttemptAnswer]] = relationship(
        back_populates="attempt",
        cascade="all, delete-orphan",
    )

    @property
    def is_completed(self) -> bool:
        return self.completed_at is not None

    @property
    def score_percent(self) -> float | None:
        if self.score is None or not self.quiz.questions:
            return None
        return round(self.score / len(self.quiz.questions) * 100, 1)


class AttemptAnswer(Base):
    __tablename__ = "attempt_answers"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    attempt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("quiz_attempts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), nullable=False
    )
    selected_option_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("answer_options.id", ondelete="CASCADE"), nullable=False
    )
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    answered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    attempt: Mapped[QuizAttempt] = relationship(back_populates="answers")
    question: Mapped[Question] = relationship(back_populates="attempt_answers")
    selected_option: Mapped[AnswerOption] = relationship()
```

---

## Завдання 5 — Налаштування Alembic

```bash
alembic init alembic
```

Потім відредагуй `alembic/env.py` — замінити вміст на:

```python
from __future__ import annotations
import asyncio
from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context
from app.config import settings
from app.database import Base

# Імпортуй всі моделі щоб Alembic їх бачив
from app.models import User, Quiz, Question, AnswerOption, QuizAttempt, AttemptAnswer  # noqa

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

---

## Завдання 6 — Створи першу міграцію

```bash
alembic revision --autogenerate -m "initial_schema"
alembic upgrade head
```

---

## Перевірка після виконання

```python
# Запусти в python REPL або як скрипт
import asyncio
from sqlalchemy import text
from app.database import engine

async def check():
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public'"))
        tables = [row[0] for row in result]
        print("Таблиці в БД:", tables)
        expected = {"users", "quizzes", "questions", "answer_options", "quiz_attempts", "attempt_answers"}
        assert expected.issubset(set(tables)), f"Відсутні таблиці: {expected - set(tables)}"
        print("✅ Всі таблиці створені успішно")

asyncio.run(check())
```

---

## Що НЕ робить цей агент

- Не пише автентифікацію (→ Агент 3)
- Не створює seed дані (→ Агент 3, створює першого адміна)
- Не пише сервіси (→ Агенти 4, 5, 6)
