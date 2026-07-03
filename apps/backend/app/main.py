from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth, health, pull_requests, repositories, users, webhooks
from app.core.config import settings

app = FastAPI(title="AI Code Review & DevOps Assistant")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(webhooks.router)
app.include_router(repositories.router)
app.include_router(pull_requests.router)
