"""FastAPI app: serves the docs REST API and the AI (SSE + JSON) endpoints."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config
from .routers import ai, docs


@asynccontextmanager
async def lifespan(_: FastAPI):
    config.ensure_dirs()
    yield


app = FastAPI(title="Plate Docs Backend", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(docs.router)
app.include_router(ai.router)


@app.get("/health")
async def health():
    return {"status": "ok"}