from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from weather_logic import DEFAULT_CENTER_LABEL, build_latest_payload

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
CACHE_TTL_SECONDS = 15 * 60

app = FastAPI(title="Storm Chase", version="1.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

_cache: dict[str, dict[str, Any]] = {}
_lock = asyncio.Lock()


def _cache_key(lat: float, lon: float, label: str) -> str:
    return f"{lat:.3f}:{lon:.3f}:{label.strip().lower()}"


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/latest")
async def latest(
    lat: float = Query(45.7640, ge=-90, le=90),
    lon: float = Query(4.8357, ge=-180, le=180),
    label: str = Query(DEFAULT_CENTER_LABEL, min_length=1, max_length=120),
    force: bool = False,
) -> dict:
    now = time.time()
    key = _cache_key(lat, lon, label)
    cached = _cache.get(key)
    if not force and cached is not None and now - cached["ts"] < CACHE_TTL_SECONDS:
        return cached["payload"]

    async with _lock:
        now = time.time()
        cached = _cache.get(key)
        if not force and cached is not None and now - cached["ts"] < CACHE_TTL_SECONDS:
            return cached["payload"]
        try:
            payload = await asyncio.to_thread(build_latest_payload, lat, lon, label)
        except Exception as exc:
            if cached is not None:
                stale = dict(cached["payload"])
                meta = dict(stale.get("meta", {}))
                meta["warning"] = f"Fallback stale cache after refresh error: {exc}"
                stale["meta"] = meta
                return stale
            raise HTTPException(status_code=502, detail=f"Weather refresh failed: {exc}")
        _cache[key] = {"ts": time.time(), "payload": payload}
        return payload


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
