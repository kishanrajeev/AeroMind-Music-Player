import type { CSSProperties } from 'react'
import { fallbackCover, type Track } from '@/lib/api'
import { Droplet } from './bubbles'
import { CoverImage } from './cover-image'
import { ScoreBars } from './score-bars'

const eqBars = [
  0.9, 0.55, 1.1, 0.7, 1.3, 0.6, 0.95, 1.2, 0.5, 0.85, 1.05, 0.65, 1.15, 0.75, 0.9, 0.6,
  1.0, 0.7, 1.25, 0.55, 0.8, 1.1, 0.6, 0.95, 1.3, 0.65, 0.85, 1.15, 0.5, 0.9, 0.75, 1.05,
]

function EqRow({ isPlaying, className }: { isPlaying: boolean; className?: string }) {
  return (
    <div className={`flex items-center justify-between gap-1 ${className ?? ''}`}>
      {eqBars.map((speed, i) => (
        <span key={i} className="flex h-full w-1 items-center">
          <span
            className="aero-eq-bar block h-full w-full"
            style={
              {
                '--mix': `${Math.round((i / (eqBars.length - 1)) * 100)}%`,
                transformOrigin: 'center',
                animationDuration: `${0.45 + speed * 0.4}s`,
                animationDelay: `${(i % 5) * -0.13}s`,
                animationPlayState: isPlaying ? 'running' : 'paused',
                opacity: isPlaying ? 1 : 0.5,
              } as CSSProperties
            }
          />
        </span>
      ))}
    </div>
  )
}

export function NowPlaying({ song, isPlaying }: { song: Track; isPlaying: boolean }) {
  return (
    <section aria-labelledby="now-playing-title" className="aero-glass flex flex-col items-center justify-center gap-5 rounded-2xl p-5 md:p-7">
      <div className="relative">
        <div className="relative size-52 overflow-hidden rounded-xl border border-white/90 shadow-[0_12px_30px_-8px_rgb(0_60_120/0.5),0_0_30px_rgb(47_211_255/0.35)] sm:size-64">
          <CoverImage
            key={song.cover}
            src={song.cover}
            fallback={fallbackCover(song.id)}
            alt={`Album art for ${song.album || song.title}`}
            fill
            sizes="256px"
            className="object-cover animate-in fade-in duration-500"
            priority
          />
          <div
            aria-hidden="true"
            className="pointer-events-none absolute inset-x-0 top-0 h-1/2 bg-gradient-to-b from-white/45 to-white/0"
          />
          <Droplet size={18} style={{ top: '14%', right: '12%' }} />
          <Droplet size={10} style={{ top: '26%', right: '22%' }} />
          <Droplet size={14} style={{ bottom: '18%', left: '10%' }} />
          <Droplet size={7} style={{ bottom: '28%', left: '20%' }} />
        </div>

        <div aria-hidden="true" className="relative mt-1 h-16 overflow-hidden sm:h-20">
          <div className="relative size-52 -scale-y-100 overflow-hidden rounded-xl opacity-35 sm:size-64 [mask-image:linear-gradient(to_top,black,transparent_35%)]">
            <CoverImage src={song.cover} fallback={fallbackCover(song.id)} alt="" fill sizes="256px" className="object-cover" />
          </div>
        </div>
      </div>

      <div className="-mt-14 flex w-full flex-col items-center gap-1 text-center sm:-mt-16">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[var(--aero-cyan-deep)]">
          {isPlaying ? 'Now Playing' : 'Paused'}
        </p>
        <h2 id="now-playing-title" className="text-balance text-2xl font-semibold text-[var(--aero-navy)] aero-text-glow sm:text-3xl">
          {song.title}
        </h2>
        <p className="text-sm text-muted-foreground">
          {song.artist}
          {song.album ? (
            <>
              <span aria-hidden="true">{' · '}</span>
              <span className="italic">{song.album}</span>
            </>
          ) : null}
        </p>
        <ScoreBars track={song} labelled className="mt-3 w-full max-w-xs text-left" />
      </div>

      <div aria-hidden="true" className="aero-eq-well w-full rounded-full px-6 py-2.5">
        <EqRow isPlaying={isPlaying} className="h-7" />
      </div>
    </section>
  )
}
