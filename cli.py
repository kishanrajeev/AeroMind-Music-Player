"""Headless CLI harness (spec §3, §10).

Run from the repo root:

    python cli.py export-fixture --placeholder # regenerate api/fixtures/
    python cli.py playlist "rainy afternoon" # fetch from a running server

Planned order: index, search, brain-state, calibrate.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from core.types import (  # noqa: E402
    API_VERSION,
    DEFAULT_ALPHA,
    DEFAULT_N,
    DEGENERATE_NORM,
    KC_DIM,
    NO_QUERY_CLAP_SCORE,
    RETRIEVE_POOL_SIZE,
)

FIXTURE_DIR = REPO / "api" / "fixtures"
FIXTURE_SEED = 20261010  # fixtures must regenerate byte-identical

#: 30 plausible Frutiger-Aero instrumental titles. Must match RETRIEVE_POOL_SIZE.
_TITLES: list[tuple[str, str]] = [
    ("Glass Pavement", "Aeroform"),
    ("Tidal Circuit", "Open Channel"),
    ("Velvet Static", "Blue Static"),
    ("Paper Lanterns", "Willow Machine"),
    ("Slow Orbit", "Pale Circuit"),
    ("Copper Rain", "Fern & Foam"),
    ("Neon Bath", "Vaporlane"),
    ("Soft Antenna", "Sonant"),
    ("Midnight Tape", "Glasshouse"),
    ("Drifting Signal", "Open Channel"),
    ("Amber Fog", "Willow Machine"),
    ("Chrome Garden", "Aeroform"),
    ("Quiet Tide", "Fern & Foam"),
    ("Hollow Bloom", "Pale Circuit"),
    ("Aero Current", "Vaporlane"),
    ("Transparent Room", "Glasshouse"),
    ("Pale Harbor", "Sonant"),
    ("Digital Willow", "Blue Static"),
    ("Winter Modem", "Vaporlane"),
    ("Blue Vapor", "Aeroform"),
    ("Static Canopy", "Open Channel"),
    ("Lantern Drift", "Willow Machine"),
    ("Deep Aquarium", "Fern & Foam"),
    ("Copper Orbit", "Pale Circuit"),
    ("Softwave", "Sonant"),
    ("Aqua Tape", "Glasshouse"),
    ("Quiet Modem", "Blue Static"),
    ("Sunrise Server", "Vaporlane"),
    ("Glass Tide", "Aeroform"),
    ("Memory Foam", "Fern & Foam"),
]
assert len(_TITLES) == RETRIEVE_POOL_SIZE


def _minmax(values: list[float]) -> list[float]:
    """Min-max with the spec §8 epsilon guard: degenerate pools -> 0.5."""
    lo, hi = min(values), max(values)
    if hi - lo < 1e-9:
        return [DEGENERATE_NORM] * len(values)
    return [(value - lo) / (hi - lo) for value in values]


def _scored(tracks: list[dict], alpha: float) -> list[dict]:
    """Blend and sort exactly the way the engine will (spec §8)."""
    scored = []
    for track in tracks:
        final = alpha * track["clap_score"] + (1.0 - alpha) * track["brain_score"]
        scored.append({**track, "final_score": round(final, 4)})
    scored.sort(key=lambda t: (-t["final_score"], -t["clap_score"], t["id"]))
    return scored


def _placeholder_tracks(rng: random.Random) -> list[dict]:
    """Canned-but-plausible tracks: scores are already normalized in-pool."""
    clap = _minmax([rng.uniform(0.05, 0.45) for _ in range(RETRIEVE_POOL_SIZE)])
    brain = _minmax([rng.gauss(0.0, 1.0) for _ in range(RETRIEVE_POOL_SIZE)])

    tracks = []
    for i, (title, artist) in enumerate(_TITLES):
        track_id = f"{i:02x}{rng.getrandbits(16):04x}"  # 6 hex chars, unique
        tracks.append(
            {
                "id": track_id,
                "title": title,
                "artist": artist,
                "duration": round(rng.uniform(120.0, 300.0), 1),
                "path": f"/music/{track_id}.flac",
                "audio_url": f"/audio/{track_id}",
                "clap_score": round(clap[i], 4),
                "brain_score": round(brain[i], 4),
            }
        )
    return tracks


def _placeholder_brain_state(track_id: str, rng: random.Random) -> dict:
    """2000 KC cells, ~8% active; weights sparse (real cold start is all zeros)."""
    kc_activity = [
        round(0.0 if rng.random() > 0.08 else rng.uniform(0.1, 1.0), 3)
        for _ in range(KC_DIM)
    ]
    weights = [0.0] * KC_DIM
    for _ in range(60):
        weights[rng.randrange(KC_DIM)] = round(rng.uniform(-0.25, 0.25), 3)

    return {
        "version": API_VERSION,
        "track_id": track_id,
        "mbon_output": 0.64,
        "kc_activity": kc_activity,
        "weights": weights,
        "feedback_count": 7,
    }


def export_fixtures(placeholder: bool) -> None:
    if not placeholder:
        raise SystemExit(
            "real-engine export arrives with the engine (spec §10 step 2).\n"
            "Run: python cli.py export-fixture --placeholder"
        )

    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    rng = random.Random(FIXTURE_SEED)

    tracks = _placeholder_tracks(rng)
    state = _placeholder_brain_state(tracks[0]["id"], rng)

    fixtures = {
        "health": {
            "version": API_VERSION,
            "ok": True,
            "library_size": len(tracks),
            "index_loaded": True,
            "fixture_mode": True,
        },
        "library": {"version": API_VERSION, "count": len(tracks), "tracks": tracks},
        "playlist": {
            "version": API_VERSION,
            "query": "rainy afternoon",
            "alpha": DEFAULT_ALPHA,
            "tracks": _scored([dict(t) for t in tracks], alpha=DEFAULT_ALPHA),
        },
        "playlist_noquery": {
            "version": API_VERSION,
            "query": None,
            "alpha": DEFAULT_ALPHA,
            "tracks": _scored(
                [{**t, "clap_score": NO_QUERY_CLAP_SCORE} for t in tracks],
                alpha=DEFAULT_ALPHA,
            ),
        },
        "brain_state": state,
        "feedback": {"version": API_VERSION, "ok": True, "brain_state": state},
    }

    for name, body in fixtures.items():
        path = FIXTURE_DIR / f"{name}.json"
        path.write_text(json.dumps(body, indent=2) + "\n")
        print(f"wrote {path.relative_to(REPO)}")


def fetch_playlist(args: argparse.Namespace) -> None:
    from urllib.parse import urlencode

    params: dict[str, object] = {"alpha": args.alpha, "n": args.n}
    if args.query:
        params["q"] = args.query
    url = f"{args.url.rstrip('/')}/playlist?{urlencode(params)}"

    try:
        with urllib.request.urlopen(url, timeout=15) as response:
            data = json.load(response)
    except urllib.error.URLError as exc:
        raise SystemExit(f"cannot reach {url}: {exc}") from exc

    print(f"query={data['query']!r}  alpha={data['alpha']}  tracks={len(data['tracks'])}")
    for i, track in enumerate(data["tracks"], 1):
        print(
            f"{i:2}. {track['title'][:24]:<24} {track['artist'][:16]:<16} "
            f"clap={track['clap_score']:.2f} brain={track['brain_score']:.2f} "
            f"final={track['final_score']:.2f}"
        )


def cmd_library(args: argparse.Namespace) -> None:
    import time

    import numpy as np

    from core.library import FEATURE_NAMES, key_label, scan_library

    root = Path(args.music_root).resolve()
    playlists = [Path(p) for p in args.playlist] if args.playlist else None
    started = time.time()

    def progress(index: int, count: int, _path: Path) -> None:
        if index % 25 == 0 or index == count:
            print(f"  scanned {index}/{count}", file=sys.stderr)

    scanned = scan_library(root, playlists, limit=args.limit or None, on_progress=progress)
    elapsed = time.time() - started

    print()
    print(
        f"{'#':>3}  {'id':8}  {'artist':<20}  {'title':<30}  {'dur':>5}  "
        f"{'bpm':>6}  {'key':>5}  {'rms':>7}  {'cent':>6}  {'roll':>6}  {'zcr':>5}  {'bw':>6}"
    )
    for i, item in enumerate(scanned, 1):
        track, f = item.track, item.features
        print(
            f"{i:>3}  {track.id:8}  {track.artist[:20]:<20}  {track.title[:30]:<30}  "
            f"{track.duration:5.0f}  {f[0]:6.1f}  {key_label(f):>5}  {f[1]:7.4f}  "
            f"{f[2]:6.0f}  {f[3]:6.0f}  {f[4]:5.3f}  {f[5]:6.0f}"
        )

    matrix = (
        np.stack([item.features for item in scanned])
        if scanned
        else np.zeros((0, len(FEATURE_NAMES)))
    )
    print()
    print(f"{len(scanned)} tracks in {elapsed:.1f}s  |  feature matrix {matrix.shape}")
    if matrix.size:
        print("raw range per feature (watch for degenerate columns):")
        for name, lo, hi in zip(FEATURE_NAMES, matrix.min(axis=0), matrix.max(axis=0)):
            print(f"  {name:>10}: {lo:12.4f} .. {hi:12.4f}")


def cmd_index(args: argparse.Namespace) -> None:
    import time

    import numpy as np

    from core.index import INDEX_PATH, IndexMismatch, build_index, load_index, save_index

    out = Path(args.out) if args.out else INDEX_PATH
    if out.exists() and not args.force:
        try:
            data = load_index(out)
        except IndexMismatch as exc:
            print(f"stale index ({exc}) — rebuilding", file=sys.stderr)
        else:
            norms = np.linalg.norm(data.embeddings, axis=1)
            print(f"index OK: {len(data.tracks)} tracks")
            print(f"  path:         {out}")
            print(f"  embeddings:   {data.embeddings.shape} (norm {norms.min():.4f}..{norms.max():.4f})")
            print(f"  features:     {data.features.shape}")
            print(f"  created_at:   {data.meta.get('created_at')}")
            model = f"{data.meta.get('model_id')} rev={data.meta.get('model_revision') or '(unknown)'}"
            print(f"  model:        {model}")
            print(f"  transformers: {data.meta.get('transformers_version')}")
            return

    if not args.music_root:
        raise SystemExit("--music-root is required to build an index")

    root = Path(args.music_root).resolve()
    playlists = [Path(p) for p in args.playlist] if args.playlist else None
    started = time.time()

    def on_scan(index: int, count: int, _path: Path) -> None:
        if index % 25 == 0 or index == count:
            print(f"  scanned {index}/{count}", file=sys.stderr)

    def on_embed(index: int, count: int) -> None:
        if index % 25 == 0 or index == count:
            print(f"  embedded {index}/{count}", file=sys.stderr)

    data = build_index(
        root,
        playlists,
        limit=args.limit or None,
        on_scan=on_scan,
        on_embed=on_embed,
        device=args.device,
    )
    save_index(data, out)
    print(f"built index: {len(data.tracks)} tracks in {time.time() - started:.1f}s -> {out}")
    print(
        f"  embeddings {data.embeddings.shape}  features {data.features.shape}  "
        f"offsets {data.offsets.shape}"
    )
    print(f"  model: {data.meta['model_id']} rev={data.meta['model_revision'] or '(unknown)'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    export = sub.add_parser("export-fixture", help="regenerate api/fixtures/*.json")
    export.add_argument(
        "--placeholder",
        action="store_true",
        help="deterministic stand-in data (used until the real engine exists)",
    )
    export.set_defaults(func=lambda args: export_fixtures(args.placeholder))

    playlist = sub.add_parser("playlist", help="fetch /playlist from a running server")
    playlist.add_argument("query", nargs="?", default=None)
    playlist.add_argument("--alpha", type=float, default=DEFAULT_ALPHA)
    playlist.add_argument("--n", type=int, default=DEFAULT_N)
    playlist.add_argument("--url", default="http://127.0.0.1:8000")
    playlist.set_defaults(func=fetch_playlist)

    library = sub.add_parser("library", help="scan a music root and print the audio-feature table")
    library.add_argument("--music-root", required=True, help="root the m3u entries resolve against")
    library.add_argument(
        "--playlist", nargs="*", default=None, help="m3u file(s); omit to scan the whole root"
    )
    library.add_argument("--limit", type=int, default=20, help="max tracks (0 = all)")
    library.set_defaults(func=cmd_library)

    index = sub.add_parser("index", help="build/load data/index.npz (CLAP embeddings + features)")
    index.add_argument("--music-root", default=None, help="required to build; not needed to inspect")
    index.add_argument(
        "--playlist", nargs="*", default=None, help="m3u file(s); omit to scan the whole root"
    )
    index.add_argument("--limit", type=int, default=0, help="max tracks (0 = all)")
    index.add_argument("--out", type=Path, default=None, help="index path (default data/index.npz)")
    index.add_argument("--device", default=None, help="cpu (default) or cuda (ROCm answers as cuda)")
    index.add_argument("--force", action="store_true", help="rebuild even if a valid index exists")
    index.set_defaults(func=cmd_index)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
