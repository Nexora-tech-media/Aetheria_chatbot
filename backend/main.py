"""
Chatbot API: FastAPI + BazaarLink (OpenAI-compatible gateway).

Run (dev):   uvicorn main:app --reload --port 8000
Docs (dev):  http://localhost:8000/docs
"""

import json
import logging
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import AsyncIterator, Literal

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    RateLimitError,
)
from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("chatbot")


# --------------------------------------------------------------------------- #
# Configuration (loaded from environment / .env, never hardcode the API key)
# --------------------------------------------------------------------------- #
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bazaarlink_api_key: SecretStr  # required; app refuses to start without it
    # BazaarLink's docs show two base URLs (see notes); keep it configurable.
    bazaarlink_base_url: str = "https://bazaarlink.ai/api/v1"
    # Must be a full "provider/model" ID that exists in GET {base_url}/models
    bazaarlink_model: str = "auto:free"
    system_prompt: str = "You are a helpful, concise assistant."
    max_output_tokens: int = 1000
    request_timeout_seconds: float = 60.0
    cors_origins: str = [
        "http://localhost:5173",
        "http://localhost:3000"
        ]

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


# --------------------------------------------------------------------------- #
# App lifecycle: one shared async client for the whole process
# --------------------------------------------------------------------------- #
@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    app.state.client = AsyncOpenAI(
        api_key=s.bazaarlink_api_key.get_secret_value(),
        base_url=s.bazaarlink_base_url,
        timeout=s.request_timeout_seconds,
        max_retries=2,
    )
    logger.info("Started. base_url=%s model=%s", s.bazaarlink_base_url, s.bazaarlink_model)
    yield
    await app.state.client.close()


app = FastAPI(
    title="Chatbot API",
    version="1.0.0",
    lifespan=lifespan
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,  # explicit origins, never "*" with credentials
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


def get_client(request: Request) -> AsyncOpenAI:
    return request.app.state.client


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #
class ChatMessage(BaseModel):
    # "system" is intentionally NOT allowed: the server owns the system prompt,
    # so a browser user can't override it.
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8000)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=50)


class ChatResponse(BaseModel):
    reply: str
    model: str | None = None


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def build_messages(req: ChatRequest, settings: Settings) -> list[dict]:
    return [
        {"role": "system", "content": settings.system_prompt},
        *[m.model_dump() for m in req.messages],
    ]


def to_http_error(exc: Exception) -> HTTPException:
    """Map upstream errors to safe, client-friendly responses (no key/detail leaks)."""
    if isinstance(exc, AuthenticationError):
        logger.error("Upstream auth failed: check BAZAARLINK_API_KEY / base URL")
        return HTTPException(502, "Chat service is misconfigured.")
    if isinstance(exc, RateLimitError):
        return HTTPException(429, "Too many requests. Please try again shortly.")
    if isinstance(exc, APITimeoutError):
        return HTTPException(504, "The AI provider timed out.")
    if isinstance(exc, APIConnectionError):
        logger.error("Cannot reach BazaarLink: %s", exc)
        return HTTPException(502, "Cannot reach the AI provider.")
    if isinstance(exc, APIStatusError):
        logger.error("Upstream error %s: %s", exc.status_code, exc.response.text[:500])
        # 400/404 here usually means a bad model ID or unsupported parameter
        return HTTPException(502, "The AI provider returned an error.")
    logger.exception("Unexpected error")
    return HTTPException(500, "Internal server error.")


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    client: AsyncOpenAI = Depends(get_client),
    settings: Settings = Depends(get_settings),
):
    """Non-streaming: returns the full reply at once."""
    try:
        completion = await client.chat.completions.create(
            model=settings.bazaarlink_model,
            messages=build_messages(req, settings),
            max_tokens=settings.max_output_tokens,
        )
    except Exception as exc:
        raise to_http_error(exc) from exc

    reply = completion.choices[0].message.content or ""
    return ChatResponse(reply=reply, model=completion.model)


@app.post("/api/chat/stream")
async def chat_stream(
    req: ChatRequest,
    client: AsyncOpenAI = Depends(get_client),
    settings: Settings = Depends(get_settings),
):
    """Streaming via Server-Sent Events. Each event: `data: {"delta": "..."}`;
    final event: `data: [DONE]`; errors: `data: {"error": "..."}`."""
    try:
        # Open the upstream stream BEFORE returning, so auth/model/rate-limit
        # failures surface as proper HTTP status codes instead of a broken stream.
        stream = await client.chat.completions.create(
            model=settings.bazaarlink_model,
            messages=build_messages(req, settings),
            max_tokens=settings.max_output_tokens,
            stream=True,
        )
    except Exception as exc:
        raise to_http_error(exc) from exc

    async def event_source() -> AsyncIterator[str]:
        try:
            async for chunk in stream:
                if not chunk.choices:  # some providers send usage-only chunks
                    continue
                delta = chunk.choices[0].delta.content
                if delta:
                    yield f"data: {json.dumps({'delta': delta})}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as exc:  # mid-stream failure: headers already sent
            logger.exception("Stream failed mid-response")
            yield f"data: {json.dumps({'error': to_http_error(exc).detail})}\n\n"

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # stop nginx from buffering the stream
        },
    )
