# HackNC 2026 — UI Spec

**Your role:** build the client. You own everything the judges see.
**You do not need the core to exist.** Fixture mode gives you the real API with fake data from hour one.

---

## 1. The project in one paragraph

A music player. You type a phrase like "rainy afternoon." It finds songs whose **sound** matches that phrase, then re-orders them using a simulated fly brain that has learned your taste from skips and listens. Two things make it work:

- **Search** matches words to *how music sounds*, not to lyrics. So "rainy afternoon" finds a melancholy instrumental that never says "rain."
- **The brain** is a model of the *Drosophila* mushroom body — a real learning circuit. It watches what you skip and what you play through, and adjusts which songs it thinks you'll like. Render it. It is the centrepiece.

**Theme track is Frutiger Aero** — glass, water, bubbles, translucency, early-2000s optimism.

---

## 2. The boundary — you talk to a server

The core runs as a **headless HTTP server**. You are a client. You can write the UI in **any language**: pygame, a web page, Tauri, Flutter, Rust, whatever you're fastest in. The server does not care.

```
┌──────────────────────────┐
│  SERVER (Python)         │   owns: library, search, brain
│  no audio, no visuals    │
└──────────────────────────┘
            ▲
            │  HTTP + JSON on localhost:8000
            ▼
┌──────────────────────────┐
│  YOU (any language)      │   owns: playback, position, all visuals
└──────────────────────────┘
```

**You own:**

| Thing | Notes |
|---|---|
| All rendering | layout, animation, the retro aesthetic |
| Audio playback | the server never plays sound |
| Playback position | and pause/resume/seek |
| Brain visualizer | poll the server for KC activity |
| Frutiger Aero styling | this is judged |

**You do not own:** search, embeddings, the brain's math, file scanning, the index.

---

## 3. Start here — run the server in fixture mode

```bash
git clone <repo>
cd hacknc
pip install -r requirements.txt
python -m api.server --fixture
```

Open **http://127.0.0.1:8000/docs** — an interactive, clickable API explorer with real example responses. Every endpoint is listed, you can hit "Try it out," and you can see exact JSON. **This is your contract. It is always current.**

Fixture mode returns canned but correctly-shaped data. Your UI will work against it exactly as it works against the real engine. When the core is ready, the only change is dropping `--fixture`.

---

## 4. The API

Base URL `http://127.0.0.1:8000`. Every response has `"version": "1.0"`.

### `GET /health`

Check the server is alive.

```json
{"version": "1.0", "ok": true, "library_size": 100,
 "index_loaded": true, "fixture_mode": true}
```

### `GET /playlist?q=rainy%20afternoon&alpha=0.5&n=10`

The main call. `q` optional (omit for a query-less playlist), `alpha` 0.0–1.0, `n` = how many to display.

```json
{"version": "1.0", "query": "rainy afternoon", "alpha": 0.5,
 "tracks": [
   {"id": "a3f9c1", "title": "Song Name", "artist": "Artist",
    "duration": 214.3, "path": "/music/song.flac",
    "audio_url": "/audio/a3f9c1",
    "clap_score": 0.82, "brain_score": 0.64, "final_score": 0.73}
 ]}
```

**The three scores are your UI's best friend.** All normalized 0.0–1.0:

| Field | Meaning | Suggested display |
|---|---|---|
| `clap_score` | how well it matches the typed phrase | "match" bar |
| `brain_score` | how much the brain thinks you'll like it | "taste" bar |
| `final_score` | the blend, what you sort by | rank order |

Show all three per track. A judge can then *see* the two systems disagreeing — which is the whole point of the project.

### `POST /feedback`

Call this on skip and on listen-through. This is how the brain learns.

```json
{"track_id": "a3f9c1", "reward": -1}
```

| Event | reward |
|---|---|
| User skips | `-1` |
| User listens through | `+1` |
| Neutral / unknown | `0` |

Returns the updated brain state. **Fire it and ignore the response if you like** — but you must call it, or the brain never learns.

### `GET /brain_state?track_id=a3f9c1`

For the visualizer. `track_id` is **required** — you tell the server which track is on screen.

```json
{"version": "1.0", "track_id": "a3f9c1", "mbon_output": 0.64,
 "kc_activity": [0.0, 0.12, ...],
 "weights": [0.0, -0.03, ...],
 "feedback_count": 7}
```

`kc_activity` and `weights` are **both exactly 2000 numbers**. Don't assume a different length.

### `GET /audio/<track_id>`

Streams the audio. **Supports `Range` requests**, so seeking works. In a web client, just set `<audio src="http://127.0.0.1:8000/audio/a3f9c1">` — the browser handles seeking for you.

### Client-owned

Position, playing/paused, seeking. **There is no `/now_playing` and no `/control`.** The server has no idea what's playing — that's yours.

---

## 5. The brain visualizer — build this first

This is the single most important thing you will make. It is the difference between "we made a music player" and "we simulated a neural circuit."

**You can build it entirely against fixture data before the core exists.**

