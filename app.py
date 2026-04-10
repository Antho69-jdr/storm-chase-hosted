from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from weather_logic import build_latest_payload

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
CACHE_TTL_SECONDS = 15 * 60

app = FastAPI(title="Storm Chase", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

_cache: dict[str, Any] = {"ts": 0.0, "payload": None}
_lock = asyncio.Lock()


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/latest")
async def latest(force: bool = False) -> dict:
    now = time.time()
    if not force and _cache["payload"] is not None and now - _cache["ts"] < CACHE_TTL_SECONDS:
        return _cache["payload"]

    async with _lock:
        now = time.time()
        if not force and _cache["payload"] is not None and now - _cache["ts"] < CACHE_TTL_SECONDS:
            return _cache["payload"]
        try:
            payload = await asyncio.to_thread(build_latest_payload)
        except Exception as exc:
            if _cache["payload"] is not None:
                stale = dict(_cache["payload"])
                meta = dict(stale.get("meta", {}))
                meta["warning"] = f"Fallback stale cache after refresh error: {exc}"
                stale["meta"] = meta
                return stale
            raise HTTPException(status_code=502, detail=f"Weather refresh failed: {exc}")
        _cache["payload"] = payload
        _cache["ts"] = time.time()
        return payload


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
