"""CLAP index: build, persist and load (spec §6, §9).

``data/index.npz`` holds, aligned by row:

- Track metadata (id, title, artist, duration, path)
- 512-d CLAP audio embeddings: 5 segments -> mean-pool -> L2-normalize
- raw 9-d brain features from core.library (so brain.py never re-decodes audio)
- per-track segment offsets actually used

The file is self-contained: the engine serves the library from it without
re-scanning audio. Every artifact carries a header, and load_index() fails
loudly on mismatch (spec §9) instead of silently mixing incompatible caches.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
import transformers
from transformers import ClapModel, ClapProcessor

from core.library import (
    FEATURE_NAMES,
    SAMPLE_RATE,
    SEGMENT_FRACTIONS,
    SEGMENT_SECONDS,
    feature_list_hash,
    load_segment,
    scan_library,
    segment_offsets,
)
from core.types import Track

MODEL_ID = "laion/clap-htsat-unfused"
INDEX_VERSION = "index-2"
EMBEDDING_DIM = 512
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
INDEX_PATH = DATA_DIR / "index.npz"


class IndexMismatch(RuntimeError):
    """Cached index does not match the current runtime config — rebuild it."""


@dataclass
class IndexData:
    tracks: list[Track]
    embeddings: np.ndarray  # (N, 512) float32, L2-normalized
    features: np.ndarray  # (N, len(FEATURE_NAMES)) float32, raw
    offsets: np.ndarray  # (N, len(SEGMENT_FRACTIONS)) float32
    meta: dict[str, str]


def pick_device() -> str:
    """CPU by default; ROCm builds answer through torch.cuda, same as CUDA."""
    requested = os.environ.get("HACKNC_DEVICE")
    if requested:
        return requested
    return "cuda" if torch.cuda.is_available() else "cpu"


def load_clap(device: str | None = None):
    device = device or pick_device()
    processor = ClapProcessor.from_pretrained(MODEL_ID)
    model = ClapModel.from_pretrained(MODEL_ID).eval().to(device)
    return processor, model, device


def embed_track(path: Path, duration: float, processor, model, device: str) -> np.ndarray:
    """3-segment mean-pooled, L2-normalized CLAP embedding (512,)."""
    segments = []
    for offset in segment_offsets(duration):
        y = load_segment(path, offset)
        inputs = processor(
            audio=[y], sampling_rate=SAMPLE_RATE, return_tensors="pt"
        ).to(device)
        with torch.no_grad():
            segments.append(model.get_audio_features(**inputs).pooler_output[0])
    pooled = torch.stack(segments).mean(dim=0)
    return F.normalize(pooled, dim=-1).float().cpu().numpy()


# ---------------------------------------------------------------------------
# header
# ---------------------------------------------------------------------------
def _track_id_list_hash(ids) -> str:
    return hashlib.sha1("|".join(sorted(ids)).encode("utf-8")).hexdigest()


def _feature_extractor_hash(processor) -> str:
    payload = json.dumps(processor.feature_extractor.to_dict(), sort_keys=True, default=str)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def _model_revision() -> str:
    """Best-effort local revision: transformers 5 no longer sets _commit_hash."""
    try:
        from huggingface_hub import constants

        ref = (
            Path(constants.HF_HUB_CACHE)
            / f"models--{MODEL_ID.replace('/', '--')}"
            / "refs"
            / "main"
        )
        if ref.is_file():
            return ref.read_text().strip()
    except Exception:
        pass
    return ""


def _header(processor, model, tracks: list[Track]) -> dict[str, str]:
    return {
        "index_version": INDEX_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model_id": MODEL_ID,
        "model_revision": str(getattr(model.config, "_commit_hash", "") or _model_revision()),
        "transformers_version": transformers.__version__,
        "feature_extractor_config_hash": _feature_extractor_hash(processor),
        "feature_list_hash": feature_list_hash(),
        "feature_names": "|".join(FEATURE_NAMES),
        "sample_rate": str(SAMPLE_RATE),
        "segment_seconds": str(SEGMENT_SECONDS),
        "segment_fractions": ",".join(f"{f:.3f}" for f in SEGMENT_FRACTIONS),
        "embedding_dim": str(EMBEDDING_DIM),
        "track_count": str(len(tracks)),
        "track_id_list_hash": _track_id_list_hash(t.id for t in tracks),
    }


# ---------------------------------------------------------------------------
# build / save / load
# ---------------------------------------------------------------------------
def build_index(
    root: Path,
    playlists: list[Path] | None = None,
    limit: int | None = None,
    on_scan=None,
    on_embed=None,
    device: str | None = None,
) -> IndexData:
    scanned = scan_library(root, playlists, limit=limit, on_progress=on_scan)
    if not scanned:
        raise RuntimeError("no tracks found — check --music-root / --playlist")

    processor, model, device = load_clap(device)
    embeddings: list[np.ndarray] = []
    offsets: list[list[float]] = []
    for index, item in enumerate(scanned, 1):
        embeddings.append(
            embed_track(
                Path(item.track.path), item.track.duration, processor, model, device
            )
        )
        offsets.append(segment_offsets(item.track.duration))
        if on_embed is not None:
            on_embed(index, len(scanned))

    tracks = [item.track for item in scanned]
    return IndexData(
        tracks=tracks,
        embeddings=np.stack(embeddings).astype("float32"),
        features=np.stack([item.features for item in scanned]).astype("float32"),
        offsets=np.asarray(offsets, dtype="float32"),
        meta=_header(processor, model, tracks),
    )


_REQUIRED_ARRAYS = (
    "track_ids",
    "titles",
    "artists",
    "durations",
    "paths",
    "embeddings",
    "features",
    "offsets",
    "meta_json",
)


def save_index(data: IndexData, path: Path = INDEX_PATH) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "wb") as handle:  # file handle: no automatic .npz suffix
        np.savez_compressed(
            handle,
            track_ids=np.array([t.id for t in data.tracks]),
            titles=np.array([t.title for t in data.tracks]),
            artists=np.array([t.artist for t in data.tracks]),
            durations=np.array([t.duration for t in data.tracks], dtype="float64"),
            paths=np.array([t.path for t in data.tracks]),
            embeddings=data.embeddings.astype("float32"),
            features=data.features.astype("float32"),
            offsets=data.offsets.astype("float32"),
            meta_json=np.array(json.dumps(data.meta, sort_keys=True)),
        )
    tmp.replace(path)


def _validate(
    meta: dict[str, str],
    track_ids: list[str],
    embeddings: np.ndarray,
    features: np.ndarray,
    offsets: np.ndarray,
) -> None:
    expected = {
        "index_version": INDEX_VERSION,
        "model_id": MODEL_ID,
        "feature_list_hash": feature_list_hash(),
        "sample_rate": str(SAMPLE_RATE),
        "segment_seconds": str(SEGMENT_SECONDS),
        "segment_fractions": ",".join(f"{f:.3f}" for f in SEGMENT_FRACTIONS),
        "embedding_dim": str(EMBEDDING_DIM),
    }
    for key, want in expected.items():
        found = meta.get(key)
        if found != want:
            raise IndexMismatch(f"{key}: {found!r} != {want!r} — rebuild index")

    count = len(track_ids)
    if meta.get("track_count") != str(count):
        raise IndexMismatch(f"track_count: {meta.get('track_count')} != {count} — rebuild index")
    if meta.get("track_id_list_hash") != _track_id_list_hash(track_ids):
        raise IndexMismatch("track id list changed — rebuild index")
    if embeddings.shape != (count, EMBEDDING_DIM):
        raise IndexMismatch(f"embeddings shape {embeddings.shape} != ({count}, {EMBEDDING_DIM})")
    if features.shape != (count, len(FEATURE_NAMES)):
        raise IndexMismatch(f"features shape {features.shape} != ({count}, {len(FEATURE_NAMES)})")
    if offsets.shape != (count, len(SEGMENT_FRACTIONS)):
        raise IndexMismatch(
            f"offsets shape {offsets.shape} != ({count}, {len(SEGMENT_FRACTIONS)})"
        )


def load_index(path: Path = INDEX_PATH) -> IndexData:
    path = Path(path)
    if not path.exists():
        raise IndexMismatch(f"no index at {path}")

    with np.load(path, allow_pickle=False) as npz:
        missing = [name for name in _REQUIRED_ARRAYS if name not in npz.files]
        if missing:
            raise IndexMismatch(f"{path.name}: missing arrays {missing} — rebuild index")
        meta = json.loads(str(npz["meta_json"]))
        track_ids = [str(x) for x in npz["track_ids"].tolist()]
        titles = [str(x) for x in npz["titles"].tolist()]
        artists = [str(x) for x in npz["artists"].tolist()]
        durations = npz["durations"].astype(float).tolist()
        paths = [str(x) for x in npz["paths"].tolist()]
        embeddings = npz["embeddings"].astype("float32")
        features = npz["features"].astype("float32")
        offsets = npz["offsets"].astype("float32")

    _validate(meta, track_ids, embeddings, features, offsets)

    tracks = [
        Track(
            id=track_id,
            title=title,
            artist=artist,
            duration=duration,
            path=track_path,
            audio_url=f"/audio/{track_id}",
        )
        for track_id, title, artist, duration, track_path in zip(
            track_ids, titles, artists, durations, paths
        )
    ]
    return IndexData(
        tracks=tracks,
        embeddings=embeddings,
        features=features,
        offsets=offsets,
        meta=meta,
    )


def ensure_index(
    root: Path | None = None,
    playlists: list[Path] | None = None,
    limit: int | None = None,
    path: Path = INDEX_PATH,
    force: bool = False,
    on_scan=None,
    on_embed=None,
    device: str | None = None,
) -> IndexData:
    """Load a valid index or rebuild it (spec §9: mismatch -> rebuild, don't guess)."""
    if path.exists() and not force:
        try:
            return load_index(path)
        except IndexMismatch:
            if root is None:
                raise
    if root is None:
        raise IndexMismatch(f"index missing or stale at {path} and no music root given")
    data = build_index(
        root,
        playlists,
        limit=limit,
        on_scan=on_scan,
        on_embed=on_embed,
        device=device,
    )
    save_index(data, path)
    return data
