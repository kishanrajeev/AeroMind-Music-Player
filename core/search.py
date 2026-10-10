"""Semantic retrieval: text query -> CLAP candidate pool (spec §6).

Search is retrieval only; personalization lives in brain.py. The query
embedding is an ensemble over prompt phrasings (bare mood words can land in odd
places; averaging templates is steadier) and is cached per query string, so
alpha-slider moves never re-encode text (spec §6).

Empty query -> every track is a candidate with clap_score = 0.5, leaving the
ranking entirely to the brain (spec §7-8).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import torch
import torch.nn.functional as F

from core.index import IndexData
from core.scoring import minmax_normalize
from core.types import NO_QUERY_CLAP_SCORE, RETRIEVE_POOL_SIZE, Track

#: Prompt phrasings; the ensemble averages their (normalized) text embeddings.
TEMPLATES = ("{}", "a {} song", "{} music", "a song that sounds {}")


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

    def embed(self, query: str) -> np.ndarray:
        key = query.strip().lower()
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        prompts = [template.format(query.strip()) for template in self.templates]
        inputs = self.processor(
            text=prompts, return_tensors="pt", padding=True, truncation=True
        ).to(self.device)
        with torch.no_grad():
            embeddings = self.model.get_text_features(**inputs).pooler_output
        embeddings = F.normalize(embeddings, dim=-1)
        vector = F.normalize(embeddings.mean(dim=0), dim=-1).float().cpu().numpy()

        if len(self._cache) >= self.cache_size:
            self._cache.pop(next(iter(self._cache)))
        self._cache[key] = vector
        return vector


def retrieve(
    index: IndexData,
    encoder: QueryEncoder | None,
    query: str | None,
    pool_size: int = RETRIEVE_POOL_SIZE,
) -> list[Candidate]:
    """Top ``pool_size`` candidates by CLAP similarity, scores normalized in-pool."""
    query = (query or "").strip()
    if not query:
        return [Candidate(track, 0.0, NO_QUERY_CLAP_SCORE) for track in index.tracks]
    if encoder is None:
        raise ValueError("retrieve() needs an encoder for a non-empty query")

    query_vector = encoder.embed(query)
    similarities = index.embeddings @ query_vector  # both L2-normalized
    count = min(pool_size, len(index.tracks))
    top = np.argsort(-similarities, kind="stable")[:count]
    raw = similarities[top]
    scores = minmax_normalize(raw)
    return [
        Candidate(index.tracks[int(track_index)], float(raw[row]), float(scores[row]))
        for row, track_index in enumerate(top)
    ]
