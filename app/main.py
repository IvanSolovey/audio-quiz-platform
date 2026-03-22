from __future__ import annotations
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from app.config import settings
from app.database import SessionLocal
from app.services.auth_service import ensure_admin_exists
from app.services.manager_auth_service import close_manager_engine
from app.routers import (
    auth, trainee, admin, docs,
    admin_docs, admin_permissions,
    announcements, admin_announcements,
    onboarding, admin_onboarding,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: створити адміна якщо немає
    async with SessionLocal() as db:
        await ensure_admin_exists(db)
        await db.commit()
    yield
    # Shutdown
    await close_manager_engine()


app = FastAPI(title="Audio Quiz Platform", lifespan=lifespan, docs_url=None, redoc_url=None)

app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)
app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="app/templates")

# Роутери
app.include_router(auth.router)
app.include_router(trainee.router)
app.include_router(admin.router)
app.include_router(docs.router)
app.include_router(admin_docs.router)
app.include_router(admin_permissions.router)
app.include_router(announcements.router)
app.include_router(admin_announcements.router)
app.include_router(onboarding.router)
app.include_router(admin_onboarding.router)


@app.get("/")
async def root():
    from fastapi.responses import RedirectResponse
    return RedirectResponse("/dashboard")


@app.get("/health")
async def health_check():
    return {"status": "ok"}
