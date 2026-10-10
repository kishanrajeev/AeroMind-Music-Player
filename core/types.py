"""
Source of truth for the HTTP API (spec §4) and the internal Engine
interface (spec §3).
"""

from __future__ import annotations

from dataclasses import dataclass

API_VERSION = "1.0"

# Contract constants (spec §8)
RETRIEVE_POOL_SIZE = 30  # CLAP candidates considered before blending
DEFAULT_N = 10  # tracks returned for display
MIN_N = 1
#: Upper clamp only. Clients ask for "the whole library" by sending a large n;
#: the engine still returns at most the candidate pool (30 with a query).
MAX_N = 1000
DEFAULT_ALPHA = 0.5  # 1.0 = pure phrase match, 0.0 = pure brain
KC_DIM = 2000  # Kenyon cells (spec §7)
PN_DIM = 50  # projection neurons

#: Value used when a min-max normalization is degenerate (every score equal).
#: 0.5 keeps pre-feedback brain scores at the neutral midpoint.
DEGENERATE_NORM = 0.5

#: clap_score for every track when there is no query.
NO_QUERY_CLAP_SCORE = 0.5

#: Legal reward values for POST /feedback: skip / neutral / listen-through.
VALID_REWARDS = (-1, 0, 1)


@dataclass(frozen=True)
class Track:
    id: str
    title: str
    artist: str
    duration: float
    path: str  # server-side debug info only; clients use audio_url
    audio_url: str  # relative, e.g. /audio/a3f9c1


@dataclass(frozen=True)
class ScoredTrack:
    id: str
    title: str
    artist: str
    duration: float
    path: str
    audio_url: str
    clap_score: float  # normalized 0..1 within the candidate pool
    brain_score: float  # normalized 0..1 within the candidate pool
    final_score: float  # alpha * clap_score + (1 - alpha) * brain_score


@dataclass(frozen=True)
class HealthResponse:
    version: str
    ok: bool
    library_size: int
    index_loaded: bool
    fixture_mode: bool


@dataclass(frozen=True)
class LibraryResponse:
    version: str
    count: int
    tracks: tuple[Track, ...]


@dataclass(frozen=True)
class PlaylistResponse:
    version: str
    query: str | None
    alpha: float
    tracks: tuple[ScoredTrack, ...]


@dataclass(frozen=True)
class FeedbackRequest:
    track_id: str
    reward: int  # one of VALID_REWARDS


@dataclass(frozen=True)
class BrainState:
    track_id: str
    mbon_output: float
    kc_activity: tuple[float, ...]  # exactly KC_DIM
    weights: tuple[float, ...]  # exactly KC_DIM
    feedback_count: int


@dataclass(frozen=True)
class FeedbackResponse:
    version: str
    ok: bool
    brain_state: BrainState


@dataclass(frozen=True)
class BrainStateResponse:
    version: str
    track_id: str
    mbon_output: float
    kc_activity: tuple[float, ...]  # exactly KC_DIM
    weights: tuple[float, ...]  # exactly KC_DIM
    feedback_count: int


@dataclass(frozen=True)
class ErrorResponse:
    version: str
    ok: bool
    error: str
