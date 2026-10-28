from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .auth import User, current_user
from .config import settings
from .db import pool
from .routers import audit, departments, employees


@asynccontextmanager
async def lifespan(_: FastAPI):
    pool.open()
    yield
    pool.close()


app = FastAPI(title="SecureHR Portal API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                   allow_methods=["GET"], allow_headers=["Authorization"])

app.include_router(employees.router)
app.include_router(departments.router)
app.include_router(audit.router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}


@app.get("/me", tags=["meta"])
def me(user: User = Depends(current_user)):
    return {"username": user.username, "role": user.role, "emp_no": user.emp_no}
