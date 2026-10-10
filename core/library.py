"""Library scanning, metadata and audio features (spec §6, §7).

Owns:
- playlist/directory resolution -> concrete audio paths
- metadata (mutagen tags + duration) -> core.types.Track
- a deterministic 9-dim feature vector for the mushroom body

The feature recipe is frozen by FEATURE_VERSION + FEATURE_NAMES. Changing either
invalidates every brain.npz that stores ``feature_list_hash`` (spec §9): bump
FEATURE_VERSION and rebuild the brain.

Segment sampling matches the CLAP index recipe (spec §6): 10 s windows at
25% / 50% / 75% of the track. Features are averaged across segments (tempo uses
the median); key/mode are detected once from the mean chroma, and key is encoded
as sin/cos so it stays non-circular when z-scored.

No CLAP here (index.py owns embeddings) and no z-scoring here (brain.py owns
that, persisting mean/std in brain.npz per spec §7).
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

import librosa
import mutagen
import numpy as np
import soundfile as sf

from core.types import Track

SAMPLE_RATE = 48000
SEGMENT_SECONDS = 10
SEGMENT_FRACTIONS = (0.25, 0.50, 0.75)
AUDIO_EXTENSIONS = {".flac", ".mp3", ".m4a", ".ogg", ".opus", ".wav"}

FEATURE_VERSION = "feat-1"
FEATURE_NAMES = (
    "tempo",  # BPM
    "rms",  # mean frame energy
    "centroid",  # spectral centroid (Hz)
    "rolloff",  # 85% spectral rolloff (Hz)
    "zcr",  # zero-crossing rate
    "bandwidth",  # spectral bandwidth (Hz)
    "key_sin",  # chroma key encoded on the unit circle
    "key_cos",
    "mode",  # 1.0 = major, 0.0 = minor
)

#: Krumhansl-Schmuckler key profiles, rotated per candidate tonic.
_MAJOR_PROFILE = np.array(
    [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
)
_MINOR_PROFILE = np.array(
    [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]
)

_KEY_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


@dataclass(frozen=True)
class ScannedTrack:
    track: Track
    features: np.ndarray  # (len(FEATURE_NAMES),) raw, un-z-scored
    labels: tuple[str, ...]  # source playlists; empty for directory scans


def feature_list_hash() -> str:
    payload = FEATURE_VERSION + "|" + "|".join(FEATURE_NAMES)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# path collection
# ---------------------------------------------------------------------------
def resolve_entry(entry: str, root: Path) -> Path | None:
    """Resolve one m3u entry (phone-absolute, absolute, relative, or basename)."""
    entry = unquote(entry).replace("\\", "/")
    candidates = []
    prefix = "/storage/emulated/0/Music/"
    if entry.startswith(prefix):
        candidates.append(root / entry[len(prefix) :])
    if entry.startswith("/"):
        candidates.append(root / entry.lstrip("/"))
    candidates.append(root / entry)
    candidates.append(root / Path(entry).name)
    return next((c for c in candidates if c.is_file()), None)


def parse_playlists(
    playlists: list[Path], root: Path
) -> tuple[list[Path], dict[Path, tuple[str, ...]]]:
    """Deduped tracks in first-seen order, plus path -> playlist names."""
    tracks: list[Path] = []
    labels: dict[Path, list[str]] = {}
    seen: set[Path] = set()
    for playlist in playlists:
        playlist = playlist if playlist.is_absolute() else root / playlist
        if not playlist.exists():
            print(f"warning: playlist not found: {playlist}", file=sys.stderr)
            continue
        missing = 0
        for raw in playlist.read_text(errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            path = resolve_entry(line, root)
            if path is None:
                missing += 1
                continue
            path = path.resolve()
            if path not in seen:
                seen.add(path)
                tracks.append(path)
            labels.setdefault(path, []).append(playlist.stem)
        if missing:
            print(
                f"warning: {playlist.name}: {missing} entries could not be resolved",
                file=sys.stderr,
            )
    return tracks, {path: tuple(names) for path, names in labels.items()}


def collect_paths(
    root: Path, playlists: list[Path] | None = None
) -> tuple[list[Path], dict[Path, tuple[str, ...]]]:
    if playlists:
        return parse_playlists(playlists, root)
    paths = sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS
    )
    return paths, {path: () for path in paths}


# ---------------------------------------------------------------------------
# audio loading
# ---------------------------------------------------------------------------
def segment_offsets(duration: float) -> list[float]:
    if duration <= SEGMENT_SECONDS:
        return [0.0]
    return [
        min(max(frac * duration, 0.0), duration - SEGMENT_SECONDS)
        for frac in SEGMENT_FRACTIONS
    ]


def duration_seconds(path: Path) -> float:
    try:
        handle = mutagen.File(path, easy=True)
        if handle is not None and getattr(handle, "info", None) and handle.info.length:
            return float(handle.info.length)
    except Exception:
        pass
    try:
        info = sf.info(path)
        return float(info.frames / info.samplerate)
    except Exception:
        return float(librosa.get_duration(path=path))


def _ffmpeg_segment(path: Path, offset: float, seconds: int, sr: int) -> np.ndarray:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError(f"cannot decode {path.name} (no ffmpeg)")
    cmd = [
        "ffmpeg", "-v", "error",
        "-ss", f"{offset:.3f}", "-t", str(seconds),
        "-i", str(path),
        "-ac", "1", "-ar", str(sr),
        "-f", "f32le", "pipe:1",
    ]
    out = subprocess.run(cmd, capture_output=True, check=True).stdout
    return np.frombuffer(out, dtype="<f4").copy()


def load_segment(
    path: Path, offset: float, *, sr: int = SAMPLE_RATE, seconds: int = SEGMENT_SECONDS
) -> np.ndarray:
    """Load one padded 10 s mono float32 window at 48 kHz."""
    try:
        y, _ = librosa.load(path, sr=sr, mono=True, offset=offset, duration=seconds)
    except Exception:
        y = _ffmpeg_segment(path, offset, seconds, sr)
    y = np.asarray(y, dtype=np.float32)
    target = sr * seconds
    if y.size < target:
        y = np.pad(y, (0, target - y.size))
    elif y.size > target:
        y = y[:target]
    return y


# ---------------------------------------------------------------------------
# metadata
# ---------------------------------------------------------------------------
def _first(value) -> str | None:
    if not value:
        return None
    return str(value[0]).strip() or None


def _clean(value: str) -> str:
    return re.sub(r"^\s*\d+\s*[.\-)]\s*", "", value).strip()


def read_track(path: Path, root: Path) -> Track:
    title: str | None = None
    artist: str | None = None
    try:
        handle = mutagen.File(path, easy=True)
        if handle is not None:
            artist = _first(handle.get("artist"))
            title = _first(handle.get("title"))
    except Exception:
        pass

    if not title or not artist:
        stem = path.stem
        if " - " in stem:
            head, tail = stem.split(" - ", 1)
            artist = artist or _clean(head)
            title = title or tail.strip()
        else:
            title = title or stem

    relative = path.resolve().relative_to(root.resolve()).as_posix()
    track_id = hashlib.sha1(relative.encode("utf-8")).hexdigest()[:8]
    return Track(
        id=track_id,
        title=(title or path.stem).strip(),
        artist=(artist or "Unknown").strip(),
        duration=round(duration_seconds(path), 1),
        path=str(path),
        audio_url=f"/audio/{track_id}",
    )


# ---------------------------------------------------------------------------
# features
# ---------------------------------------------------------------------------
def _detect_key(chroma: np.ndarray) -> tuple[int, int]:
    """Krumhansl-Schmuckler (Pearson correlation): (key 0-11, mode 1=major 0=minor)."""
    c = np.asarray(chroma, dtype=np.float64)
    c = c - c.mean()
    norm_c = np.linalg.norm(c) + 1e-12
    best_score, best_key, best_mode = -np.inf, 0, 0
    for tonic in range(12):
        rotated = np.roll(c, -tonic)
        for mode, profile in ((1, _MAJOR_PROFILE), (0, _MINOR_PROFILE)):
            p = profile - profile.mean()
            score = float(np.dot(rotated, p) / (norm_c * np.linalg.norm(p)))
            if score > best_score:
                best_score, best_key, best_mode = score, tonic, mode
    return best_key, best_mode


def _segment_scalars(y: np.ndarray, sr: int) -> tuple[list[float], np.ndarray]:
    tempo = float(librosa.feature.tempo(y=y, sr=sr, aggregate=np.median)[0])
    rms = float(librosa.feature.rms(y=y).mean())
    centroid = float(librosa.feature.spectral_centroid(y=y, sr=sr).mean())
    rolloff = float(librosa.feature.spectral_rolloff(y=y, sr=sr).mean())
    zcr = float(librosa.feature.zero_crossing_rate(y).mean())
    bandwidth = float(librosa.feature.spectral_bandwidth(y=y, sr=sr).mean())
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr).mean(axis=1)
    return [tempo, rms, centroid, rolloff, zcr, bandwidth], chroma


def extract_features(path: Path, duration: float | None = None) -> np.ndarray:
    """Raw 9-dim feature vector; deterministic for a given file."""
    duration = duration if duration is not None else duration_seconds(path)
    scalars: list[list[float]] = []
    chromas: list[np.ndarray] = []
    for offset in segment_offsets(duration):
        values, chroma = _segment_scalars(load_segment(path, offset), SAMPLE_RATE)
        scalars.append(values)
        chromas.append(chroma)

    block = np.asarray(scalars, dtype=np.float32)  # (segments, 6)
    key, mode = _detect_key(np.mean(chromas, axis=0))

    features = np.empty(len(FEATURE_NAMES), dtype=np.float32)
    features[:6] = block.mean(axis=0)
    features[0] = np.median(block[:, 0])  # tempo: median is octave-error resistant
    features[6] = np.sin(2.0 * np.pi * key / 12.0)
    features[7] = np.cos(2.0 * np.pi * key / 12.0)
    features[8] = float(mode)
    return features


def key_label(features: np.ndarray) -> str:
    angle = np.arctan2(features[6], features[7])
    key = int(round(angle / (2.0 * np.pi) * 12.0)) % 12
    return _KEY_NAMES[key] + ("maj" if features[8] >= 0.5 else "min")


def scan_library(
    root: Path,
    playlists: list[Path] | None = None,
    limit: int | None = None,
    on_progress=None,
) -> list[ScannedTrack]:
    """Resolve, read metadata and extract features. Unreadable files are skipped."""
    paths, labels = collect_paths(root, playlists)
    if limit:
        paths = paths[:limit]

    scanned: list[ScannedTrack] = []
    for index, path in enumerate(paths, 1):
        try:
            track = read_track(path, root)
            features = extract_features(path, track.duration)
        except Exception as exc:
            print(f"skip {path.name}: {exc}", file=sys.stderr)
        else:
            scanned.append(ScannedTrack(track, features, labels.get(path, ())))
        if on_progress is not None:
            on_progress(index, len(paths), path)
    return scanned
