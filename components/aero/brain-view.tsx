'use client'

import { memo, useEffect, useMemo, useState, useSyncExternalStore, type ReactNode } from 'react'
import { Activity, ArrowLeft, Brain, Sparkles, Waves } from 'lucide-react'
import { fallbackCover, type Track } from '@/lib/api'
import {
  KC_COUNT,
  getBrainSnapshot,
  loadBrainState,
  maxWeightMagnitude,
  subscribeBrain,
} from '@/lib/brain'
import { BrainCore } from './brain-core'
import { CoverImage } from './cover-image'

/** Stable all-zero state so the canvas has something to render while /brain_state loads. */
const NO_ACTIVITY: number[] = new Array<number>(KC_COUNT).fill(0)
const NO_WEIGHTS: number[] = new Array<number>(KC_COUNT).fill(0)

function pct(value: number, total: number) {
  return total > 0 ? Math.round((value / total) * 100) : 0
}

function StatCard({ label, icon, children }: { label: string; icon: ReactNode; children: ReactNode }) {
  return (
    <div className="aero-glass rounded-2xl p-4">
      <p className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.2em] text-[var(--aero-cyan-deep)]">
        <span aria-hidden="true">{icon}</span>
        {label}
      </p>
      {children}
    </div>
  )
}

/**
 * The Mushroom Body view: the live Kenyon-cell sphere, predicted enjoyment and
 * the learned-signals stats, all read from the backend's /brain_state
 * (`lib/brain.ts`). The player posts /feedback; each response bumps the store's
 * revision, which refetches the visible song's state and fires the pulse.
 */
