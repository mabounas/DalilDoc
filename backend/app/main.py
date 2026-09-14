"""Point d'entrée FastAPI — WathiqaDoc API.

Lancement (depuis ``backend/``) : ``uvicorn app.main:app --reload``
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from .config import settings
from .db import AdminUser, SessionLocal, init_db
from .middleware.security import hash_password
from .routers import admin, public
from .services.knowledge import rag_holder, seed_from_files

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("wathiqadoc")


def bootstrap() -> None:
    """Crée les tables, le super-admin initial et amorce la base de connaissances."""
    init_db()
    with SessionLocal() as db:
        if settings.admin_bootstrap_email and settings.admin_bootstrap_password:
            email = settings.admin_bootstrap_email.lower()
            if db.scalar(select(AdminUser).where(AdminUser.email == email)) is None:
                db.add(AdminUser(email=email, password_hash=hash_password(settings.admin_bootstrap_password), role="super-admin"))
                db.commit()
                log.info("Super-admin initial créé : %s", email)
        seed_from_files(db)
        rag_holder.rebuild(db)


@asynccontextmanager
async def lifespan(_: FastAPI):
    bootstrap()
    yield


app = FastAPI(title="WathiqaDoc API", version="1.0.0", lifespan=lifespan,
              description="Assistant citoyen RAG — démarches administratives marocaines (Phase 1 : CIN).")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"],
                   allow_credentials=False)
app.include_router(public.router)
app.include_router(admin.router)


@app.get("/")
def root() -> dict:
    return {"service": "WathiqaDoc API", "docs": "/docs", "health": "/api/v1/health"}
