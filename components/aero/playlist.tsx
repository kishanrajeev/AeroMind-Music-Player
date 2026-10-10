'use client'

import { useEffect, useRef } from 'react'
import Image from 'next/image'
import { Search, X, Volume2, Music2 } from 'lucide-react'
import { formatTime, type Song } from '@/lib/songs'

type PlaylistProps = {
  songs: Song[]
  totalCount: number
  query: string
  onQueryChange: (query: string) => void
  status: 'loading' | 'ready' | 'error'
  currentId: string
  isPlaying: boolean
  onSelect: (id: string) => void
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function Highlight({ text, query }: { text: string; query: string }) {
  const q = query.trim()
  if (!q) return <>{text}</>
  const parts = text.split(new RegExp(`(${escapeRegExp(q)})`, 'ig'))
  return (
    <>
      {parts.map((part, i) =>
        part.toLowerCase() === q.toLowerCase() ? (
          <mark key={i} className="rounded-sm bg-[var(--aero-lime)]/70 px-0.5 text-inherit">
            {part}
          </mark>
        ) : (
          <span key={i}>{part}</span>
        ),
      )}
    </>
  )
}

export function Playlist({ songs, totalCount, query, onQueryChange, status, currentId, isPlaying, onSelect }: PlaylistProps) {
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      const target = e.target as HTMLElement
      const typing = target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable
      if (e.key === '/' && !typing) {
        e.preventDefault()
        inputRef.current?.focus()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  return (
    <section aria-labelledby="playlist-title" className="aero-glass flex h-full min-h-0 flex-col rounded-2xl p-4">
      <div className="flex items-baseline justify-between gap-2 px-1">
        <h2 id="playlist-title" className="text-lg font-semibold text-[var(--aero-navy)] aero-text-glow">
          Playlist
        </h2>
        <p className="text-xs text-muted-foreground" aria-live="polite">
          {query.trim() ? `${songs.length} of ${totalCount} songs` : `${totalCount} songs`}
        </p>
      </div>

      <div className="aero-search mt-3 flex items-center gap-2 px-3">
        <Search className="size-4 shrink-0 text-[var(--aero-cyan-deep)]" aria-hidden="true" />
        <label htmlFor="playlist-search" className="sr-only">
          Search songs, artists, or albums
        </label>
        <input
          ref={inputRef}
          id="playlist-search"
          type="search"
          value={query}
          onChange={(e) => onQueryChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Escape') onQueryChange('')
            if (e.key === 'Enter' && !e.nativeEvent.isComposing && e.keyCode !== 229 && songs[0]) onSelect(songs[0].id)
          }}
          placeholder="Search songs, artists, albums…"
          autoComplete="off"
          className="h-9 min-w-0 flex-1 bg-transparent text-sm text-[var(--aero-navy)] outline-none placeholder:text-[var(--aero-navy)]/45 [&::-webkit-search-cancel-button]:hidden"
        />
        {query ? (
          <button
            type="button"
            onClick={() => {
              onQueryChange('')
              inputRef.current?.focus()
            }}
            aria-label="Clear search"
            className="aero-pill grid size-6 shrink-0 place-items-center"
          >
            <X className="size-3" strokeWidth={3} />
          </button>
        ) : (
          <kbd className="hidden rounded border border-[var(--aero-cyan-deep)]/30 bg-white/70 px-1.5 text-[10px] text-muted-foreground sm:inline">
            /
          </kbd>
        )}
      </div>

      <ul className="aero-scroll mt-3 flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto pr-1" aria-label="Songs">
        {songs.length === 0 && (
          <li className="flex flex-col items-center gap-2 px-4 py-10 text-center">
            <span className="aero-pill grid size-12 place-items-center">
              <Music2 className="size-5 text-[var(--aero-cyan-deep)]" aria-hidden="true" />
            </span>
            <p className="text-sm font-semibold text-[var(--aero-navy)]">
              {status === 'error' ? "Can't reach the server" : status === 'loading' ? 'Loading playlist…' : 'No songs found'}
            </p>
            <p className="text-xs text-muted-foreground">
              {status === 'error'
                ? 'Make sure the backend is running at http://127.0.0.1:8000.'
                : status === 'loading'
                  ? 'Fetching tracks from the server.'
                  : `Nothing matches "${query}". Try another title, artist, or album.`}
            </p>
          </li>
        )}

        {songs.map((song) => {
          const active = song.id === currentId
          return (
            <li key={song.id}>
              <button
                type="button"
                onClick={() => onSelect(song.id)}
                aria-current={active ? 'true' : undefined}
                className={`flex w-full items-center gap-3 rounded-lg border border-transparent px-2 py-1.5 text-left transition-colors hover:border-white/90 hover:bg-white/50 focus-visible:border-[var(--aero-cyan-deep)] focus-visible:outline-none ${
                  active ? 'aero-row-active' : ''
                }`}
              >
                <span className="relative size-10 shrink-0 overflow-hidden rounded-md border border-white/90 shadow-sm">
                  <Image src={song.cover || '/placeholder.svg'} alt="" fill sizes="40px" className="object-cover" />
                  {active && (
                    <span className="absolute inset-0 grid place-items-center bg-[var(--aero-navy)]/40">
                      <Volume2 className={`size-4 text-white ${isPlaying ? 'animate-pulse' : ''}`} aria-hidden="true" />
                    </span>
                  )}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-semibold text-[var(--aero-navy)]">
                    <Highlight text={song.title} query={query} />
                  </span>
                  <span className="block truncate text-xs text-muted-foreground">
                    <Highlight text={song.artist} query={query} />
                    {song.album ? (
                      <>
                        {' · '}
                        <Highlight text={song.album} query={query} />
                      </>
                    ) : null}
                  </span>
                </span>
                <span className="shrink-0 text-xs tabular-nums text-muted-foreground">{formatTime(song.duration)}</span>
                {active && <span className="sr-only">{isPlaying ? '(playing)' : '(paused)'}</span>}
              </button>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
