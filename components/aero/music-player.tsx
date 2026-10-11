'use client'

import { useCallback, useEffect, useEffectEvent, useRef, useState } from 'react'
import { Brain } from 'lucide-react'
import { DEFAULT_ALPHA, audioUrl, fetchHealth, fetchPlaylist, toTrack, type Track } from '@/lib/api'
import { postFeedback } from '@/lib/feedback'
import { TitleBar } from './title-bar'
import { NowPlaying } from './now-playing'
import { Playlist } from './playlist'
import { ControlBar, type RepeatMode } from './control-bar'
import { BlendSlider } from './blend-slider'
import { Droplet } from './bubbles'
import { BrainView } from './brain-view'
import { getDesktop } from '@/lib/desktop'

/** Query results: the retrieval pool is 30, so this shows all ranked candidates. */
const QUERY_LIMIT = 30

/** No query: a large n effectively means "the whole library", ranked by taste. */
const LIBRARY_LIMIT = 1000
const SEARCH_DEBOUNCE_MS = 300

/** Shown before the first playlist request lands (or when the library is empty). */
const NOTHING_QUEUED: Track = {
  id: '',
  title: 'Nothing queued',
  artist: 'Pick a track from the playlist',
  album: '',
  cover: '/placeholder.svg',
  duration: 0,
  clap_score: 0,
  brain_score: 0,
  final_score: 0,
}

