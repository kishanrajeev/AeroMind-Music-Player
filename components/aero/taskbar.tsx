import { Droplet, Volume2, Wifi } from 'lucide-react'
import { TaskbarClock } from './taskbar-clock'

function WindowsFlag() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className="h-6 w-6 drop-shadow-[0_1px_1px_rgba(0,0,0,0.5)]">
      <defs>
        <linearGradient id="flag-red" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#ff8a5c" />
          <stop offset="1" stopColor="#e2311d" />
        </linearGradient>
        <linearGradient id="flag-green" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#b6f25a" />
          <stop offset="1" stopColor="#3fa50f" />
        </linearGradient>
        <linearGradient id="flag-blue" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#7cd3ff" />
          <stop offset="1" stopColor="#1268d8" />
        </linearGradient>
        <linearGradient id="flag-yellow" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#ffe873" />
          <stop offset="1" stopColor="#f2a900" />
        </linearGradient>
      </defs>
      <path d="M2 4.6c2.6-1.3 5.3-1.4 8.6.2v6.5c-3.3-1.6-6-1.5-8.6-.2z" fill="url(#flag-red)" />
      <path d="M12 5.4c3.3 1.6 6.4 1.5 10-.4v6.5c-3.6 1.9-6.7 2-10 .4z" fill="url(#flag-green)" />
      <path d="M2 12.6c2.6-1.3 5.3-1.4 8.6.2v6.5c-3.3-1.6-6-1.5-8.6-.2z" fill="url(#flag-blue)" />
      <path d="M12 13.4c3.3 1.6 6.4 1.5 10-.4v6.5c-3.6 1.9-6.7 2-10 .4z" fill="url(#flag-yellow)" />
    </svg>
  )
}

export function Taskbar() {
  return (
    <footer className="fixed inset-x-0 bottom-0 z-40 h-11">
      <div
        aria-hidden="true"
        className="absolute inset-0 border-t border-white/40 bg-gradient-to-b from-[#3a6a7c]/70 via-[#0d3442]/80 to-[#04161e]/90 shadow-[0_-4px_24px_rgba(0,40,60,0.35)] backdrop-blur-xl"
      />
      <div aria-hidden="true" className="absolute inset-x-0 top-0 h-1/2 bg-gradient-to-b from-white/25 to-white/5" />
      <div aria-hidden="true" className="absolute inset-x-0 top-px h-px bg-cyan-200/50" />

      <nav aria-label="Taskbar" className="relative flex h-full items-center pl-2">
        <button
          type="button"
          aria-label="Start"
          className="group relative -mt-3 flex h-14 w-14 items-center justify-center rounded-full border border-white/60 bg-[radial-gradient(circle_at_50%_75%,#5ee6ff_0%,#1a8fb5_40%,#0a3a52_75%,#06202e_100%)] shadow-[0_0_0_1px_rgba(0,0,0,0.45),0_2px_10px_rgba(0,200,255,0.45),inset_0_-4px_10px_rgba(140,255,120,0.35)] transition-all duration-200 hover:shadow-[0_0_0_1px_rgba(0,0,0,0.45),0_0_22px_rgba(120,255,240,0.85),inset_0_-4px_12px_rgba(160,255,120,0.6)] hover:brightness-110 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-lime-300 active:scale-95"
        >
          <span
            aria-hidden="true"
            className="pointer-events-none absolute inset-x-1.5 top-1 h-[46%] rounded-t-full bg-gradient-to-b from-white/80 to-white/5"
          />
          <span
            aria-hidden="true"
            className="pointer-events-none absolute inset-0 rounded-full opacity-0 transition-opacity duration-200 group-hover:opacity-100 bg-[radial-gradient(circle_at_50%_85%,rgba(170,255,120,0.55),transparent_60%)]"
          />
          <span className="relative">
            <WindowsFlag />
          </span>
        </button>

        <div className="ml-3 flex h-full items-center gap-1 py-1" role="list" aria-label="Open applications">
          <button
            type="button"
            role="listitem"
            aria-current="true"
            aria-label="Aero Media Player, active window"
            className="group relative flex h-full w-12 items-center gap-2 overflow-hidden rounded-[4px] border border-white/45 bg-gradient-to-b from-[#7fd8f0]/45 via-[#2a8fb3]/35 to-[#0b4a66]/50 px-2 shadow-[inset_0_0_0_1px_rgba(0,0,0,0.35),inset_0_0_12px_rgba(120,240,255,0.45),0_0_10px_rgba(80,220,255,0.35)] transition-all hover:brightness-125 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-lime-300 sm:w-52"
          >
            <span aria-hidden="true" className="pointer-events-none absolute inset-x-0 top-0 h-1/2 bg-gradient-to-b from-white/35 to-white/5" />
            <span
              aria-hidden="true"
              className="pointer-events-none absolute inset-x-2 bottom-0 h-3 rounded-full bg-[radial-gradient(ellipse_at_50%_100%,rgba(170,255,120,0.75),transparent_70%)]"
            />
            <span className="aero-orb relative grid size-6 shrink-0 place-items-center" aria-hidden="true">
              <Droplet className="relative size-3.5" fill="currentColor" />
            </span>
            <span className="relative hidden truncate text-xs text-white [text-shadow:0_1px_2px_rgb(0_0_0/0.6)] sm:inline">
              Aero Media Player
            </span>
          </button>
        </div>

        <div className="ml-auto flex h-full items-center gap-3 border-l border-white/15 bg-gradient-to-b from-white/5 to-black/20 px-3 shadow-[inset_1px_0_0_rgba(0,0,0,0.35)]">
          <Volume2 aria-label="Volume" className="size-4 text-white/90 drop-shadow-[0_1px_1px_rgba(0,0,0,0.6)]" />
          <Wifi aria-label="Network connected" className="hidden size-4 text-white/90 drop-shadow-[0_1px_1px_rgba(0,0,0,0.6)] sm:block" />
          <TaskbarClock />
        </div>
      </nav>
    </footer>
  )
}