### What to render

| Data | Visual idea |
|---|---|
| `kc_activity` (2000 floats) | a grid of ~2000 cells, brightness = activity. Only ~5–10% should be lit |
| `weights` (2000 floats) | same grid, colour-coded — positive/negative (e.g. cyan/amber) |
| `mbon_output` (0–1) | a single bar or gauge — "predicted enjoyment" |
| `feedback_count` | small readout — "7 signals learned" |

### Why it matters

A judge will ask: *"is the brain real or is it decoration?"* A live visual showing the actual KC activity for the current song is the answer. It's not an illustration — it's the model's internal state, rendered.

### Motion

Poll `/brain_state` on a timer (250–500 ms) or after each `feedback()`. When the user skips a track, the weights should **visibly shift**. That flicker of change is your money shot.

### Aesthetic

Glossy cells, soft bloom, translucent panel — Frutiger Aero. It should look like a living thing inside glass.

---

## 6. The alpha slider

One control. Label it something like **"literal match ← → my taste."**

- Left (`alpha = 1.0`) → pure phrase matching
- Right (`alpha = 0.0`) → pure brain preference
- Default `0.5`

On drag: re-call `/playlist` with the new alpha and re-render. **Do not expect the server to be slow** — it caches the query embedding, so this should feel instant.

**Why this matters:** it makes a two-system architecture legible in one gesture. Judges understand the whole project by watching the list reorder.

---

## 7. Suggested UI stack

Pick what you're fastest in. All are fine.

| Option | Aesthetic fit | Notes |
|---|---|---|
| **Web (HTML/CSS/JS)** | **Best** | CSS `backdrop-filter` gives real glass/blur in ~6 lines. `<audio>` handles playback and seeking for free |
| **pygame** | Retro, not glossy | Most control, but no native blur. Lean "retro terminal" instead of "glass" |
| **Tauri / Electron** | Good | Web styling + a real window. Extra build complexity |
| **Terminal (Textual)** | Retro | Fast to build, genuinely unusual, but weak for a brain visualizer |

**If you're undecided: go web.** Frutiger Aero is a glass aesthetic and CSS does glass natively. pygame does not, and you'd be fighting it.

---

## 8. Build order

| Order | Task | Blocked by |
|---|---|---|
| 1 | Run fixture server, read `/docs` | nothing |
| 2 | Agree the contract with your teammate (30 min) | nothing |
| 3 | UI shell — layout, retro frame, playback controls | nothing |
| 4 | `/playlist` wired up, list renders with the three score bars | nothing |
| 5 | **Brain visualizer against fixture `brain_state`** | nothing |
| 6 | Alpha slider wired | nothing |
| 7 | Feedback calls on skip / listen-through | nothing |
| 8 | Polish — Frutiger Aero styling, animation | nothing |
| 9 | Swap fixture → real server, fix what breaks | core ready |

**Items 1–8 are all unblocked right now.** You can complete the entire UI before the core works. That is the point of fixture mode.

---

## 9. Integration checklist

Run through this the first time you point at the real server.

- [ ] `curl http://127.0.0.1:8000/health` returns `ok: true`
- [ ] Field names match exactly — `clap_score`, not `clapScore`
- [ ] `kc_activity.length === 2000`
- [ ] Empty query works — call `/playlist` with no `q`
- [ ] Zero results doesn't crash the UI
- [ ] `feedback()` on an unknown `track_id` doesn't error
- [ ] `alpha` clamped to 0.0–1.0 before sending
- [ ] Audio plays and **seeking works**
- [ ] Server down → UI shows a message, doesn't hang

---

## 10. Working with your teammate

**Branches:** `core` (theirs) and `ui` (yours). Merge to `main` at integration points.

**The contract file is `core/types.py` and `api/server.py`.** Read them, don't edit them. If you need a change — a new field, a different name — **ask, don't commit.** A silent rename breaks the other side.

**Forced integration at the halfway point.** Even if the core is half-built, point the UI at the real server and run it. You will find mismatches while there's still time to fix them. Do not leave integration to the end.

**Report early, report loudly.** If `/docs` and the actual response disagree, that's a bug in the server — say so immediately.

---

## 11. What good looks like

By the end you should be able to:

1. Type "rainy afternoon," get a playlist, and see the three score bars per track
2. Skip two songs and play one through, and **watch the KC grid shift**
3. Re-run the same query and see the **order change**
4. Drag the alpha slider and see the list **re-sort**
5. Show a brain visualizer that is clearly live data, not an animation loop

Points 2 and 3 are the demo. Everything else supports them.

---

## 12. Demo-day notes

- **Use your own laptop.** The demo runs on one machine.
- **Have a Creative Commons playlist ready** for the video recording — the published video can't contain copyrighted audio. Live at the table you can use anything.
- **Sleep.** The demo fair is where you're scored, and it's Sunday afternoon.
- The demo fair is **3 judges, 4 minutes each: 2 minutes demo, 2 minutes questions.** Rehearse the 2 minutes.
