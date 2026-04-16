"""FastAPI relay service entry point."""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import redis.asyncio as redis

from config import get_settings
from services.connection_manager import ConnectionManager


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle: Redis connection pool."""
    settings = get_settings()
    app.state.redis = redis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
    )
    app.state.manager = ConnectionManager(app.state.redis)
    yield
    await app.state.redis.close()


app = FastAPI(
    title="Studio AI Relay",
    description="WebSocket relay service for Studio AI",
    version="0.1.0",
    lifespan=lifespan,
)

_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key", "Stripe-Signature"],
    max_age=600,
)

# Import and register routers after app creation
from routers import websocket, relay, stripe_webhooks  # noqa: E402

app.include_router(websocket.router)
app.include_router(relay.router)
app.include_router(stripe_webhooks.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
