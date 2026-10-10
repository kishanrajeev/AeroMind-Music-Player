'use client'

import type { CSSProperties } from 'react'

/**
 * One control: left = literal phrase match (alpha 1.0), right = learned taste
 * (alpha 0.0). The range value is inverted so the left end is the literal one,
 * matching the spec's "literal match <- -> my taste" direction.
 */
export function BlendSlider({
  alpha,
  onAlphaChange,
}: {
  alpha: number
  onAlphaChange: (value: number) => void
}) {
  const taste = Math.round((1 - alpha) * 100)

  return (
    <div className="aero-glass flex items-center gap-3 rounded-2xl px-4 py-2.5">
      <span className="shrink-0 text-[10px] font-semibold uppercase tracking-[0.15em] text-[var(--aero-cyan-deep)]">
        literal match
      </span>
      <input
        type="range"
        min={0}
        max={1}
        step={0.01}
        value={1 - alpha}
        onChange={(e) => onAlphaChange(1 - Number(e.target.value))}
        aria-label="Blend: literal match to my taste"
        aria-valuetext={`${taste}% my taste, ${100 - taste}% literal match`}
        className="aero-range min-w-0 flex-1"
        style={{ '--value': `${Math.round((1 - alpha) * 100)}%` } as CSSProperties}
      />
      <span className="shrink-0 text-[10px] font-semibold uppercase tracking-[0.15em] text-[var(--aero-navy)]/70">
        my taste
      </span>
    </div>
  )
}
