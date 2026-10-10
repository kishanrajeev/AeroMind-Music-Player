"""Smoke tests

Usage:
    python scripts/smoke.py [base_url]

Exits non-zero if any contract check fails.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from core.types import API_VERSION, DEFAULT_N, KC_DIM  # noqa: E402

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")
FAILURES: list[str] = []


def request(
    method: str,
    path: str,
    body: Any = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, Any]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            raw = response.read()
            content_type = response.headers.get("content-type", "")
            payload = json.loads(raw) if "json" in content_type else None
            return response.status, payload
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            payload = json.loads(raw)
        except Exception:
            payload = None
        return exc.code, payload


def check(name: str, ok: bool, detail: str = "") -> None:
    if ok:
        print(f"PASS  {name}")
    else:
        FAILURES.append(name)
        print(f"FAIL  {name}" + (f"  ({detail})" if detail else ""))


def is_error(body: Any) -> bool:
    return (
        isinstance(body, dict)
        and body.get("version") == API_VERSION
        and body.get("ok") is False
        and isinstance(body.get("error"), str)
    )


def main() -> int:
    code, health = request("GET", "/health")
    if not isinstance(health, dict) or health.get("version") != API_VERSION:
        print(f"FAIL  server not reachable or wrong shape: {code} {health}")
        print("      start it with: python -m api.server --fixture")
        return 1
    fixture = bool(health.get("fixture_mode"))
    print(f"PASS  GET /health  (mode: {'fixture' if fixture else 'real'})")

    code, library = request("GET", "/library")
    tracks = (library or {}).get("tracks", [])
    check(
        "GET /library -> count == len(tracks)",
        code == 200 and library.get("count") == len(tracks),
        f"{code} {library}",
    )
    check(
        "library tracks have contract fields",
        bool(tracks)
        and all({"id", "title", "artist", "duration", "audio_url"} <= set(t) for t in tracks),
    )
    track_id = tracks[0]["id"] if tracks else ""

    code, playlist = request("GET", f"/playlist?q=rainy%20afternoon&alpha=0.5&n={DEFAULT_N}")
    check("GET /playlist -> 200 + version", code == 200 and playlist.get("version") == API_VERSION)
    play_tracks = (playlist or {}).get("tracks", [])
    score_fields = {"clap_score", "brain_score", "final_score"}
    check(
        "playlist scores present and within 0..1",
        bool(play_tracks)
        and all(
            score_fields <= set(t) and all(0.0 <= t[f] <= 1.0 for f in score_fields)
            for t in play_tracks
        ),
    )
    finals = [t["final_score"] for t in play_tracks]
    check("playlist sorted by final_score desc", finals == sorted(finals, reverse=True), str(finals[:5]))

    code, noquery = request("GET", "/playlist")
    check("GET /playlist with no q -> query null", code == 200 and noquery.get("query") is None)

    code, clamped = request("GET", "/playlist?alpha=2.5&n=9999")
    check(
        "alpha and n clamped server-side",
        code == 200 and clamped.get("alpha") == 1.0 and len(clamped.get("tracks", [])) <= 50,
        f"{code} alpha={clamped.get('alpha') if clamped else None}",
    )

    code, state = request("GET", f"/brain_state?track_id={track_id}")
    check("GET /brain_state -> 200", code == 200 and isinstance(state, dict), f"{code} {state}")
    check(
        f"kc_activity is exactly {KC_DIM} floats",
        isinstance(state, dict) and len(state.get("kc_activity", [])) == KC_DIM,
    )
    check(
        f"weights are exactly {KC_DIM} floats",
        isinstance(state, dict) and len(state.get("weights", [])) == KC_DIM,
    )
    check("brain_state echoes track_id", isinstance(state, dict) and state.get("track_id") == track_id)

    code, body = request("GET", "/brain_state?track_id=does-not-exist")
    check("unknown brain_state track -> 404 error shape", code == 404 and is_error(body), f"{code} {body}")

    code, body = request("POST", "/feedback", {"track_id": track_id, "reward": -1})
    check(
        "POST /feedback -> 200 + brain_state",
        code == 200 and (body or {}).get("ok") is True and "brain_state" in (body or {}),
        f"{code} {body}",
    )

    code, body = request("POST", "/feedback", {"track_id": "does-not-exist", "reward": -1})
    check("unknown feedback track -> 404 error shape", code == 404 and is_error(body), f"{code} {body}")

    code, body = request("POST", "/feedback", {"track_id": track_id, "reward": 7})
    check("bad reward -> 422 error shape", code == 422 and is_error(body), f"{code} {body}")

    code, body = request("GET", "/playlist?alpha=nope")
    check("bad alpha -> 422 error shape", code == 422 and is_error(body), f"{code} {body}")

    code, body = request("GET", "/no-such-route")
    check("unknown route -> 404 error shape", code == 404 and is_error(body), f"{code} {body}")

    code, _ = request("GET", "/docs")
    check("GET /docs -> 200", code == 200)
    code, spec = request("GET", "/openapi.json")
    paths = set((spec or {}).get("paths", {}))
    expected = {"/health", "/library", "/playlist", "/feedback", "/brain_state", "/audio/{track_id}"}
    check("OpenAPI lists all six endpoints", expected <= paths, str(sorted(paths)))

    if fixture:
        code, body = request("GET", f"/audio/{track_id}")
        check("fixture /audio -> 404 error shape", code == 404 and is_error(body), f"{code} {body}")
    else:
        code, _ = request("GET", f"/audio/{track_id}", headers={"Range": "bytes=0-1023"})
        check("real /audio honours Range -> 206", code == 206, f"{code}")

    print()
    if FAILURES:
        print(f"{len(FAILURES)} check(s) failed: {', '.join(FAILURES)}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
