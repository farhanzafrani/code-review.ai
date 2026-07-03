from fastapi import FastAPI

from app.api.routes import auth, health, users, webhooks

app = FastAPI(title="AI Code Review & DevOps Assistant")

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(webhooks.router)
