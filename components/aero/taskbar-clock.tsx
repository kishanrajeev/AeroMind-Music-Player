'use client'

import { useEffect, useState } from 'react'

export function TaskbarClock() {
  const [now, setNow] = useState<Date | null>(null)

  useEffect(() => {
    setNow(new Date())
    const id = setInterval(() => setNow(new Date()), 15_000)
    return () => clearInterval(id)
  }, [])

  return (
    <time
      dateTime={now?.toISOString()}
      className="flex min-w-16 flex-col items-center text-[11px] leading-tight text-white [text-shadow:0_1px_2px_rgb(0_0_0/0.6)]"
    >
      <span>{now ? now.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }) : '\u00a0'}</span>
      <span className="text-white/80">{now ? now.toLocaleDateString([], { month: 'numeric', day: 'numeric', year: 'numeric' }) : '\u00a0'}</span>
    </time>
  )
}
