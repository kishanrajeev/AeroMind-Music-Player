import type { Track } from '@/lib/api'

type Scores = Pick<Track, 'clap_score' | 'brain_score' | 'final_score'>

const ROWS = [
  { key: 'clap_score', label: 'match', background: 'var(--aero-cyan)' },
  { key: 'brain_score', label: 'taste', background: 'var(--aero-lime, #a3e635)' },
  {
    key: 'final_score',
    label: 'final',
    background: 'linear-gradient(90deg, var(--aero-cyan), var(--aero-lime, #a3e635))',
  },
] as const

function pct(value: number) {
  return Math.round(Math.max(0, Math.min(1, value)) * 100)
}

/** The three blend scores. Compact = thin stacked bars; labelled = rows with values. */
export function ScoreBars({
  track,
  labelled = false,
  className = '',
}: {
  track: Scores
  labelled?: boolean
  className?: string
}) {
  if (!labelled) {
    return (
      <span className={`flex flex-col gap-[2px] ${className}`} aria-hidden="true">
        {ROWS.map((row) => (
          <span key={row.key} className="block h-[3px] w-full overflow-hidden rounded-full bg-white/60">
            <span
              className="block h-full rounded-full"
              style={{ width: `${pct(track[row.key])}%`, background: row.background }}
              title={`${row.label} ${pct(track[row.key])}%`}
            />
          </span>
        ))}
      </span>
    )
  }

  return (
    <div className={`flex flex-col gap-1.5 ${className}`}>
      {ROWS.map((row) => (
        <div key={row.key} className="flex items-center gap-2">
          <span className="w-9 shrink-0 text-right text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
            {row.label}
          </span>
          <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-white/60">
            <span
              className="block h-full rounded-full transition-[width] duration-300"
              style={{ width: `${pct(track[row.key])}%`, background: row.background }}
            />
          </span>
          <span className="w-8 shrink-0 text-right text-[10px] tabular-nums text-muted-foreground">
            {pct(track[row.key])}%
          </span>
        </div>
      ))}
    </div>
  )
}
