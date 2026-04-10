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
STALE_TTL_SECONDS = 2 * 60 * 60

app = FastAPI(title="Storm Chase", version="1.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

_cache: dict[str, dict[str, Any]] = {}
_inflight: dict[str, asyncio.Task] = {}
_lock = asyncio.Lock()


def _cache_key(lat: float, lon: float) -> str:
    # Rounded key to deduplicate "same practical zone" requests
    return f"{lat:.2f}:{lon:.2f}"


def _cache_fresh(entry: dict[str, Any] | None, ttl: int = CACHE_TTL_SECONDS) -> bool:
    if entry is None:
        return False
    return (time.time() - float(entry["ts"])) < ttl


def _merge_label(payload: dict[str, Any], label: str) -> dict[str, Any]:
    out = dict(payload)
    meta = dict(out.get("meta", {}))
    center = dict(meta.get("center", {}))
    center["label"] = label
    meta["center"] = center
    out["meta"] = meta
    return out


def _stale_payload(entry: dict[str, Any], label: str, warning: str) -> dict[str, Any]:
    stale = _merge_label(entry["payload"], label)
    meta = dict(stale.get("meta", {}))
    meta["warning"] = warning
    meta["stale"] = True
    meta["cached_at_epoch"] = entry["ts"]
    stale["meta"] = meta
    return stale


async def _build_payload(lat: float, lon: float, label: str) -> dict[str, Any]:
    payload = await asyncio.to_thread(build_latest_payload, lat, lon, label)
    return _merge_label(payload, label)


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
    key = _cache_key(lat, lon)

    # Fresh cache hit first, outside lock
    cached = _cache.get(key)
    if not force and _cache_fresh(cached):
        return _merge_label(cached["payload"], label)

    async with _lock:
        cached = _cache.get(key)
        if not force and _cache_fresh(cached):
            return _merge_label(cached["payload"], label)

        task = _inflight.get(key)
        if task is None or task.done():
            task = asyncio.create_task(_build_payload(lat, lon, label))
            _inflight[key] = task

    try:
        payload = await task
    except Exception as exc:
        async with _lock:
            if _inflight.get(key) is task:
                _inflight.pop(key, None)

        cached = _cache.get(key)
        if cached is not None and _cache_fresh(cached, ttl=STALE_TTL_SECONDS):
            return _stale_payload(
                cached,
                label=label,
                warning=f"Données mises en cache utilisées après erreur de rafraîchissement: {exc}",
            )
        raise HTTPException(status_code=502, detail=f"Weather refresh failed: {exc}")
    else:
        async with _lock:
            _cache[key] = {"ts": time.time(), "payload": payload}
            if _inflight.get(key) is task:
                _inflight.pop(key, None)
        return _merge_label(payload, label)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
