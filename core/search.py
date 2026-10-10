"""Semantic retrieval: text query -> CLAP candidate pool (spec §6).

Search is retrieval only; personalization lives in brain.py. The query
embedding is cached per query string, so alpha-slider moves never re-encode
text (spec §6).

Measured on the full 884-track library: averaging several prompt templates
drifts the query embedding toward a generic "music" direction where hub tracks
(e.g. "Legends Never Die") rank #1 for almost every phrase. A bare phrase is
far more directional — hub at #1 in 2/20 probe phrases vs 8/20 for the
4-template ensemble — so bare is the default.

A second measured fix: some tracks are "hubs" that match almost every phrase
because they sit near a generic music direction. ``QueryEncoder.hub_prior()``
estimates that per-track affinity from a fixed set of generic prompts, and
retrieval subtracts ``PRIOR_BETA * prior`` before ranking (override with
HACKNC_HUB_BETA=0).

Empty query -> every track is a candidate with clap_score = 0.5, leaving the
ranking entirely to the brain (spec §7-8).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import numpy as np
import torch
import torch.nn.functional as F

from core.index import IndexData
from core.scoring import minmax_normalize
from core.types import NO_QUERY_CLAP_SCORE, RETRIEVE_POOL_SIZE, Track

#: Prompt phrasings. See the module docstring: bare beats template ensembles on
#: the full library by a wide margin (hub avoidance and result diversity).
TEMPLATES = ("{}",)

#: Generic prompts used to estimate how "universally similar" a track is. A
#: track that matches many unrelated prompts sits near a generic music centroid
#: and otherwise hogs the top of every query (a "hub"). Subtracting
#: beta * prior suppresses those: on the 884-track library, hub at #1 went
#: 2/23 -> 0/23 and hub in top-10 12 -> 6, with no diversity loss.
GENERIC_PROMPTS = (
    "music", "a song", "pop", "rap", "rock", "sad", "happy", "slow", "fast",
    "loud", "quiet", "night", "party", "love", "angry", "calm", "dance",
    "guitar", "drums", "melody", "vocals", "beat", "emotional", "energetic",
)

#: Correction strength; HACKNC_HUB_BETA=0 disables it.
PRIOR_BETA = float(os.environ.get("HACKNC_HUB_BETA", "0.3"))


@dataclass(frozen=True)
class Candidate:
    track: Track
    clap_raw: float
    clap_score: float  # normalized 0..1 within the pool


class QueryEncoder:
    """CLAP text encoder with a per-query embedding cache."""

    def __init__(
        self,
        processor,
        model,
        device: str,
        templates=TEMPLATES,
        cache_size: int = 256,
    ):
        self.processor = processor
        self.model = model
        self.device = device
        self.templates = tuple(templates)
        self.cache_size = cache_size
        self._cache: dict[str, np.ndarray] = {}
        self._hub_prior: np.ndarray | None = None
        self._hub_prior_key: int | None = None

    def _encode_prompts(self, prompts: list[str]) -> torch.Tensor:
        inputs = self.processor(
            text=prompts, return_tensors="pt", padding=True, truncation=True
        ).to(self.device)
        with torch.no_grad():
            embeddings = self.model.get_text_features(**inputs).pooler_output
        return F.normalize(embeddings, dim=-1)

    def embed(self, query: str) -> np.ndarray:
        key = query.strip().lower()
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        prompts = [template.format(query.strip()) for template in self.templates]
        embeddings = self._encode_prompts(prompts)
        vector = F.normalize(embeddings.mean(dim=0), dim=-1).float().cpu().numpy()

        if len(self._cache) >= self.cache_size:
            self._cache.pop(next(iter(self._cache)))
        self._cache[key] = vector
        return vector

    def hub_prior(self, index: IndexData) -> np.ndarray:
        """Per-track affinity to a generic music direction, cached per index."""
        if self._hub_prior is None or self._hub_prior_key != id(index):
            embeddings = self._encode_prompts(list(GENERIC_PROMPTS))
            direction = F.normalize(embeddings.mean(dim=0), dim=-1).float().cpu().numpy()
            self._hub_prior = index.embeddings @ direction
            self._hub_prior_key = id(index)
        return self._hub_prior


def retrieve(
    index: IndexData,
    encoder: QueryEncoder | None,
    query: str | None,
    pool_size: int = RETRIEVE_POOL_SIZE,
    beta: float = PRIOR_BETA,
) -> list[Candidate]:
    """Top ``pool_size`` candidates by hub-corrected CLAP similarity.

    Scores are normalized 0..1 within the pool (spec §8).
    """
    query = (query or "").strip()
    if not query:
        return [Candidate(track, 0.0, NO_QUERY_CLAP_SCORE) for track in index.tracks]
    if encoder is None:
        raise ValueError("retrieve() needs an encoder for a non-empty query")

    query_vector = encoder.embed(query)
    similarities = index.embeddings @ query_vector  # both L2-normalized
    if beta:
        similarities = similarities - beta * encoder.hub_prior(index)
    count = min(pool_size, len(index.tracks))
    top = np.argsort(-similarities, kind="stable")[:count]
    raw = similarities[top]
    scores = minmax_normalize(raw)
    return [
        Candidate(index.tracks[int(track_index)], float(raw[row]), float(scores[row]))
        for row, track_index in enumerate(top)
    ]
