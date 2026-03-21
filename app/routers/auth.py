from __future__ import annotations
from fastapi import APIRouter, Request, Depends, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.services.auth_service import (
    authenticate_user,
    create_access_token,
    get_or_create_manager_user,
)
from app.services.manager_auth_service import (
    is_manager_login,
    authenticate_manager,
)

router = APIRouter(tags=["auth"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("auth/login.html", {"request": request})


@router.post("/login")
async def login(
    request: Request,
    response: Response,
    email: str = Form(...),   # приймає і email, і числовий ID менеджера
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    user = None

    # ─── Визначаємо тип логіну ────────────────────────────────────────────────
    if is_manager_login(email):
        # Числовий логін → перевіряємо в MySQL панелі менеджера
        manager_data = await authenticate_manager(email, password)

        if manager_data is None:
            request.session["flash"] = {
                "type": "error",
                "message": "Невірний ID або пароль",
            }
            return RedirectResponse("/login", status_code=303)

        # Знайти або створити запис в PostgreSQL
        user = await get_or_create_manager_user(
            db=db,
            manager_login=email,
            manager_id=manager_data["user_id"],
            manager_name=manager_data.get("name"),
        )
        await db.commit()

    else:
        # Email логін → стандартна автентифікація через PostgreSQL
        user = await authenticate_user(db, email, password)

        if not user:
            request.session["flash"] = {
                "type": "error",
                "message": "Невірний email або пароль. Спробуй ще раз або зверніться до керівника",
            }
            return RedirectResponse("/login", status_code=303)

    # ─── Видати JWT ───────────────────────────────────────────────────────────
    token = create_access_token(user.id, user.role)
    redirect_url = "/admin" if user.is_admin_or_above else "/dashboard"

    response = RedirectResponse(redirect_url, status_code=303)
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        max_age=60 * 60 * 8,
        samesite="lax",
    )
    return response


@router.post("/logout")
async def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie("access_token")
    return response