export function MusicPlayer() {
  const audioRef = useRef<HTMLAudioElement>(null)

  const [query, setQuery] = useState('')
  const [alpha, setAlpha] = useState(DEFAULT_ALPHA)
  const [tracks, setTracks] = useState<Track[]>([])
  const [librarySize, setLibrarySize] = useState(0)
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [current, setCurrent] = useState<Track | null>(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const [audioDuration, setAudioDuration] = useState(0)
  const [volume, setVolume] = useState(70)
  const [muted, setMuted] = useState(false)
  const [shuffle, setShuffle] = useState(false)
  const [repeat, setRepeat] = useState<RepeatMode>('off')
  const [view, setView] = useState<'player' | 'brain'>('player')
  const showPlayer = useCallback(() => setView('player'), [])

  const song = current ?? NOTHING_QUEUED
  const currentIndex = current ? tracks.findIndex((t) => t.id === current.id) : -1
  const duration = audioDuration || song.duration

  // Load the playlist from the search server: once on mount, then on every
  // query change (debounced while typing).
  useEffect(() => {
    const controller = new AbortController()
    setStatus('loading')
    const timer = setTimeout(
      () => {
        const limit = query.trim() ? QUERY_LIMIT : LIBRARY_LIMIT
        fetchPlaylist(query, alpha, limit, controller.signal)
          .then((data) => {
            const results = data.tracks.map(toTrack)
            setTracks(results)
            setStatus('ready')
            // Keep the playing track selected; otherwise surface the top hit.
            setCurrent((prev) => (prev ? results.find((t) => t.id === prev.id) ?? prev : results[0] ?? null))
          })
          .catch(() => {
            if (!controller.signal.aborted) setStatus('error')
          })
      },
      query.trim() ? SEARCH_DEBOUNCE_MS : 0,
    )
    return () => {
      clearTimeout(timer)
      controller.abort()
    }
  }, [query, alpha])

  // Library size, for the "10 of 100 songs" counter.
  useEffect(() => {
    const controller = new AbortController()
    fetchHealth(controller.signal)
      .then((health) => setLibrarySize(health.library_size))
      .catch(() => {})
    return () => controller.abort()
  }, [])

  // Point the audio element at the selected track.
  useEffect(() => {
    const audio = audioRef.current
    if (!audio) return
    setCurrentTime(0)
    setAudioDuration(0)
    if (!song.id) {
      audio.removeAttribute('src')
      audio.load()
      return
    }
    audio.src = audioUrl(song.id)
    audio.load()
  }, [song.id])

  // Play / pause follows the UI state.
  useEffect(() => {
    const audio = audioRef.current
    if (!audio || !song.id) return
    if (isPlaying) {
      audio.play().catch(() => setIsPlaying(false))
    } else {
      audio.pause()
    }
  }, [isPlaying, song.id])

  // Volume + mute.
  useEffect(() => {
    const audio = audioRef.current
    if (!audio) return
    audio.volume = Math.min(1, Math.max(0, volume / 100))
    audio.muted = muted
  }, [volume, muted])

  // Desktop app: the native title bar shows the text the old in-window title bar showed.
  useEffect(() => {
    if (getDesktop()) document.title = `Aero Media Player — ${song.title} — ${song.artist}`
  }, [song.title, song.artist])

  function playSong(id: string) {
    const track = tracks.find((t) => t.id === id)
    if (!track) return
    if (track.id === song.id) {
      seek(0)
      setIsPlaying(true)
      return
    }
    setCurrent(track)
    setCurrentTime(0)
    setIsPlaying(true)
  }

  function next() {
    if (tracks.length === 0) return
    if (shuffle && tracks.length > 1) {
      let index = currentIndex
      while (index === currentIndex) index = Math.floor(Math.random() * tracks.length)
      playSong(tracks[index].id)
      return
    }
    playSong(tracks[(currentIndex + 1) % tracks.length].id)
  }

  /** Next button: counts as a skip, so tell the brain before advancing. */
  function skip() {
    if (song.id) void postFeedback(song.id, -1).catch(() => {})
    next()
  }

  function seek(time: number) {
    setCurrentTime(time)
    const audio = audioRef.current
    if (audio && song.id && audio.readyState > 0) audio.currentTime = time
  }

  function prev() {
    if (currentTime > 3) {
      seek(0)
      return
    }
    if (tracks.length === 0) return
    const base = currentIndex >= 0 ? currentIndex : 0
    playSong(tracks[(base - 1 + tracks.length) % tracks.length].id)
  }

  // A finished track is a listen-through (+1); then advance per repeat/shuffle.
  function handleTrackEnd() {
    const audio = audioRef.current
    if (repeat === 'one') {
      setCurrentTime(0)
      if (audio) {
        audio.currentTime = 0
        void audio.play().catch(() => setIsPlaying(false))
      }
    } else if (repeat === 'off' && !shuffle && currentIndex === tracks.length - 1) {
      setIsPlaying(false)
      setCurrentTime(0)
    } else {
      next()
    }
  }

  const togglePlay = useEffectEvent(() => {
    if (!song.id) return
    setIsPlaying((p) => !p)
  })

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      const target = e.target as HTMLElement
      if (target.tagName === 'INPUT' || target.tagName === 'BUTTON' || target.isContentEditable) return
      if (e.code === 'Space') {
        e.preventDefault()
        togglePlay()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  return (
    <div className="aero-window w-full max-w-5xl overflow-hidden rounded-2xl">
      <audio
        ref={audioRef}
        hidden
        preload="metadata"
        onTimeUpdate={(e) => setCurrentTime(e.currentTarget.currentTime)}
        onLoadedMetadata={(e) => {
          const d = e.currentTarget.duration
          if (Number.isFinite(d) && d > 0) setAudioDuration(d)
        }}
        onEnded={() => {
          if (song.id) void postFeedback(song.id, 1).catch(() => {})
          handleTrackEnd()
        }}
        onError={() => setIsPlaying(false)}
      />

      <TitleBar nowPlaying={`${song.title} — ${song.artist}`} />

      <Droplet size={16} style={{ top: 58, left: '46%' }} />
      <Droplet size={9} style={{ top: 82, left: '48%' }} />
      <Droplet size={12} style={{ bottom: 140, right: 18 }} />

      <div className="aero-player-body flex flex-col gap-4 px-3 pb-3">
        {/* Hidden, not unmounted, while the brain view is open: the player keeps its state and scroll. */}
        <div className={view === 'player' ? 'flex min-h-0 flex-1 flex-col gap-4' : 'hidden'}>
          <div className="aero-player-grid grid gap-3 md:h-[600px] md:grid-cols-[1fr_minmax(300px,380px)]">
            <NowPlaying song={song} isPlaying={isPlaying} />
            <div className="h-[420px] md:h-auto md:min-h-0">
              <Playlist
                songs={tracks}
                totalCount={librarySize || tracks.length}
                query={query}
                onQueryChange={setQuery}
                status={status}
                currentId={song.id}
                isPlaying={isPlaying}
                onSelect={playSong}
              />
            </div>
          </div>

          <div className="flex items-center gap-3">
            <div className="min-w-0 flex-1">
              <BlendSlider alpha={alpha} onAlphaChange={setAlpha} />
            </div>
            <button
              type="button"
              onClick={() => setView('brain')}
              className="aero-pill inline-flex h-9 shrink-0 items-center gap-1.5 px-3 text-xs font-semibold text-[var(--aero-navy)]"
            >
              <Brain className="size-3.5" aria-hidden="true" />
              Mushroom Body
            </button>
          </div>
        </div>

        {view === 'brain' && <BrainView song={song} onBack={showPlayer} />}

        <ControlBar
          isPlaying={isPlaying}
          currentTime={currentTime}
          duration={duration}
          volume={volume}
          muted={muted}
          shuffle={shuffle}
          repeat={repeat}
          onTogglePlay={() => setIsPlaying((p) => !p)}
          onPrev={prev}
          onNext={skip}
          onSeek={seek}
          onVolume={(v) => {
            setVolume(v)
            setMuted(v === 0)
          }}
          onToggleMute={() => setMuted((m) => !m)}
          onToggleShuffle={() => setShuffle((s) => !s)}
          onCycleRepeat={() => setRepeat((r) => (r === 'off' ? 'all' : r === 'all' ? 'one' : 'off'))}
        />
      </div>
    </div>
  )
}
