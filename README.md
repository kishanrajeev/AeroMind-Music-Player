# AeroMind Music Player

> A music player that learns your taste with a simulated fruit-fly mushroom body.

Type a mood — *"aggressive"*, *"hype, slow, night drive"* — and AeroMind finds songs by how they, not how they're tagged. It then re-ranks the results through a simulated Drosophila mushroom body that learns from every skip and listen, with a live visualization of the 2000-neuron circuit thinking in real time.

---

## Inspiration
Trying to find the perfect song to fit the mood while trying to work out at the gym, or while getting ready to go on a drive usually ends in choosing the same song you always do. Playlists don't fix this problem; having to update each playlist manually and deciding between random shuffle, algorithmic shuffle(always the same songs), and just picking a song from the playlist manually also aren't the best way to solve this problem. We faced this problem everyday and decided to brainstorm ways to have a better system: one that learns from your preferences.

## What it does
AeroMind Music Player uses CLAP(Contrastive Language-Audio Pretraining) to find music by sound instead of tags. By simply typing a genre or mood like "aggressive" or "heavy", you can filter a list of songs that closely match those terms. Those candidates are then re-ranked by a simulated fruit-fly mushroom body which learns based on single user preferences. Each song lights up a sparse pattern of 2000 Kenyon cells, and every skip (−1) or listen-through (+1) rewires their learned weights. It learns your preferences to actual songs, not just for that particular genre, so all of your future searches are ranked based on past data. 

## How it works

- **Retrieval** — every track is indexed once with CLAP (`laion/clap-htsat-unfused`): 5 audio segments, tested with 850+ songs.
- **Kenyon cells** — 9 audio features (tempo, RMS, spectral centroid/rolloff, ZCR, bandwidth, key sin/cos, mode) are z-scored and whitened, then projected into 2000 Kenyon cells. Each song activates a sparse 5–10% pattern.
- **MBON weights** — one shared learnable weight per Kenyon cell. Learning is the three-factor rule `Δw = drive · reward · kc_activity / active_cells`, with `reward ∈ {−1, 0, +1}`.
- **Persistence** — `brain.npz` stores the projection, z-score statistics, feature-order hash, seed and model revision, so learned weights always apply to the same KC basis across restarts. 

## How we built it

We decoupled a Python/FastAPI backend and a Next.js/React frontend. The backend handles deterministic 5-segment CLAP audio embeddings and a custom-built numpy mushroom body. The frontend uses Tailwind CSS to recreate retro glassmorphism to fit the Aero theme, renders the live circuit on a Canvas 2D "neural core", and ships as an Electron desktop app.

```
hacknc-ui/     Next.js 16 · React 19 · Tailwind 4 · Electron - player, canvas visualizer, brain store
HackNC2026/    Python · FastAPI · CLAP · librosa · numpy - index, search, mushroom body
```

## Running it

**Prerequisites:** Python 3.14, Node 20+, and `ffmpeg` on `PATH` (audio decode fallback).

### Backend (`HackNC2026/`)

```bash
cd HackNC2026
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-core.txt # FastAPI + torch/transformers/librosa

export HACKNC_MUSIC_ROOT=/path/to/music # directory of audio files
export HACKNC_PLAYLISTS=English.m3u # optional: .m3u playlist(s), comma separated
python -m api.server # http://127.0.0.1:8000
```

The first run indexes the library (CLAP embeddings) and creates `data/brain.npz`. Interactive API docs: http://127.0.0.1:8000/docs.

```bash
pip install -r requirements.txt
python -m api.server --fixture
```

### Frontend (`hacknc-ui/`)

```bash
cd hacknc-ui
npm install
npm run dev # browser at http://localhost:3000
```

### Desktop app (Electron)

```bash
npm run desktop:build # static export into .next-desktop/
npm run desktop # launch the app window
npm run desktop:glass # transparent window (compositor blurs the real desktop behind it)
npm run desktop:dev # use the running dev server instead of the export
```

## Headless CLI

```bash
python cli.py library # scan the music root, print the feature table
python cli.py index # build/load data/index.npz
python cli.py search "energetic" # CLAP candidates without the brain
python cli.py playlist "aggressive" # full blend from a running server
python cli.py brain # status + valence range
python cli.py brain --state "Goat" # one track's state
python cli.py brain --reset # discard learned weights and rebuild
python scripts/smoke.py # endpoint contract checks against a running server
```
---

*Built at HackNC 2026.*

**Built with the use of deepseek-v4.1-flash and v0**
