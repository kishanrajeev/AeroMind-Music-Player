#!/usr/bin/env python
"""CLAP mood-retrieval probe — G1 pre-check (spec §10 gate G1).

Embeds a library sample with the exact 3-segment recipe index.py will use, then
ranks tracks for mood queries under several prompt phrasings. No server, no
brain — it answers one question: does CLAP retrieve by mood on this library?

Segment recipe (spec §6): 3 windows of 10 s starting at 25% / 50% / 75% of the
track (clamped so the window fits), encoded independently, then mean-pooled and
L2-normalized. Embeddings are cached in data/mood_probe.npz keyed by path set.

Usage:
    python scripts/mood_probe.py \
        --music-root /mnt/Data/Projects/HackNC/music \
        --playlist Crockpot.m3u Hersheys.m3u \
        --queries sad energetic slow chill hype happy dark romantic
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import unquote

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import numpy as np  # noqa: E402
import torch  # noqa: E402
from transformers import ClapModel, ClapProcessor  # noqa: E402

from core.library import (  # noqa: E402
    SAMPLE_RATE,
    duration_seconds,
    load_segment,
    parse_playlists,
    segment_offsets,
)

MODEL_ID = "laion/clap-htsat-unfused"
CACHE_FILE = REPO / "data" / "mood_probe.npz"

#: Prompt phrasings; the ensemble averages their (normalized) text embeddings.
TEMPLATES = ("{}", "a {} song", "{} music", "a song that sounds {}")


def embed_track(path: Path, proc: ClapProcessor, model: ClapModel) -> torch.Tensor:
    """3-segment mean-pooled, L2-normalized CLAP embedding (512,)."""
    embs = []
    for offset in segment_offsets(duration_seconds(path)):
        y = load_segment(path, offset)
        inputs = proc(audio=[y], sampling_rate=SAMPLE_RATE, return_tensors="pt")
        with torch.no_grad():
            embs.append(model.get_audio_features(**inputs).pooler_output[0])
    pooled = torch.stack(embs).mean(dim=0)
    return torch.nn.functional.normalize(pooled, dim=-1)


def build_embeddings(
    tracks: list[Path], proc: ClapProcessor, model: ClapModel
) -> tuple[list[Path], torch.Tensor]:
    """Encode tracks, reusing data/mood_probe.npz when the path set matches."""
    ids = [str(p.relative_to(p.anchor)) for p in tracks]
    if CACHE_FILE.exists():
        cache = np.load(CACHE_FILE, allow_pickle=False)
        cached_ids = set(cache["ids"].tolist())
        if cached_ids == set(ids):
            order = {tid: i for i, tid in enumerate(cache["ids"].tolist())}
            emb = torch.from_numpy(cache["emb"][[order[t] for t in ids]])
            print(f"loaded {len(ids)} cached embeddings from {CACHE_FILE}")
            return tracks, emb

    rows, kept = [], []
    for i, path in enumerate(tracks, 1):
        try:
            rows.append(embed_track(path, proc, model))
            kept.append(path)
        except Exception as exc:
            print(f"  skip {path.name}: {exc}")
        if i % 20 == 0 or i == len(tracks):
            print(f"  embedded {i}/{len(tracks)}")

    emb = torch.stack(rows)
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    np.savez(
        CACHE_FILE,
        ids=np.array([str(p.relative_to(p.anchor)) for p in kept]),
        emb=emb.numpy(),
    )
    print(f"cached {len(kept)} embeddings -> {CACHE_FILE.relative_to(REPO)}")
    return kept, emb


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--music-root", required=True, type=Path)
    parser.add_argument("--playlist", required=True, nargs="+", type=Path)
    parser.add_argument("--queries", nargs="+", default=["sad", "energetic", "slow", "chill"])
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--summary", action="store_true", help="one line per query: top-N titles")
    parser.add_argument("--json", type=Path, default=None, help="dump full scores here")
    args = parser.parse_args()

    root = args.music_root.resolve()
    print(f"library root: {root}")
    tracks, labels = parse_playlists(args.playlist, root)
    print(f"tracks: {len(tracks)} unique")

    proc = ClapProcessor.from_pretrained(MODEL_ID)
    model = ClapModel.from_pretrained(MODEL_ID).eval()

    tracks, emb = build_embeddings(tracks, proc, model)

    dump: dict[str, dict] = {}
    for query in args.queries:
        prompts = [t.format(query) for t in TEMPLATES]
        with torch.no_grad():
            text = model.get_text_features(
                **proc(text=prompts, return_tensors="pt", padding=True, truncation=True)
            ).pooler_output
        text = torch.nn.functional.normalize(text, dim=-1)
        ensemble = torch.nn.functional.normalize(text.mean(dim=0), dim=-1)

        scores = (emb @ ensemble).tolist()
        order = sorted(range(len(tracks)), key=lambda i: -scores[i])

        if args.summary:
            names = [tracks[i].stem for i in order[: args.top]]
            print(f"{query:>14}: " + " | ".join(names))
            dump[query] = {
                "prompts": prompts,
                "results": [
                    {"path": str(tracks[i]), "score": scores[i], "labels": labels.get(tracks[i], [])}
                    for i in order
                ],
            }
            continue

        print(f"\n=== {query!r} ===")
        for j, prompt in enumerate(prompts):
            per = (emb @ text[j]).argmax().item()
            print(f"  top1 [{prompt}]: {tracks[per].stem}")

        for rank, i in enumerate(order[: args.top], 1):
            label = ", ".join(sorted(set(labels.get(tracks[i], [])))) or "?"
            print(f"  {rank:2}. {scores[i]:+.4f}  {tracks[i].stem}  [{label}]")

        dump[query] = {
            "prompts": prompts,
            "results": [
                {"path": str(tracks[i]), "score": scores[i], "labels": labels.get(tracks[i], [])}
                for i in order
            ],
        }

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(dump, indent=2))
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
