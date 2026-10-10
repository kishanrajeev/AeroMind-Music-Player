# HackNC 2026 — core (headless)

A music player whose core is a headless HTTP service (spec §3): **CLAP** audio–text
search retrieves songs by how they *sound*, then a simulated **Drosophila mushroom
body** re-ranks them using taste learned from skips and listens. The UI is one
client among many — it owns playback and all visuals; this service never touches
an audio device.

> Specs live one level up, outside this repo: `../hacknc-spec.md`, `../hacknc-ui-spec.md`.

## Status

Build order steps 1–2 (spec §10) are done:

- `core/types.py` — frozen contract types, single source of truth
- `api/server.py --fixture` — full HTTP surface over canned JSON
- `api/fixtures/*.json` + `cli.py export-fixture --placeholder`
- `scripts/smoke.py` — endpoint contract smoke test

Not built yet: `library.py`, `index.py`, `search.py`, `brain.py`, `engine.py`
(real mode is step 7).

## Quickstart (fixture mode — no ML deps needed)

Python version is pinned in `.python-version` (3.14, spec §9).

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt       # fast: FastAPI + uvicorn only
python -m api.server --fixture        # http://127.0.0.1:8000
```

Open **http://127.0.0.1:8000/docs** — the authoritative, always-current contract.
Then, in another terminal:

```bash
python cli.py playlist "rainy afternoon" --alpha 0.5
python scripts/smoke.py               # contract checks against a running server
```

Regenerate fixtures (deterministic; safe to re-run):

```bash
python cli.py export-fixture --placeholder
```

The ML stack (torch, transformers, librosa) is **not needed** for fixture mode;
it lives in `requirements-core.txt` and gets pinned at gate G0 (spec §9).

## Layout

```
core/types.py       shared contract types (stdlib only, never imports FastAPI)
api/server.py       FastAPI app — the ONLY file allowed to import core.engine
api/fixtures/       canned responses for --fixture mode (regenerate, don't hand-edit)
cli.py              headless harness (export-fixture now; search/calibrate later)
scripts/smoke.py    endpoint contract smoke test
data/               index.npz / brain.npz land here (gitignored)
```

## Contract rules

- Every JSON response carries `"version": "1.0"` (`core.types.API_VERSION`).
- Field names are snake_case, exactly as in `core/types.py`. Renames bump the version.
- Errors: every non-2xx response is `{"version": "1.0", "ok": false, "error": "..."}`.
- `kc_activity` and `weights` are always exactly 2000 floats.
- `alpha` is clamped to 0–1 and `n` to 1–50 server-side.
- No query → `"query": null`, every `clap_score` is 0.5, ordering comes from the brain.
- Unknown `track_id` on `/feedback` or `/brain_state` → 404 error JSON.
- Playback state is client-owned: no `/now_playing`, no `/control`.
- Fixture mode has no audio files — `/audio/<id>` returns a 404 error JSON.

## Decisions made while scaffolding (say something now if you disagree)

- **Retrieve pool = 30** (spec said 25–30); `KC_DIM = 2000`.
- **Degenerate min-max normalization = 0.5** for both terms (spec left the constant open).
- **Empty query → `clap_score = 0.5`** for every track, so the slider still works.
- **Unknown track feedback = 404**, not a silent no-op.
- Fixture `/playlist` recomputes `final_score` with the real blend formula and
  re-sorts, so the alpha slider is fully testable before the engine exists.

## Workflow

Branches `core` (backend) and `ui` (frontend), merged to `main` at integration points.
`api/server.py` and `core/types.py` are the contract — change them in a commit both
sides see, never silently.
