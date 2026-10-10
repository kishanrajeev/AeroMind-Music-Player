"""HTTP server.

The core is headless (spec §3): this process owns the library, index, search,
brain and audio files, it never touches an audio device.

    python -m api.server --fixture   # canned JSON from api/fixtures/
    python -m api.server             # real engine (core/engine.py)

Interactive contract: http://127.0.0.1:8000/docs
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

if __package__ in (None, ""):  # allow `python api/server.py` as well as `-m`
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.types import (  # noqa: E402
    API_VERSION,
    DEFAULT_ALPHA,
    DEFAULT_N,
    KC_DIM,
    MAX_N,
    MIN_N,
    VALID_REWARDS,
)

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
FIXTURE_MODE = ("--fixture" in sys.argv) or os.environ.get("HACKNC_FIXTURE") == "1"

REQUIRED_FIXTURES = (
    "health",
    "library",
    "playlist",
    "playlist_noquery",
    "brain_state",
    "feedback",
)


def load_fixture(name: str) -> dict[str, Any]:
    """Load one canned response. Shapes are the contract — validate loudly."""
    path = FIXTURE_DIR / f"{name}.json"
    if not path.exists():
        raise RuntimeError(
            f"missing fixture {path} — run: python cli.py export-fixture --placeholder"
        )
    data = json.loads(path.read_text())
    if data.get("version") != API_VERSION:
        raise RuntimeError(
            f"fixture {path.name}: version {data.get('version')!r} != {API_VERSION!r} "
            "— regenerate fixtures"
        )
    return data


def _error_body(message: str) -> dict[str, Any]:
    return {"version": API_VERSION, "ok": False, "error": message}


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _engine(request: Request):
    engine = getattr(request.app.state, "engine", None)
    if engine is None:
        raise HTTPException(status_code=503, detail="engine not available")
    return engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    if FIXTURE_MODE:
        for name in REQUIRED_FIXTURES:
            data = load_fixture(name)
            state = data.get("brain_state", data)
            for key in ("kc_activity", "weights"):
                if key in state and len(state[key]) != KC_DIM:
                    raise RuntimeError(
                        f"fixture {name}.json: {key} has {len(state[key])} values, "
                        f"expected {KC_DIM}"
                    )
    else:
        try:
            from core.engine import Engine
        except Exception as exc:
            raise RuntimeError(
                "real engine unavailable (core/engine.py) — run with --fixture "
                "for canned data, or build the engine (spec §10 step 7)"
            ) from exc
        app.state.engine = Engine()
    yield


app = FastAPI(title="HackNC 2026 core", version=API_VERSION, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(StarletteHTTPException)
async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=_error_body(str(exc.detail)))


@app.exception_handler(RequestValidationError)
async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    errors = exc.errors()
    first = errors[0] if errors else {}
    loc = ".".join(str(part) for part in first.get("loc", ()))
    message = f"{loc}: {first.get('msg', 'invalid request')}".lstrip(": ")
    return JSONResponse(status_code=422, content=_error_body(message))


@app.get("/health", summary="Server liveness and mode")
def health(request: Request) -> dict[str, Any]:
    if FIXTURE_MODE:
        body = load_fixture("health")
        body["fixture_mode"] = True
        body["library_size"] = len(load_fixture("library")["tracks"])
        return body
    engine = _engine(request)
    return {
        "version": API_VERSION,
        "ok": True,
        "library_size": len(engine.library()),
        "index_loaded": bool(getattr(engine, "index_loaded", True)),
        "fixture_mode": False,
    }


@app.get("/library", summary="All tracks")
def library(request: Request) -> dict[str, Any]:
    if FIXTURE_MODE:
        return load_fixture("library")
    tracks = [asdict(track) for track in _engine(request).library()]
    return {"version": API_VERSION, "count": len(tracks), "tracks": tracks}


@app.get("/playlist", summary="Search + taste blend")
def playlist(
    request: Request,
    q: str | None = Query(
        default=None, description="English phrase; omit for a taste-only playlist"
    ),
    alpha: float = Query(
        default=DEFAULT_ALPHA, description="1.0 = phrase only, 0.0 = brain only"
    ),
    n: int = Query(default=DEFAULT_N, description=f"Displayed tracks ({MIN_N}-{MAX_N})"),
) -> dict[str, Any]:
    alpha = _clamp(alpha, 0.0, 1.0)
    n = int(_clamp(n, MIN_N, MAX_N))
    query = (q or "").strip() or None

    if FIXTURE_MODE:
        data = load_fixture("playlist" if query else "playlist_noquery")
        tracks = data["tracks"]
        # Same blend formula as the engine, so the alpha slider works pre-engine.
        for track in tracks:
            track["final_score"] = round(
                alpha * track["clap_score"] + (1.0 - alpha) * track["brain_score"], 4
            )
        tracks.sort(key=lambda t: (-t["final_score"], -t["clap_score"], t["id"]))
        return {
            "version": API_VERSION,
            "query": query,
            "alpha": alpha,
            "tracks": tracks[:n],
        }

    scored = _engine(request).playlist(query, alpha, n)
    return {
        "version": API_VERSION,
        "query": query,
        "alpha": alpha,
        "tracks": [asdict(track) for track in scored],
    }


class FeedbackBody(BaseModel):
    track_id: str
    reward: int


@app.post("/feedback", summary="Teach the brain (skip / neutral / listen-through)")
def feedback(request: Request, body: FeedbackBody) -> dict[str, Any]:
    if body.reward not in VALID_REWARDS:
        raise HTTPException(
            status_code=422, detail=f"reward must be one of {list(VALID_REWARDS)}"
        )

    if FIXTURE_MODE:
        ids = {track["id"] for track in load_fixture("library")["tracks"]}
        if body.track_id not in ids:
            raise HTTPException(status_code=404, detail=f"unknown track_id: {body.track_id}")
        state = dict(load_fixture("feedback")["brain_state"])
        state["track_id"] = body.track_id
        return {"version": API_VERSION, "ok": True, "brain_state": state}

    try:
        state = _engine(request).feedback(body.track_id, body.reward)
    except KeyError as exc:
        raise HTTPException(
            status_code=404, detail=f"unknown track_id: {body.track_id}"
        ) from exc
    return {"version": API_VERSION, "ok": True, "brain_state": asdict(state)}


@app.get("/brain_state", summary="Mushroom-body state for the visualizer")
def brain_state(
    request: Request, track_id: str = Query(..., description="track currently displayed")
) -> dict[str, Any]:
    if FIXTURE_MODE:
        ids = {track["id"] for track in load_fixture("library")["tracks"]}
        if track_id not in ids:
            raise HTTPException(status_code=404, detail=f"unknown track_id: {track_id}")
        state = dict(load_fixture("brain_state"))
        state["track_id"] = track_id
        return state

    try:
        state = _engine(request).brain_state(track_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"unknown track_id: {track_id}") from exc
    return {"version": API_VERSION, **asdict(state)}


@app.get("/audio/{track_id}", summary="Stream audio (supports Range)")
def audio(request: Request, track_id: str) -> FileResponse:
    if FIXTURE_MODE:
        raise HTTPException(
            status_code=404,
            detail="fixture mode has no audio files; run without --fixture for /audio",
        )
    try:
        path = Path(_engine(request).audio_path(track_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"unknown track_id: {track_id}") from exc
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"audio file missing for {track_id}")
    return FileResponse(path)  # Starlette FileResponse honours Range requests


@app.get("/cover/{track_id}", summary="Embedded album art thumbnail")
def cover(request: Request, track_id: str) -> Response:
    if FIXTURE_MODE:
        raise HTTPException(
            status_code=404, detail="fixture mode has no cover art; run without --fixture"
        )
    try:
        art = _engine(request).cover(track_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"unknown track_id: {track_id}") from exc
    if art is None:
        raise HTTPException(status_code=404, detail=f"no embedded cover for {track_id}")
    payload, mime = art
    return Response(
        content=payload,
        media_type=mime,
        headers={"Cache-Control": "public, max-age=3600"},
    )


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m api.server", description=__doc__)
    parser.add_argument(
        "--fixture", action="store_true", help="serve api/fixtures/*.json instead of the engine"
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.environ.get("HACKNC_PORT", "8000")))
    parser.add_argument("--reload", action="store_true", help="auto-reload on code changes (dev)")
    args = parser.parse_args()

    if args.fixture:
        os.environ["HACKNC_FIXTURE"] = "1"  # visible to the uvicorn reloader child

    import uvicorn

    target = "api.server:app" if args.reload else app
    uvicorn.run(target, host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
