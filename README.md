# OSD Audio Quiz Platform

An internal training platform for company interns built with FastAPI, HTMX, and PostgreSQL.

## Features

- 🎧 **Audio-based quizzes** — listen to audio clips and select the correct answer
- 📚 **Knowledge base** — documentation and guides with Markdown support
- 📣 **Announcements** — modal notifications for trainees on login
- 👥 **Role-based access** — granular admin permissions system
- 📊 **Trainee profiles** — detailed progress tracking and statistics

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI + Jinja2 |
| Frontend | HTMX + TailwindCSS (CDN) |
| Database | PostgreSQL + SQLAlchemy (async) |
| Migrations | Alembic |
| Audio storage | Cloudflare R2 |
| Audio processing | ffmpeg |
| Auth | JWT (httpOnly cookie) |

## Requirements

- Python 3.11+
- PostgreSQL 15+
- ffmpeg
- Docker & Docker Compose (for deployment)

## Local Development

**1. Clone the repository**
```bash
git clone https://github.com/IvanSolovey/audio-quiz-platform.git
cd audio-quiz-platform
```

**2. Create virtual environment**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

**3. Install dependencies**
```bash
pip install -r requirements.txt
```

**4. Set up environment variables**

Create a `.env` file in the project root:
```dotenv
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/audioquiz
SECRET_KEY=your-secret-key-min-32-chars
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=480
ADMIN_EMAIL=admin@company.com
ADMIN_PASSWORD=your-admin-password
R2_ACCOUNT_ID=
R2_ACCESS_KEY_ID=
R2_SECRET_ACCESS_KEY=
R2_BUCKET_NAME=audio-quiz-files
R2_PUBLIC_URL=
```

**5. Start PostgreSQL**
```bash
docker run -d \
  --name audioquiz-db \
  -e POSTGRES_USER=audioquiz \
  -e POSTGRES_PASSWORD=audioquiz123 \
  -e POSTGRES_DB=audioquiz \
  -p 5432:5432 \
  postgres:15
```

**6. Run migrations**
```bash
alembic upgrade head
```

**7. Start the server**
```bash
uvicorn app.main:app --reload
```

Open [http://localhost:8000](http://localhost:8000) and log in with your admin credentials.

## Deployment

The project is designed to run on a Debian server using Docker Compose.

```bash
docker compose up -d --build
docker compose exec app alembic upgrade head
```

See `docker-compose.yml` and `Dockerfile` for configuration details.

## Audio Storage

Audio files are stored in Cloudflare R2 (S3-compatible). For local development, leave the `R2_*` variables empty — files will be stored in `static/audio/` instead.

All uploaded audio is automatically converted to MP3 128kbps via ffmpeg before storage.

## License

Internal use only — OSD Company.