export const BrainView = memo(function BrainView({ song, onBack }: { song: Track; onBack: () => void }) {
  const brain = useSyncExternalStore(subscribeBrain, getBrainSnapshot, getBrainSnapshot)
  // Learning events that happened before this view opened are not replayed as pulses.
  const [pulseSeenOnOpen] = useState(() => brain.pulse?.id ?? 0)
  const pulse = brain.pulse && brain.pulse.id > pulseSeenOnOpen ? brain.pulse : null

  // Fetch the state for the visible song, and refetch whenever the backend learns.
  useEffect(() => loadBrainState(song.id), [song.id, brain.revision])

  // Never draw activity from another track: stateTrackId is the song it belongs to.
  const state = brain.stateTrackId === song.id ? brain.state : null
  const activity = state?.kc_activity ?? NO_ACTIVITY
  const weights = state?.weights ?? NO_WEIGHTS

  const litCount = useMemo(
    () => activity.reduce((count, firing) => count + (firing > 0 ? 1 : 0), 0),
    [activity],
  )
  // Weights start at zero and grow by eta ≈ 0.005 per signal, so "learned" is
  // relative: any cell within 10% of the strongest weight counts.
  const weightScale = useMemo(() => maxWeightMagnitude(weights), [weights])
  const memory = useMemo(() => {
    const threshold = weightScale * 0.1
    let liked = 0
    let avoided = 0
    for (const weight of weights) {
      if (weight > threshold) liked++
      else if (weight < -threshold) avoided++
    }
    return { liked, avoided, trained: liked + avoided }
  }, [weights, weightScale])

  const enjoyment = state?.mbon_output ?? 0
  const enjoymentPct = Math.round(enjoyment * 100)
  const feedbackCount = state?.feedback_count ?? 0

  const statusChip =
    brain.status === 'error' ? (
      <span className="rounded-full border border-red-300/70 bg-red-50/70 px-2.5 py-1 text-[10px] font-semibold text-red-700">
        backend offline
      </span>
    ) : brain.status === 'loading' ? (
      <span className="rounded-full border border-white/70 bg-white/45 px-2.5 py-1 text-[10px] font-semibold text-[var(--aero-navy)]/80">
        syncing…
      </span>
    ) : brain.status === 'idle' ? (
      <span className="rounded-full border border-white/70 bg-white/45 px-2.5 py-1 text-[10px] font-semibold text-[var(--aero-navy)]/80">
        nothing queued
      </span>
    ) : null

  return (
    <section aria-label="Mushroom Body" className="aero-brain-view flex min-h-0 flex-1 flex-col gap-3">
      <header className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <button
          type="button"
          onClick={onBack}
          className="aero-pill inline-flex h-8 items-center gap-1.5 px-3 text-xs font-semibold text-[var(--aero-navy)]"
        >
          <ArrowLeft className="size-3.5" aria-hidden="true" />
          Back to player
        </button>
        <div className="ml-auto flex items-center gap-2">
          {pulse ? (
            <span className="aero-pill flex h-7 items-center gap-1.5 px-2.5 text-[10px] font-semibold text-[var(--aero-navy)]">
              <Waves className="size-3" aria-hidden="true" />
              {pulse.changed.length} cells just updated
            </span>
          ) : null}
          {statusChip}
        </div>
      </header>

      <div className="grid min-h-0 flex-1 gap-3 md:grid-cols-[minmax(0,1.55fr)_minmax(270px,0.85fr)]">
        <div className="aero-brain-panel relative min-h-[360px] overflow-hidden rounded-2xl">
          <BrainCore
            activity={activity}
            weights={weights}
            weightScale={weightScale}
            pulse={pulse}
            enjoyment={enjoyment}
            label={`Live mushroom-body visualization: ${litCount} of ${KC_COUNT} Kenyon cells firing for ${song.title}, predicted enjoyment ${enjoymentPct} percent, ${feedbackCount} learned signals.`}
            className="absolute inset-0"
          />

          {state ? (
            /* Hero readout sits in the empty middle of the sphere. */
            <div className="pointer-events-none absolute inset-0 grid place-items-center">
              <div className="flex flex-col items-center px-6 text-center">
                <p className="text-[10px] font-semibold uppercase tracking-[0.3em] text-cyan-100/85">
                  Predicted enjoyment
                </p>
                <p className="mt-1 text-6xl font-semibold tabular-nums text-white drop-shadow-[0_0_18px_rgba(47,211,255,0.65)] sm:text-7xl">
                  {enjoymentPct}%
                </p>
                <div className="mt-3 h-2 w-44 overflow-hidden rounded-full bg-white/20 ring-1 ring-white/25">
                  <div
                    className="h-full rounded-full transition-[width] duration-500"
                    style={{ width: `${enjoymentPct}%`, background: 'linear-gradient(90deg, var(--aero-cyan), var(--aero-lime))' }}
                  />
                </div>
              </div>
            </div>
          ) : (
            <div className="pointer-events-none absolute inset-0 grid place-items-center">
              <div className="px-6 text-center">
                <p className="text-[10px] font-semibold uppercase tracking-[0.3em] text-cyan-100/75">
                  {brain.status === 'error'
                    ? 'Backend unreachable'
                    : song.id
                      ? 'Reading mushroom body'
                      : 'Nothing queued'}
                </p>
                <p className="mt-1.5 text-xs text-cyan-50/70">
                  {brain.status === 'error'
                    ? 'Start the Python API on 127.0.0.1:8000 to see the circuit'
                    : song.id
                      ? 'GET /brain_state'
                      : 'Pick a track from the playlist'}
                </p>
              </div>
            </div>
          )}

          <div className="pointer-events-none absolute inset-x-4 bottom-3 flex flex-wrap items-center justify-between gap-x-4 gap-y-1 text-[10px] text-cyan-50/75">
            <div className="flex items-center gap-3">
              <span className="flex items-center gap-1.5">
                <span className="size-2 rounded-full bg-[#f2fdff] shadow-[0_0_7px_#2fd3ff]" />
                firing now
              </span>
              <span className="flex items-center gap-1.5">
                <span className="size-2 rounded-full bg-[#2fd3ff] shadow-[0_0_7px_#2fd3ff]" />
                liked
              </span>
              <span className="flex items-center gap-1.5">
                <span className="size-2 rounded-full bg-[#ffb020] shadow-[0_0_7px_#ffb020]" />
                avoided
              </span>
            </div>
          </div>
        </div>

        <aside className="aero-scroll flex min-h-0 flex-col gap-3 overflow-y-auto pr-1">
          <div className="aero-glass rounded-2xl p-4">
            <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-[var(--aero-cyan-deep)]">
              Now analysing
            </p>
            <div className="mt-2.5 flex items-center gap-3">
              <span className="relative size-12 shrink-0 overflow-hidden rounded-lg border border-white/90 shadow-sm">
                <CoverImage
                  key={song.cover}
                  src={song.cover}
                  fallback={fallbackCover(song.id)}
                  alt=""
                  fill
                  sizes="48px"
                  className="object-cover"
                />
              </span>
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold text-[var(--aero-navy)]">{song.title}</p>
                <p className="truncate text-xs text-muted-foreground">{song.artist}</p>
              </div>
            </div>
          </div>

          <StatCard label="Signals learned" icon={<Sparkles className="size-3" />}>
            <div className="mt-1 flex items-baseline gap-2">
              <p className="text-3xl font-semibold tabular-nums text-[var(--aero-navy)]">{feedbackCount}</p>
              <span className="text-[10px] text-muted-foreground">skips + listen-throughs</span>
            </div>
            <p className="mt-1.5 text-xs text-muted-foreground">
              {pulse
                ? `${pulse.changed.length} firing cells shifted their weights`
                : 'Every skip and full listen nudges the weights.'}
            </p>
          </StatCard>

          <StatCard label="Active Kenyon cells" icon={<Activity className="size-3" />}>
            <div className="mt-1 flex items-baseline gap-2">
              <p className="text-3xl font-semibold tabular-nums text-[var(--aero-navy)]">{litCount}</p>
              <span className="text-[10px] text-muted-foreground">
                of {KC_COUNT} firing ({pct(litCount, KC_COUNT)}%)
              </span>
            </div>
            <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/60">
              <div
                className="h-full rounded-full bg-[var(--aero-cyan)] transition-[width] duration-500"
                style={{ width: `${pct(litCount, KC_COUNT)}%` }}
              />
            </div>
          </StatCard>

          <StatCard label="Learned memory" icon={<Brain className="size-3" />}>
            <div className="mt-1.5 flex items-baseline justify-between text-xs font-semibold">
              <span className="text-[var(--aero-cyan-deep)]">{memory.liked} liked</span>
              <span className="text-[var(--aero-amber)]">{memory.avoided} avoided</span>
            </div>
            <div className="mt-1.5 flex h-2 overflow-hidden rounded-full bg-white/60">
              <span className="h-full bg-[var(--aero-cyan)]" style={{ width: `${pct(memory.liked, KC_COUNT)}%` }} />
              <span className="h-full bg-[var(--aero-amber)]" style={{ width: `${pct(memory.avoided, KC_COUNT)}%` }} />
            </div>
            <p className="mt-1.5 text-xs text-muted-foreground">{memory.trained} cells carry a learned weight</p>
          </StatCard>
        </aside>
      </div>

      <p className="sr-only">
        The sphere shows all {KC_COUNT} Kenyon cells: {litCount} are firing for {song.title}, glowing cyan cells carry
        liked weights, amber cells carry avoided weights. Predicted enjoyment is {enjoymentPct} percent after{' '}
        {feedbackCount} learned signals.
      </p>
    </section>
  )
})
