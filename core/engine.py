"""Engine: index + search + brain behind one object (spec §3).

This is what api/server.py wraps. The HTTP surface is the contract; the Engine
is internal. It owns:

- the loaded index (library metadata, embeddings, features)
- the mushroom body and its persisted state
- the CLAP text encoder, loaded once and kept warm

A single lock guards brain reads/writes so a POST /feedback cannot race a
GET /playlist (uvicorn runs sync handlers in a threadpool).
"""

from __future__ import annotations

import logging
import os
import threading
from functools import lru_cache
from pathlib import Path

import numpy as np

from core.brain import (
    BRAIN_PATH,
    DEFAULT_ETA,
    DEFAULT_SEED,
    Brain,
    ensure_brain,
)
from core.index import INDEX_PATH, IndexData, ensure_index, load_clap
from core.library import cover_bytes
from core.scoring import blend, minmax_normalize
from core.search import QueryEncoder, retrieve
from core.types import (
    MAX_N,
    MIN_N,
    RETRIEVE_POOL_SIZE,
    VALID_REWARDS,
    BrainState,
    ScoredTrack,
    Track,
)

log = logging.getLogger("hacknc.engine")


@lru_cache(maxsize=512)
def _cover_thumbnail(path: str, mtime_ns: int) -> tuple[bytes, str] | None:
    """Cached by (path, mtime) so editing a file's art invalidates it."""
    return cover_bytes(Path(path))


def _scan_log(done: int, total: int, _path) -> None:
    if done % 25 == 0 or done == total:
        log.info("scan %d/%d", done, total)


def _embed_log(done: int, total: int) -> None:
    if done % 25 == 0 or done == total:
        log.info("embed %d/%d", done, total)


class Engine:
    def __init__(
        self,
        music_root: Path | None = None,
        playlists: list[Path] | None = None,
        index_path: Path = INDEX_PATH,
        brain_path: Path = BRAIN_PATH,
        device: str | None = None,
        eta: float = DEFAULT_ETA,
        seed: int = DEFAULT_SEED,
        warm: bool = True,
    ):
        if music_root is None:
            env_root = os.environ.get("HACKNC_MUSIC_ROOT")
            music_root = Path(env_root) if env_root else None
        if playlists is None:
            raw = os.environ.get("HACKNC_PLAYLISTS", "")
            playlists = [Path(part.strip()) for part in raw.split(",") if part.strip()]

        self.index: IndexData = ensure_index(
            music_root,
            playlists or None,
            path=Path(index_path),
            on_scan=_scan_log,
            on_embed=_embed_log,
            device=device,
        )
        log.info("index ready: %d tracks", len(self.index.tracks))

        self._brain_path = Path(brain_path)
        self.brain: Brain = ensure_brain(
            self.index, path=self._brain_path, eta=eta, seed=seed
        )
        self._brain_stamp = self._brain_mtime()
        log.info("brain ready: %d feedback signals", self.brain.feedback_count)

        self.processor, self.model, self.device = load_clap(device)
        self.encoder = QueryEncoder(self.processor, self.model, self.device)
        if warm:
            self.encoder.embed("warmup")  # first encode may be slow; do it now
        self.index_loaded = True

        self._row_by_id = {track.id: i for i, track in enumerate(self.index.tracks)}
        self._brain_lock = threading.RLock()
        log.info("engine ready on %s", self.device)

    # -- reads --------------------------------------------------------------
    def _brain_mtime(self) -> int | None:
        try:
            return self._brain_path.stat().st_mtime_ns
        except FileNotFoundError:
            return None

    def _sync_brain(self) -> None:
        """Pick up brain.npz edits made by the CLI (reset / calibration) live.

        Called under the brain lock. The file is written atomically, so a stat
        plus reload is safe even if another process is writing it.
        """
        stamp = self._brain_mtime()
        if stamp is not None and stamp != self._brain_stamp:
            self.brain = ensure_brain(self.index, path=self._brain_path)
            self._brain_stamp = self._brain_mtime()
            log.info("brain reloaded from disk: %d feedback signals", self.brain.feedback_count)

    def library(self) -> list[Track]:
        return list(self.index.tracks)

    def audio_path(self, track_id: str) -> str:
        return self.index.tracks[self._row_by_id[track_id]].path

    def cover(self, track_id: str) -> tuple[bytes, str] | None:
        """Thumbnail bytes + mime for a track's embedded art, or None."""
        path = Path(self.index.tracks[self._row_by_id[track_id]].path)
        try:
            mtime_ns = path.stat().st_mtime_ns
        except OSError:
            return None
        return _cover_thumbnail(str(path), mtime_ns)

    def brain_state(self, track_id: str) -> BrainState:
        row = self._row_by_id[track_id]  # KeyError -> caller maps to 404
        with self._brain_lock:
            self._sync_brain()
            return self.brain.state(track_id, self.index.features[row])

    # -- main call ----------------------------------------------------------
    def playlist(self, query: str | None, alpha: float, n: int) -> list[ScoredTrack]:
        query = (query or "").strip() or None
        alpha = max(0.0, min(1.0, float(alpha)))
        n = max(MIN_N, min(MAX_N, int(n)))

        candidates = retrieve(
            self.index,
            self.encoder if query else None,
            query,
            pool_size=RETRIEVE_POOL_SIZE,
        )
        if not candidates:
            return []

        features = np.stack(
            [self.index.features[self._row_by_id[c.track.id]] for c in candidates]
        )
        clap_norm = np.array([c.clap_score for c in candidates], dtype=np.float64)
        with self._brain_lock:
            self._sync_brain()
            brain_norm = minmax_normalize(self.brain.valences(features))
        final = blend(clap_norm, brain_norm, alpha)

        # tie-break: final desc, then CLAP desc, then stable id (spec §8)
        order = sorted(
            range(len(candidates)),
            key=lambda i: (-float(final[i]), -float(clap_norm[i]), candidates[i].track.id),
        )[:n]

        scored: list[ScoredTrack] = []
        for i in order:
            track = candidates[i].track
            scored.append(
                ScoredTrack(
                    id=track.id,
                    title=track.title,
                    artist=track.artist,
                    duration=track.duration,
                    path=track.path,
                    audio_url=track.audio_url,
                    clap_score=round(float(clap_norm[i]), 4),
                    brain_score=round(float(brain_norm[i]), 4),
                    final_score=round(float(final[i]), 4),
                )
            )
        return scored

    # -- learning -----------------------------------------------------------
    def feedback(self, track_id: str, reward: float) -> BrainState:
        reward = int(reward)
        if reward not in VALID_REWARDS:
            raise ValueError(f"reward must be one of {list(VALID_REWARDS)}")
        row = self._row_by_id[track_id]  # KeyError -> caller maps to 404
        features = self.index.features[row]
        with self._brain_lock:
            self._sync_brain()
            self.brain.feedback(features, reward)
            if reward != 0:
                self.brain.save(self._brain_path)
                self._brain_stamp = self._brain_mtime()
            return self.brain.state(track_id, features)
