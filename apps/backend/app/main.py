from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth, health, notifications, pull_requests, repositories, users, webhooks
from app.core.config import settings
from app.core.logging import configure_logging
from app.core.metrics import metrics_endpoint, prometheus_middleware
from app.core.rate_limit import rate_limit_middleware

configure_logging()

app = FastAPI(title="AI Code Review & DevOps Assistant")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.middleware("http")(prometheus_middleware)
# Added last -> runs first: reject over-limit requests before they're even
# counted in the HTTP metrics above.
app.middleware("http")(rate_limit_middleware)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(webhooks.router)
app.include_router(repositories.router)
app.include_router(pull_requests.router)
app.include_router(notifications.router)

app.get("/metrics", include_in_schema=False)(metrics_endpoint)
