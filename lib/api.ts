import type { Song } from './songs'

export const API_BASE = 'http://127.0.0.1:8000'

/**
 * Blend between literal phrase match (1.0) and the brain's learned taste (0.0).
 * There is no alpha slider in the UI yet, so every request uses this fixed value.
 */
export const DEFAULT_ALPHA = 0.5

export type ApiTrack = {
  id: string
  title: string
  artist: string
  duration: number
  path: string
  audio_url: string
  clap_score: number
  brain_score: number
  final_score: number
}

export type PlaylistResponse = {
  version: string
  query: string
  alpha: number
  tracks: ApiTrack[]
}

export type HealthResponse = {
  version: string
  ok: boolean
  library_size: number
  index_loaded: boolean
  fixture_mode: boolean
}

export type BrainState = {
  version: string
  track_id: string
  mbon_output: number
  kc_activity: number[]
  weights: number[]
  feedback_count: number
}

/** A track as the UI renders it: API fields plus local display placeholders. */
export type Track = Song & {
  clap_score: number
  brain_score: number
  final_score: number
}

// Real album art is served by the backend as a thumbnail of the picture embedded
// in the audio file. The bundled aero images are the fallback when a track has
// no embedded art (or the backend runs in fixture mode).
const COVERS = [
  '/images/album-aqua.png',
  '/images/album-meadow.png',
  '/images/album-orbit.png',
  '/images/album-koi.png',
]

export function fallbackCover(id: string) {
  let hash = 0
  for (let i = 0; i < id.length; i++) hash = (hash * 31 + id.charCodeAt(i)) | 0
  return COVERS[Math.abs(hash) % COVERS.length]
}

export function coverUrl(trackId: string) {
  return `${API_BASE}/cover/${encodeURIComponent(trackId)}`
}

export function toTrack(track: ApiTrack): Track {
  return {
    id: track.id,
    title: track.title,
    artist: track.artist,
    album: '', // not part of the API response yet
    cover: coverUrl(track.id),
    duration: track.duration,
    clap_score: track.clap_score,
    brain_score: track.brain_score,
    final_score: track.final_score,
  }
}

export function audioUrl(trackId: string) {
  return `${API_BASE}/audio/${encodeURIComponent(trackId)}`
}

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { signal })
  if (!res.ok) throw new Error(`GET ${path} failed with ${res.status}`)
  return res.json() as Promise<T>
}

export function fetchPlaylist(query: string, alpha: number, n: number, signal?: AbortSignal) {
  const clamped = Math.min(1, Math.max(0, alpha))
  const params = new URLSearchParams({ alpha: String(clamped), n: String(n) })
  const q = query.trim()
  if (q) params.set('q', q)
  return getJson<PlaylistResponse>(`/playlist?${params.toString()}`, signal)
}

export function fetchHealth(signal?: AbortSignal) {
  return getJson<HealthResponse>('/health', signal)
}

export function fetchBrainState(trackId: string, signal?: AbortSignal) {
  return getJson<BrainState>(`/brain_state?track_id=${encodeURIComponent(trackId)}`, signal)
}

/** Fire-and-forget learning signal: -1 skip, +1 listen-through, 0 neutral. */
export type FeedbackResponse = {
  version: string
  ok: boolean
  brain_state: BrainState
}

/** Teach the brain; the response carries the updated state for the fed-back track. */
export function postFeedback(trackId: string, reward: -1 | 0 | 1): Promise<FeedbackResponse> {
  return fetch(`${API_BASE}/feedback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ track_id: trackId, reward }),
  }).then((res) => {
    if (!res.ok) throw new Error(`POST /feedback failed with ${res.status}`)
    return res.json() as Promise<FeedbackResponse>
  })
}
