import { fetchBrainState, type BrainState } from './api'

/*
 * Live mushroom-body state, shared between the player (which posts feedback) and
 * the BrainView (which visualises it). /brain_state is the single source of truth:
 * this module only caches the latest response, tells subscribers when it changed,
 * and turns each /feedback response into a pulse for the visualizer.
 */

/** One dot per Kenyon cell; mirrors KC_DIM in the backend (core/types.py). */
export const KC_COUNT = 2000

export type BrainPulse = {
  /** Increments once per learning event; lets views ignore pulses that are not new. */
  id: number
  /** Kenyon cells the latest skip or listen-through moved. */
  changed: number[]
}

export type BrainSnapshot = {
  /** Track a state is being loaded for; '' when nothing is queued. */
  trackId: string
  /** Track `state` belongs to, so a view never draws stale activity for a new song. */
  stateTrackId: string
  status: 'idle' | 'loading' | 'ready' | 'error'
  state: BrainState | null
  pulse: BrainPulse | null
  /** Bumps whenever the backend reports new learning, so views can refetch. */
  revision: number
}

let snapshot: BrainSnapshot = {
  trackId: '',
  stateTrackId: '',
  status: 'idle',
  state: null,
  pulse: null,
  revision: 0,
}
const listeners = new Set<() => void>()

function emit(patch: Partial<BrainSnapshot>) {
  snapshot = { ...snapshot, ...patch }
  listeners.forEach((listener) => listener())
}

export function subscribeBrain(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

export function getBrainSnapshot(): BrainSnapshot {
  return snapshot
}

/** Fetch /brain_state for one track. Returns an abort function for effect cleanup. */
export function loadBrainState(trackId: string): () => void {
  if (!trackId) {
    emit({ trackId: '', status: 'idle', state: null, stateTrackId: '' })
    return () => {}
  }
  const controller = new AbortController()
  emit({ trackId, status: 'loading' })
  fetchBrainState(trackId, controller.signal)
    .then((state) => {
      if (getBrainSnapshot().trackId === trackId) emit({ state, stateTrackId: trackId, status: 'ready' })
    })
    .catch(() => {
      if (!controller.signal.aborted && getBrainSnapshot().trackId === trackId) emit({ status: 'error' })
    })
  return () => controller.abort()
}

/**
 * Publish a POST /feedback response. The backend returns the updated state for the
 * track that was just fed back; its kc_activity is exactly the set of cells that moved.
 */
export function reportFeedback(state: BrainState): void {
  const changed: number[] = []
  for (let i = 0; i < state.kc_activity.length; i++) {
    if (state.kc_activity[i] > 0) changed.push(i)
  }
  const revision = snapshot.revision + 1
  emit({ pulse: { id: revision, changed }, revision })
}

/** Largest |weight|, so the UI can scale to the range actually learned (it starts tiny). */
export function maxWeightMagnitude(weights: number[]): number {
  let max = 0
  for (const weight of weights) {
    const magnitude = Math.abs(weight)
    if (magnitude > max) max = magnitude
  }
  return max
}
